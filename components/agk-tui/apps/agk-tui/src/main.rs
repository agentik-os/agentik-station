mod data;
mod input;
mod model;
mod paste;
mod system_info;
mod theme;
mod ui;

use std::{
    env, io,
    os::unix::process::CommandExt,
    path::PathBuf,
    process::Command,
    time::{Duration, Instant},
};

use anyhow::{Context, Result};
use crossterm::{
    cursor::Show,
    event::{
        self, DisableBracketedPaste, DisableMouseCapture, EnableBracketedPaste, EnableMouseCapture,
        Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers, MouseButton, MouseEvent,
        MouseEventKind,
    },
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use data::RegistryClient;
use input::Action;
use model::{App, Density, Focus, Mode, Overlay, SessionTarget, View, density};
use ratatui::{Terminal, backend::CrosstermBackend};
use ratatui_rmux::PaneState;
use rmux_sdk::{Pane, PaneCursor, PaneSnapshot, Rmux};
use system_info::SystemInfoService;
use theme::Preferences;
use ui::SessionPreview;

const FRAME_TIME: Duration = Duration::from_millis(33);
const INPUT_DRAIN_BUDGET: Duration = Duration::from_millis(8);
const PREVIEW_REFRESH_TIME: Duration = Duration::from_millis(100);
const FOOTER_CONTEXT_REFRESH_TIME: Duration = Duration::from_millis(250);
const SESSION_START_TIMEOUT: Duration = Duration::from_secs(8);
const DOUBLE_TAB_TIME: Duration = Duration::from_millis(320);

#[derive(Debug)]
struct PendingSession {
    name: String,
    started_at: Instant,
    enter_terminal: bool,
}

impl PendingSession {
    fn created(name: String) -> Self {
        Self {
            name,
            started_at: Instant::now(),
            enter_terminal: true,
        }
    }

    fn renamed(name: String) -> Self {
        Self {
            name,
            started_at: Instant::now(),
            enter_terminal: false,
        }
    }
}

#[derive(Debug, Eq, PartialEq)]
enum PendingResolution {
    Waiting,
    Ready { name: String, enter_terminal: bool },
    TimedOut { name: String, registered: bool },
}

#[tokio::main]
async fn main() -> Result<()> {
    let environment = std::env::var("AGK_ENVIRONMENT")
        .unwrap_or_else(|_| std::env::var("USER").unwrap_or_else(|_| "agentik".into()));
    let (preferences, preference_warning) = match Preferences::load() {
        Ok(preferences) => (preferences, None),
        Err(error) => (
            Preferences::default(),
            Some(format!("Preferences could not be loaded: {error}")),
        ),
    };
    let registry = RegistryClient::discover(environment.clone());
    let rmux = Rmux::builder()
        .default_timeout(Duration::from_secs(3))
        .connect_or_start()
        .await
        .context("connect to RMUX")?;

    let mut app = App::new(preferences);
    app.current_rmux_session = current_rmux_session();
    app.status = preference_warning;
    refresh(&rmux, &registry, &mut app).await?;

    enable_raw_mode().context("enable terminal raw mode")?;
    let _restore = RestoreTerminal;
    let mut stdout = io::stdout();
    execute!(
        stdout,
        EnterAlternateScreen,
        EnableMouseCapture,
        EnableBracketedPaste
    )?;
    let mut terminal = Terminal::new(CrosstermBackend::new(stdout))?;
    terminal.clear()?;
    run(&mut terminal, &rmux, &registry, &mut app).await
}

struct RestoreTerminal;

impl Drop for RestoreTerminal {
    fn drop(&mut self) {
        let _ = disable_raw_mode();
        let _ = execute!(
            io::stdout(),
            DisableBracketedPaste,
            DisableMouseCapture,
            LeaveAlternateScreen,
            Show
        );
    }
}

async fn refresh(rmux: &Rmux, registry: &RegistryClient, app: &mut App) -> Result<()> {
    let live_names = rmux
        .list_sessions()
        .await
        .context("list RMUX sessions")?
        .into_iter()
        .map(|name| name.as_ref().to_owned())
        .collect::<Vec<_>>();
    app.set_snapshot(registry.load(&live_names));
    Ok(())
}

async fn run(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    rmux: &Rmux,
    registry: &RegistryClient,
    app: &mut App,
) -> Result<()> {
    let mut host = SystemInfoService::new();
    let mut last_refresh = Instant::now();
    let mut refresh_requested = false;
    let mut pending_session: Option<PendingSession> = None;
    let mut preview_cache = PreviewCache::default();
    let mut observed_status = app.status.clone();
    let mut status_since = Instant::now();
    let mut last_preview_refresh = Instant::now() - PREVIEW_REFRESH_TIME;
    let mut last_footer_refresh = Instant::now() - FOOTER_CONTEXT_REFRESH_TIME;
    let mut last_tab_at: Option<Instant> = None;
    let mut preview_refresh_requested = true;
    let mut rendered_layout = None;

    'event_loop: loop {
        if app.status != observed_status {
            observed_status.clone_from(&app.status);
            status_since = Instant::now();
        } else if app.status.is_some() && status_since.elapsed() >= Duration::from_secs(4) {
            app.status = None;
            observed_status = None;
        }
        let refresh_interval = Duration::from_millis(app.preferences.refresh_ms.max(100));
        if refresh_requested || last_refresh.elapsed() >= refresh_interval {
            match refresh(rmux, registry, app).await {
                Ok(()) => {
                    let resolution = pending_session
                        .as_ref()
                        .map(|pending| resolve_pending_session(app, pending, Instant::now()));
                    match resolution {
                        Some(PendingResolution::Ready {
                            name,
                            enter_terminal,
                        }) => {
                            pending_session = None;
                            if enter_terminal {
                                app.mode = Mode::Terminal;
                                app.focus = Focus::Detail;
                                app.expanded = false;
                                app.scroll_preview_live();
                                preview_cache.clear();
                                preview_refresh_requested = true;
                                app.status = Some(format!("Created and opened {name}"));
                            } else {
                                app.status = Some(format!("Renamed and selected {name}"));
                            }
                        }
                        Some(PendingResolution::TimedOut { name, registered }) => {
                            pending_session = None;
                            app.status = Some(if registered {
                                format!(
                                    "Session {name} was created but its provider terminal did not stay live"
                                )
                            } else {
                                format!("Session {name} did not appear in RMUX after creation")
                            });
                        }
                        Some(PendingResolution::Waiting) | None => {}
                    }
                    if refresh_requested {
                        app.status
                            .get_or_insert_with(|| "RMUX and MCP registries refreshed".into());
                    }
                }
                Err(error) => app.status = Some(format!("Refresh failed: {error:#}")),
            }
            last_refresh = Instant::now();
            refresh_requested = false;
        }

        if last_footer_refresh.elapsed() >= FOOTER_CONTEXT_REFRESH_TIME {
            update_footer(&mut host, app);
            last_footer_refresh = Instant::now();
        }
        let size = terminal.size()?;
        let layout = (
            app.mode,
            app.view,
            app.expanded,
            app.preferences.split_preview,
            size.width,
            size.height,
        );
        if rendered_layout != Some(layout) {
            // Mode changes and responsive pane transitions rewrite large areas.
            // Force the physical terminal to match Ratatui's model instead of
            // trusting a stale differential buffer after an alternate-screen
            // transition or resize.
            terminal.clear()?;
            preview_cache.invalidate_layout();
            preview_refresh_requested = true;
            rendered_layout = Some(layout);
        }
        if app.mode == Mode::Terminal {
            let pane = ui::terminal_preview_area(size, app.expanded);
            app.preview_width = pane.width;
            app.preview_height = pane.height;
        }
        // A pane snapshot is an RPC and must never sit in front of queued
        // keyboard input. Capture only a visible preview, and never rediscover
        // the same pane on every frame or keystroke.
        let input_pending = event::poll(Duration::ZERO)?;
        let history_requested = app.preview_scroll > 0 && preview_cache.history.is_none();
        if preview_is_visible(app)
            && (preview_refresh_requested
                || history_requested
                || (!input_pending && last_preview_refresh.elapsed() >= PREVIEW_REFRESH_TIME))
        {
            refresh_preview(rmux, app, &mut preview_cache).await;
            last_preview_refresh = Instant::now();
            preview_refresh_requested = false;
        } else {
            if app.view != View::Sessions {
                preview_cache.clear();
            }
        }
        terminal.draw(|frame| ui::draw(frame, app, preview_cache.view()))?;

        if !input_pending && !event::poll(FRAME_TIME)? {
            continue;
        }
        let drain_started = Instant::now();
        let mut queued_events = vec![event::read()?];
        while drain_started.elapsed() < INPUT_DRAIN_BUDGET && event::poll(Duration::ZERO)? {
            queued_events.push(event::read()?);
        }

        for event in queued_events {
            let mut terminal_action = None;
            if !matches!(&event, Event::Key(key) if accepts_key(key) && key.code == KeyCode::Tab) {
                last_tab_at = None;
            }
            if app.mode == Mode::Terminal {
                match &event {
                    Event::Key(key) if accepts_key(key) && terminal_returns_to_control(key) => {
                        app.mode = Mode::Control;
                        app.view = View::Sessions;
                        app.focus = Focus::List;
                        app.expanded = false;
                        app.scroll_preview_live();
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                        continue;
                    }
                    Event::Key(key) if accepts_key(key) && key.code == KeyCode::Tab => {
                        let double = register_tab(&mut last_tab_at, Instant::now());
                        let _ = session_tab(app, true, double);
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                        continue;
                    }
                    Event::Key(key)
                        if accepts_key(key)
                            && app.focus == Focus::Detail
                            && terminal_scroll_key(app, key) =>
                    {
                        preview_refresh_requested = true;
                        continue;
                    }
                    Event::Key(key)
                        if accepts_key(key)
                            && app.focus == Focus::List
                            && terminal_sidebar_control_key(key) =>
                    {
                        // The visible sidebar remains the Sessions control
                        // surface while a provider owns the right pane. Route
                        // its actions through the normal dispatcher so n/x/r
                        // cannot be swallowed by terminal input handling.
                        app.mode = Mode::Control;
                        app.view = View::Sessions;
                        app.expanded = false;
                        let size = terminal.size()?;
                        let detail_available = app.current_session().is_some();
                        terminal_action = Some(input::handle_key_for_layout(
                            app,
                            *key,
                            detail_available,
                            density(size.width, size.height) == Density::Compact,
                        ));
                        preview_cache.clear();
                        preview_refresh_requested = true;
                    }
                    Event::Key(key)
                        if accepts_key(key)
                            && app.focus == Focus::List
                            && terminal_top_nav_key(app, key) =>
                    {
                        preview_cache.clear();
                        preview_refresh_requested = true;
                        continue;
                    }
                    Event::Key(key) if accepts_key(key) && app.focus == Focus::List => {
                        let selected_before = app.selected_session_name().map(str::to_owned);
                        if terminal_sidebar_key(app, key)
                            && selected_before.as_deref() != app.selected_session_name()
                        {
                            preview_cache.clear();
                            preview_refresh_requested = true;
                        }
                        continue;
                    }
                    Event::Mouse(mouse) => {
                        let size = terminal.size()?;
                        match ui::terminal_focus_at(size, app.expanded, mouse.column, mouse.row) {
                            Some(Focus::List) => {
                                let selected_before =
                                    app.selected_session_name().map(str::to_owned);
                                app.expanded = false;
                                app.focus = Focus::List;
                                match mouse.kind {
                                    MouseEventKind::ScrollUp => {
                                        for _ in 0..3 {
                                            app.select_previous();
                                        }
                                    }
                                    MouseEventKind::ScrollDown => {
                                        for _ in 0..3 {
                                            app.select_next();
                                        }
                                    }
                                    _ => {}
                                }
                                if selected_before.as_deref() != app.selected_session_name() {
                                    preview_cache.clear();
                                    preview_refresh_requested = true;
                                }
                                continue;
                            }
                            Some(Focus::Detail) => {
                                app.focus = Focus::Detail;
                                match mouse.kind {
                                    MouseEventKind::ScrollUp => {
                                        app.scroll_preview_up(3);
                                        preview_refresh_requested = true;
                                        continue;
                                    }
                                    MouseEventKind::ScrollDown => {
                                        app.scroll_preview_down(3);
                                        preview_refresh_requested = true;
                                        continue;
                                    }
                                    _ => {}
                                }
                            }
                            Some(Focus::Nav) | None => continue,
                        }
                    }
                    Event::Resize(_, _) => {
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                        continue;
                    }
                    _ => {}
                }
                if terminal_action.is_none() && app.focus == Focus::Detail {
                    if app.preview_scroll > 0 {
                        app.scroll_preview_live();
                        preview_refresh_requested = true;
                    }
                    send_terminal_event(rmux, app, &mut preview_cache, event.clone()).await;
                }
                if terminal_action.is_none() {
                    continue;
                }
            }

            let detail_available = detail_available(app);
            let preview_scroll_before = app.preview_scroll;
            let selected_session_before = app.selected_session_name().map(str::to_owned);
            let action = if let Some(action) = terminal_action {
                action
            } else {
                match event {
                    Event::Mouse(mouse) => {
                        let outcome = handle_mouse(app, mouse, terminal.size()?);
                        if outcome.preview_scrolled {
                            preview_refresh_requested = true;
                        }
                        if outcome.activate_session {
                            Action::EnterTerminal
                        } else {
                            Action::None
                        }
                    }
                    Event::Key(key)
                        if accepts_key(&key)
                            && key.code == KeyCode::Tab
                            && app.view == View::Sessions =>
                    {
                        let double = register_tab(&mut last_tab_at, Instant::now());
                        if session_tab(app, detail_available, double) {
                            Action::EnterTerminal
                        } else {
                            Action::None
                        }
                    }
                    Event::Key(key) if accepts_key(&key) => {
                        let size = terminal.size()?;
                        input::handle_key_for_layout(
                            app,
                            key,
                            detail_available,
                            density(size.width, size.height) == Density::Compact,
                        )
                    }
                    Event::Paste(text) => input::handle_paste(app, &text),
                    Event::Resize(_, _) => {
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                        Action::None
                    }
                    _ => Action::None,
                }
            };
            if app.preview_scroll != preview_scroll_before {
                preview_refresh_requested = true;
            }
            if selected_session_before.as_deref() != app.selected_session_name() {
                preview_cache.clear();
                preview_refresh_requested = true;
            }
            match action {
                Action::None => {}
                Action::Quit => break 'event_loop,
                Action::Reload => return reload_agk(terminal),
                Action::Refresh => {
                    refresh_requested = true;
                    preview_cache.clear();
                    preview_refresh_requested = true;
                }
                Action::PersistPreferences => match app.preferences.save() {
                    Ok(()) => {
                        if app.status.is_none() {
                            app.status = Some("Preferences saved".into());
                        }
                    }
                    Err(error) => {
                        app.status = Some(format!("Could not save preferences: {error}"));
                    }
                },
                Action::InstallProvider { id } => match install_provider(terminal, &id) {
                    Ok(true) => {
                        app.status = Some(format!("Provider {id} installed and verified"));
                        refresh_requested = true;
                        rendered_layout = None;
                        preview_refresh_requested = true;
                    }
                    Ok(false) => {
                        app.status = Some(format!("Provider {id} setup did not complete"));
                        refresh_requested = true;
                        rendered_layout = None;
                        preview_refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Provider setup failed: {error:#}"));
                        rendered_layout = None;
                        preview_refresh_requested = true;
                    }
                },
                Action::EnterTerminal => {
                    if enter_selected_terminal(app) {
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                    }
                }
                Action::CreateSession { kind, name } => match create_session(kind.slug(), &name) {
                    Ok(message) => {
                        app.status = Some(format!("{message} · opening provider terminal…"));
                        pending_session = Some(PendingSession::created(name));
                        refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Session creation failed: {error:#}"));
                        app.overlay = Overlay::NewName { kind, value: name };
                    }
                },
                Action::OpenAgent { id, session } => match open_agent(&id, &session) {
                    Ok(message) => {
                        app.status = Some(format!("{message} · opening agent terminal…"));
                        pending_session = Some(PendingSession::created(session));
                        refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Agent launch failed: {error:#}"));
                    }
                },
                Action::ResumeConversation { target } => match resume_conversation(&target) {
                    Ok(message) => {
                        app.status = Some(format!("{message} · opening synced conversation…"));
                        pending_session = Some(PendingSession::created(target.name));
                        refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Conversation resume failed: {error:#}"));
                    }
                },
                Action::RenameSession { target, name } => match rename_session(&target, &name) {
                    Ok(message) => {
                        if app.current_rmux_session.as_deref() == Some(target.rmux_session.as_str())
                        {
                            app.current_rmux_session = Some(name.clone());
                        }
                        app.status = Some(message);
                        pending_session = Some(PendingSession::renamed(name));
                        refresh_requested = true;
                        preview_cache.clear();
                        preview_refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Session rename failed: {error:#}"));
                    }
                },
                Action::CloseSession { target } => {
                    if app.current_rmux_session.as_deref() == Some(target.rmux_session.as_str()) {
                        app.status = Some(
                            "AGK cannot close the RMUX session that is running this interface"
                                .into(),
                        );
                    } else {
                        match close_session(&target) {
                            Ok(message) => {
                                app.status = Some(message);
                                refresh_requested = true;
                                preview_cache.clear();
                                preview_refresh_requested = true;
                            }
                            Err(error) => {
                                app.status = Some(format!("Session close failed: {error:#}"));
                            }
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

fn reload_agk(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>) -> Result<()> {
    disable_raw_mode().context("leave raw mode before AGK reload")?;
    execute!(
        terminal.backend_mut(),
        DisableBracketedPaste,
        DisableMouseCapture,
        LeaveAlternateScreen,
        Show
    )
    .context("restore terminal before AGK reload")?;
    let executable = env::current_exe().context("resolve the running AGK executable")?;
    let error = Command::new(&executable).exec();
    Err(error).with_context(|| format!("reload AGK from {}", executable.display()))
}

fn install_provider(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    provider: &str,
) -> Result<bool> {
    disable_raw_mode().context("leave raw mode for provider setup")?;
    execute!(
        terminal.backend_mut(),
        DisableBracketedPaste,
        DisableMouseCapture,
        LeaveAlternateScreen,
        Show
    )
    .context("leave AGK screen for provider setup")?;

    let installer = env::var_os("AGK_TERMINAL_BIN").unwrap_or_else(|| "agk-terminal".into());
    let result = Command::new(installer)
        .args(["provider", "install", provider])
        .status()
        .context("run AGK-TUI provider installer");

    enable_raw_mode().context("restore raw mode after provider setup")?;
    execute!(
        terminal.backend_mut(),
        EnterAlternateScreen,
        EnableMouseCapture,
        EnableBracketedPaste
    )
    .context("restore AGK screen after provider setup")?;
    terminal.clear().context("clear restored AGK screen")?;
    result.map(|status| status.success())
}

fn update_footer(host: &mut SystemInfoService, app: &mut App) {
    let directory = footer_directory(app);
    let usage = footer_model_usage(app);
    host.refresh_for_context(
        usage.map(data::ModelUsageRecord::io_tokens),
        usage.map(|usage| usage.model.as_str()),
        app.snapshot.runtimes.len(),
        directory.as_deref(),
    );
    app.footer = host.snapshot().clone();
}

fn footer_model_usage(app: &App) -> Option<&data::ModelUsageRecord> {
    let session = app.selected_session_name()?;
    app.snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.name == session)
        .and_then(|runtime| runtime.model_usage.first())
}

fn footer_directory(app: &App) -> Option<PathBuf> {
    if app.view == View::Projects {
        return app
            .current_object()
            .filter(|object| object.kind.eq_ignore_ascii_case("project"))
            .and_then(|object| object.path.as_deref())
            .map(PathBuf::from);
    }

    let session = app.selected_session_name()?;
    app.snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.name == session)
        .map(|runtime| PathBuf::from(&runtime.cwd))
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
enum PreviewState {
    Live,
    History,
    CurrentSession,
    #[default]
    Unavailable,
}

#[derive(Default)]
struct PreviewCache {
    session: Option<String>,
    handle: Option<Pane>,
    target: Option<String>,
    pane: Option<PaneState>,
    history: Option<Vec<String>>,
    size: Option<(u16, u16)>,
    state: PreviewState,
}

impl PreviewCache {
    fn clear(&mut self) {
        self.session = None;
        self.handle = None;
        self.target = None;
        self.pane = None;
        self.history = None;
        self.size = None;
        self.state = PreviewState::Unavailable;
    }

    fn select(&mut self, session: &str) {
        if self.session.as_deref() != Some(session) {
            self.clear();
            self.session = Some(session.to_owned());
        }
    }

    fn invalidate_layout(&mut self) {
        // Keep the last correct frame visible while the resized snapshot is
        // fetched. Dropping the whole cache here produces a visible offline
        // flash every time focus or fullscreen changes.
        self.size = None;
    }

    fn view(&self) -> SessionPreview<'_> {
        match self.state {
            PreviewState::Live => self
                .pane
                .as_ref()
                .map(SessionPreview::Live)
                .unwrap_or(SessionPreview::Unavailable),
            PreviewState::History => self
                .history
                .as_deref()
                .map(SessionPreview::History)
                .unwrap_or(SessionPreview::Unavailable),
            PreviewState::CurrentSession => SessionPreview::CurrentSession,
            PreviewState::Unavailable => SessionPreview::Unavailable,
        }
    }

    fn invalidate_handle(&mut self) {
        self.handle = None;
        self.target = None;
        self.size = None;
    }
}

fn preview_is_visible(app: &App) -> bool {
    app.view == View::Sessions
        && (app.mode == Mode::Terminal
            || (app.preview_width > 1
                && app.preview_height > 1
                && (app.focus == Focus::Detail || app.preferences.split_preview)))
}

async fn cached_primary_pane(
    rmux: &Rmux,
    session_name: &str,
    cache: &mut PreviewCache,
) -> Option<Pane> {
    cache.select(session_name);
    if let Some(pane) = cache.handle.clone() {
        return Some(pane);
    }
    let pane = primary_pane(rmux, session_name).await?;
    cache.target = Some(
        pane.id()
            .await
            .ok()
            .flatten()
            .map(|id| id.to_string())
            .unwrap_or_else(|| session_name.to_owned()),
    );
    cache.handle = Some(pane.clone());
    Some(pane)
}

async fn refresh_preview(rmux: &Rmux, app: &App, cache: &mut PreviewCache) {
    let Some(runtime) = app.current_session() else {
        cache.clear();
        return;
    };
    cache.select(&runtime.rmux_session);
    if app.selected_is_current_rmux_session() {
        cache.invalidate_handle();
        cache.pane = None;
        cache.history = None;
        cache.state = PreviewState::CurrentSession;
        return;
    }
    if !runtime.live {
        cache.invalidate_handle();
        cache.pane = None;
        cache.history = None;
        cache.state = PreviewState::Unavailable;
        return;
    }
    let session_name = runtime.rmux_session.clone();
    let Some(pane) = cached_primary_pane(rmux, &session_name, cache).await else {
        cache.state = PreviewState::Unavailable;
        return;
    };
    let width = app.preview_width;
    let height = app.preview_height;
    let target = cache.target.clone().unwrap_or_else(|| session_name.clone());
    if width > 1 && height > 1 && cache.size != Some((width, height)) {
        // A pane cannot grow beyond its window. The SDK's pane.resize() is
        // therefore a no-op for the usual one-pane AGK sessions; resize the
        // owning rmux window so the agent receives SIGWINCH.
        let _ = resize_window(&target, width, height);
        cache.size = Some((width, height));
    }
    if app.preview_scroll > 0 {
        if cache.history.is_none() {
            cache.history = capture_history(&target);
        }
        if cache.history.is_some() {
            cache.pane = None;
            cache.state = PreviewState::History;
            return;
        }
    }
    cache.history = None;
    let snapshot = pane.snapshot().await.ok();
    if snapshot.is_none() {
        cache.invalidate_handle();
    }
    cache.pane = snapshot
        .map(|snapshot| crop_snapshot_to_height(snapshot, height))
        .map(PaneState::from_snapshot);
    cache.state = if cache.pane.is_some() {
        PreviewState::Live
    } else {
        PreviewState::Unavailable
    };
}

fn resize_window(target: &str, width: u16, height: u16) -> bool {
    Command::new("rmux")
        .args([
            "resize-window",
            "-t",
            target,
            "-x",
            &width.to_string(),
            "-y",
            &height.to_string(),
        ])
        .output()
        .is_ok_and(|output| output.status.success())
}

fn crop_snapshot_to_height(snapshot: PaneSnapshot, height: u16) -> PaneSnapshot {
    if height == 0 || snapshot.rows <= height || snapshot.cols == 0 {
        return snapshot;
    }
    let first_row = snapshot.rows - height;
    let first_cell = usize::from(first_row) * usize::from(snapshot.cols);
    let cursor_in_view = snapshot.cursor.row >= first_row;
    let cursor = PaneCursor::new(
        snapshot.cursor.row.saturating_sub(first_row),
        snapshot.cursor.col,
        snapshot.cursor.visible && cursor_in_view,
        snapshot.cursor.style,
    );
    PaneSnapshot {
        cols: snapshot.cols,
        rows: height,
        cells: snapshot.cells[first_cell..].to_vec(),
        cursor,
        revision: snapshot.revision,
    }
}

fn capture_history(target: &str) -> Option<Vec<String>> {
    let output = Command::new("rmux")
        .args(["capture-pane", "-p", "-t", target, "-S", "-500000"])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    Some(
        String::from_utf8_lossy(&output.stdout)
            .lines()
            .map(str::to_owned)
            .collect(),
    )
}

fn create_session(kind: &str, name: &str) -> Result<String> {
    let output = Command::new("agk")
        .arg("new")
        .arg(kind)
        .arg(name)
        .output()
        .context("run `agk new`")?;
    if !output.status.success() {
        let error = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        anyhow::bail!(if error.is_empty() {
            format!("agk exited with {}", output.status)
        } else {
            error
        });
    }
    let message = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    Ok(if message.is_empty() {
        format!("Created {name}")
    } else {
        message
    })
}

fn open_agent(id: &str, session: &str) -> Result<String> {
    let mut command = Command::new("agk");
    command.args(["specialist", "start", id]);
    if !session.is_empty() {
        command.args(["--session", session]);
    }
    let output = command.output().context("run `agk specialist start`")?;
    if !output.status.success() {
        anyhow::bail!(command_error(&output));
    }
    let message = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    Ok(if message.is_empty() {
        format!("Opened {id}")
    } else {
        message
    })
}

fn resume_conversation(target: &SessionTarget) -> Result<String> {
    let mut command = Command::new("agk");
    if target.managed {
        command.args(["restart", target.id.as_str()]);
    } else {
        let native = target
            .native_session
            .as_deref()
            .context("synced conversation has no Hermes session id")?;
        command.args([
            "new",
            "hermes",
            target.name.as_str(),
            "--native-session",
            native,
        ]);
        if !target.cwd.is_empty() {
            command.args(["--cwd", target.cwd.as_str()]);
        }
        if let Some(profile) = target.hermes_profile.as_deref() {
            command.args(["--profile", profile]);
        }
    }
    let output = command
        .output()
        .context("resume Hermes conversation through AGK")?;
    if !output.status.success() {
        anyhow::bail!(command_error(&output));
    }
    let message = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    Ok(if message.is_empty() {
        format!("Resumed {}", target.name)
    } else {
        message
    })
}

fn resolve_pending_session(
    app: &mut App,
    pending: &PendingSession,
    now: Instant,
) -> PendingResolution {
    let runtime = app
        .snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.name == pending.name);
    let registered = runtime.is_some();
    let ready = runtime.is_some_and(|runtime| !pending.enter_terminal || runtime.live);
    if ready && app.select_session_by_name(&pending.name) {
        return PendingResolution::Ready {
            name: pending.name.clone(),
            enter_terminal: pending.enter_terminal,
        };
    }
    if now.duration_since(pending.started_at) >= SESSION_START_TIMEOUT {
        if registered {
            app.select_session_by_name(&pending.name);
        }
        return PendingResolution::TimedOut {
            name: pending.name.clone(),
            registered,
        };
    }
    PendingResolution::Waiting
}

fn rename_session(target: &SessionTarget, name: &str) -> Result<String> {
    let mut command = if target.managed {
        let mut command = Command::new("agk");
        command.args(["rename", &target.name, name]);
        command
    } else {
        let mut command = Command::new("rmux");
        command.args(["rename-session", "-t", &target.rmux_session, name]);
        command
    };
    let output = command.output().context("rename selected session")?;
    if !output.status.success() {
        anyhow::bail!(command_error(&output));
    }
    Ok(format!("Renamed {} to {name}", target.name))
}

fn close_session(target: &SessionTarget) -> Result<String> {
    if !target.managed && !rmux_session_exists(&target.rmux_session) {
        return Ok(format!("{} was already closed", target.name));
    }
    let mut command = if target.managed {
        let mut command = Command::new("agk");
        command.args(["close", "--yes", &target.name]);
        command
    } else {
        let mut command = Command::new("rmux");
        command.args(["kill-session", "-t", &target.rmux_session]);
        command
    };
    let output = command.output().context("close selected session")?;
    if !output.status.success() {
        anyhow::bail!(command_error(&output));
    }
    if rmux_session_exists(&target.rmux_session) {
        anyhow::bail!("RMUX session {} is still running", target.rmux_session);
    }
    Ok(format!("Closed {}", target.name))
}

fn rmux_session_exists(name: &str) -> bool {
    Command::new("rmux")
        .args(["has-session", "-t", name])
        .output()
        .is_ok_and(|output| output.status.success())
}

fn command_error(output: &std::process::Output) -> String {
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    if !stderr.is_empty() {
        stderr
    } else if !stdout.is_empty() {
        stdout
    } else {
        format!("command exited with {}", output.status)
    }
}

async fn send_terminal_event(rmux: &Rmux, app: &App, cache: &mut PreviewCache, event: Event) {
    let Some(runtime) = app.current_session() else {
        return;
    };
    let Some(pane) = cached_primary_pane(rmux, &runtime.rmux_session, cache).await else {
        return;
    };
    let result = match event {
        Event::Paste(text) => paste::send(&pane, &text).await,
        Event::Key(key) if accepts_key(&key) => {
            if key.code == KeyCode::Enter
                && key
                    .modifiers
                    .intersects(KeyModifiers::SHIFT | KeyModifiers::ALT)
            {
                // Match the supported agent CLIs: a trailing backslash plus Enter
                // inserts a newline without submitting the prompt.
                match pane.send_text("\\").await {
                    Ok(_) => pane.send_key("Enter").await.map(|_| ()),
                    Err(error) => Err(error),
                }
            } else if let KeyCode::Char(character) = key.code
                && !key
                    .modifiers
                    .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT)
            {
                pane.send_text(character.to_string()).await.map(|_| ())
            } else if let Some(token) = rmux_key_token(key) {
                pane.send_key(token).await.map(|_| ())
            } else {
                return;
            }
        }
        Event::Mouse(_) => return,
        _ => return,
    };
    if result.is_err() {
        cache.invalidate_handle();
    }
}

async fn primary_pane(rmux: &Rmux, session_name: &str) -> Option<Pane> {
    rmux.find_panes()
        .session(session_name)
        .all()
        .await
        .ok()?
        .into_iter()
        .next()
        .map(|discovered| discovered.pane)
}

fn rmux_key_token(key: KeyEvent) -> Option<String> {
    let shift = key.modifiers.contains(KeyModifiers::SHIFT);
    let alt = key.modifiers.contains(KeyModifiers::ALT);
    let control = key.modifiers.contains(KeyModifiers::CONTROL);
    if matches!(key.code, KeyCode::Backspace) && (shift || alt || control) {
        return Some("C-w".into());
    }
    if matches!(key.code, KeyCode::Delete) && (shift || alt) {
        return Some("M-d".into());
    }
    if matches!(key.code, KeyCode::Left) && (alt || control) {
        return Some("M-b".into());
    }
    if matches!(key.code, KeyCode::Right) && (alt || control) {
        return Some("M-f".into());
    }
    let base = match key.code {
        // rmux's canonical token is `BSpace`; unknown names are sent as
        // literal text, which is why AGK previously typed "Backspace" into
        // the selected agent instead of deleting a character.
        KeyCode::Backspace => "BSpace".into(),
        KeyCode::Enter => "Enter".into(),
        KeyCode::Left => "Left".into(),
        KeyCode::Right => "Right".into(),
        KeyCode::Up => "Up".into(),
        KeyCode::Down => "Down".into(),
        KeyCode::Home => "Home".into(),
        KeyCode::End => "End".into(),
        KeyCode::PageUp => "PageUp".into(),
        KeyCode::PageDown => "PageDown".into(),
        KeyCode::Tab => "Tab".into(),
        KeyCode::BackTab => "BTab".into(),
        KeyCode::Delete => "Delete".into(),
        KeyCode::Insert => "IC".into(),
        KeyCode::F(number) => format!("F{number}"),
        KeyCode::Char(character) => character.to_string(),
        KeyCode::Null => "C-Space".into(),
        KeyCode::Esc => "Escape".into(),
        _ => return None,
    };
    if matches!(key.code, KeyCode::Null) {
        return Some(base);
    }
    let mut prefixes = Vec::new();
    if key.modifiers.contains(KeyModifiers::CONTROL) {
        prefixes.push("C");
    }
    if key.modifiers.contains(KeyModifiers::ALT) {
        prefixes.push("M");
    }
    if key.modifiers.contains(KeyModifiers::SHIFT)
        && !matches!(key.code, KeyCode::Char(_) | KeyCode::BackTab)
    {
        prefixes.push("S");
    }
    if prefixes.is_empty() {
        Some(base)
    } else {
        Some(format!("{}-{base}", prefixes.join("-")))
    }
}

fn current_rmux_session() -> Option<String> {
    resolve_current_rmux_session_with(
        |name| std::env::var(name).ok(),
        |pane| {
            let output = Command::new("rmux")
                .args(["display-message", "-p", "-t", pane, "#{session_name}"])
                .output()
                .ok()?;
            output
                .status
                .success()
                .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
        },
    )
}

fn resolve_current_rmux_session_with<E, D>(mut env_var: E, mut display_session: D) -> Option<String>
where
    E: FnMut(&str) -> Option<String>,
    D: FnMut(&str) -> Option<String>,
{
    fn nonempty(value: String) -> Option<String> {
        let value = value.trim();
        (!value.is_empty()).then(|| value.to_owned())
    }

    env_var("RMUX_PANE")
        .and_then(nonempty)
        .and_then(|pane| display_session(&pane))
        .and_then(nonempty)
        .or_else(|| env_var("RMUX_SESSION").and_then(nonempty))
        .or_else(|| env_var("TMUX_SESSION").and_then(nonempty))
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
struct MouseOutcome {
    preview_scrolled: bool,
    activate_session: bool,
}

fn handle_mouse(
    app: &mut App,
    mouse: MouseEvent,
    terminal_size: ratatui::layout::Size,
) -> MouseOutcome {
    let mut outcome = MouseOutcome::default();
    if !matches!(
        mouse.kind,
        MouseEventKind::ScrollUp | MouseEventKind::ScrollDown
    ) && !matches!(mouse.kind, MouseEventKind::Down(MouseButton::Left))
    {
        return outcome;
    }
    if let Some(focus) = ui::focus_at(app, terminal_size, mouse.column, mouse.row) {
        // The top navigation is a direct horizontal axis, never a focus stop.
        // Panel focus remains stable when the user merely clicks its chrome.
        if focus != Focus::Nav {
            app.focus = focus;
            outcome.activate_session = app.view == View::Sessions
                && focus == Focus::Detail
                && matches!(mouse.kind, MouseEventKind::Down(MouseButton::Left));
        }
    }
    match mouse.kind {
        MouseEventKind::ScrollUp if app.focus == Focus::List => {
            for _ in 0..3 {
                app.select_previous();
            }
        }
        MouseEventKind::ScrollDown if app.focus == Focus::List => {
            for _ in 0..3 {
                app.select_next();
            }
        }
        MouseEventKind::ScrollUp if app.view == View::Sessions => {
            app.scroll_preview_up(3);
            outcome.preview_scrolled = true;
        }
        MouseEventKind::ScrollDown if app.view == View::Sessions => {
            app.scroll_preview_down(3);
            outcome.preview_scrolled = true;
        }
        MouseEventKind::ScrollUp => app.detail_scroll = app.detail_scroll.saturating_sub(3),
        MouseEventKind::ScrollDown => app.detail_scroll = app.detail_scroll.saturating_add(3),
        _ => {}
    }
    outcome
}

fn accepts_key(key: &KeyEvent) -> bool {
    matches!(key.kind, KeyEventKind::Press | KeyEventKind::Repeat)
}

fn terminal_returns_to_control(key: &KeyEvent) -> bool {
    key.code == KeyCode::Char('g') && key.modifiers.contains(KeyModifiers::CONTROL)
}

fn terminal_sidebar_control_key(key: &KeyEvent) -> bool {
    (key.modifiers.is_empty() && matches!(key.code, KeyCode::Char('n' | 'x' | 'r' | 'q')))
        || (key.modifiers == KeyModifiers::CONTROL && key.code == KeyCode::Char('r'))
}

fn enter_selected_terminal(app: &mut App) -> bool {
    if app.selected_is_current_rmux_session() {
        app.status =
            Some("This session is running AGK; recursive terminal mode is disabled".into());
        return false;
    }
    if !app.current_session().is_some_and(|runtime| runtime.live) {
        app.status = Some("This provider terminal is not live; press R to restart it".into());
        return false;
    }
    app.mode = Mode::Terminal;
    app.view = View::Sessions;
    app.focus = Focus::Detail;
    app.expanded = false;
    app.scroll_preview_live();
    true
}

fn register_tab(last_tab_at: &mut Option<Instant>, now: Instant) -> bool {
    let double =
        last_tab_at.is_some_and(|previous| now.duration_since(previous) <= DOUBLE_TAB_TIME);
    *last_tab_at = (!double).then_some(now);
    double
}

/// Returns true when the provider pane owns input after the transition.
fn session_tab(app: &mut App, detail_available: bool, double: bool) -> bool {
    if double && detail_available {
        app.expanded = true;
        app.focus = Focus::Detail;
        return true;
    }
    if app.expanded {
        app.expanded = false;
        app.focus = Focus::List;
        return false;
    }
    app.focus = if app.focus == Focus::List && detail_available {
        Focus::Detail
    } else {
        Focus::List
    };
    app.focus == Focus::Detail
}

fn terminal_sidebar_key(app: &mut App, key: &KeyEvent) -> bool {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            app.select_previous();
            true
        }
        KeyCode::Down | KeyCode::Char('j') => {
            app.select_next();
            true
        }
        KeyCode::Enter => {
            app.expanded = false;
            app.focus = Focus::Detail;
            true
        }
        _ => false,
    }
}

/// Left/right stays the global top-menu axis while the session sidebar owns
/// focus. Provider input keeps both arrows untouched when the live pane owns
/// focus, so shell and editor cursor movement remains native.
fn terminal_top_nav_key(app: &mut App, key: &KeyEvent) -> bool {
    match key.code {
        KeyCode::Left => app.previous_view(),
        KeyCode::Right => app.next_view(),
        _ => return false,
    }
    app.mode = Mode::Control;
    app.expanded = false;
    true
}

fn terminal_scroll_key(app: &mut App, key: &KeyEvent) -> bool {
    let modified_vertical = key
        .modifiers
        .intersects(KeyModifiers::ALT | KeyModifiers::SHIFT)
        && !key.modifiers.contains(KeyModifiers::CONTROL);
    match key.code {
        KeyCode::PageUp => app.scroll_preview_up(app.preview_height.max(8)),
        KeyCode::PageDown => app.scroll_preview_down(app.preview_height.max(8)),
        KeyCode::Home if key.modifiers.is_empty() => app.scroll_preview_home(),
        KeyCode::End if key.modifiers.is_empty() => app.scroll_preview_live(),
        KeyCode::Up if modified_vertical => app.scroll_preview_up(3),
        KeyCode::Down if modified_vertical => app.scroll_preview_down(3),
        _ => return false,
    }
    true
}

fn detail_available(app: &App) -> bool {
    match app.view {
        View::Sessions => app.current_session().is_some(),
        View::Projects => app.current_object().is_some(),
        View::Agents => app.current_agent().is_some(),
        View::Os => app.current_os().is_some(),
        View::Mcp => app.current_mcp().is_some(),
        View::Skills => app.current_skill().is_some(),
        View::Rules => app.current_rule().is_some(),
        View::Settings => true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{RegistrySnapshot, RuntimeRecord};
    use rmux_sdk::{PaneCell, PaneGlyph};

    fn runtime(name: &str, live: bool) -> RuntimeRecord {
        RuntimeRecord {
            id: format!("runtime-{name}"),
            name: name.into(),
            kind: "hermes".into(),
            environment: "operator".into(),
            client: None,
            project: None,
            mission: None,
            native_session: None,
            hermes_profile: None,
            rmux_session: name.into(),
            cwd: "/home/operator".into(),
            status: if live { "running" } else { "interrupted" }.into(),
            created_at: 1.0,
            last_activity: 2.0,
            tokens: 0,
            model_usage: Vec::new(),
            managed: true,
            live,
        }
    }

    #[test]
    fn preview_refreshes_only_when_the_pane_is_rendered() {
        let mut app = App::new(Preferences::default());
        app.preview_width = 80;
        app.preview_height = 20;
        app.focus = Focus::List;
        app.preferences.split_preview = false;
        assert!(!preview_is_visible(&app));

        app.focus = Focus::Detail;
        assert!(preview_is_visible(&app));
        app.mode = Mode::Terminal;
        assert!(preview_is_visible(&app));
        app.view = View::Projects;
        assert!(!preview_is_visible(&app));
    }

    #[test]
    fn terminal_key_mapping_forwards_navigation_function_and_modifiers() {
        let cases = [
            (
                KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE),
                "BSpace",
            ),
            (KeyEvent::new(KeyCode::Insert, KeyModifiers::NONE), "IC"),
            (KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE), "Escape"),
            (KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE), "Tab"),
            (KeyEvent::new(KeyCode::BackTab, KeyModifiers::SHIFT), "BTab"),
            (KeyEvent::new(KeyCode::PageUp, KeyModifiers::NONE), "PageUp"),
            (KeyEvent::new(KeyCode::F(11), KeyModifiers::NONE), "F11"),
            (
                KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL),
                "C-c",
            ),
            (KeyEvent::new(KeyCode::Char('x'), KeyModifiers::ALT), "M-x"),
            (
                KeyEvent::new(
                    KeyCode::Char('x'),
                    KeyModifiers::CONTROL | KeyModifiers::ALT,
                ),
                "C-M-x",
            ),
            (KeyEvent::new(KeyCode::Up, KeyModifiers::SHIFT), "S-Up"),
            (
                KeyEvent::new(KeyCode::Backspace, KeyModifiers::CONTROL),
                "C-w",
            ),
            (KeyEvent::new(KeyCode::Left, KeyModifiers::ALT), "M-b"),
            (
                KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL),
                "C-r",
            ),
        ];
        for (key, expected) in cases {
            assert_eq!(rmux_key_token(key).as_deref(), Some(expected));
        }
    }

    #[test]
    fn terminal_escape_keys_do_not_capture_provider_control_r() {
        assert!(!terminal_returns_to_control(&KeyEvent::new(
            KeyCode::Tab,
            KeyModifiers::NONE,
        )));
        assert!(terminal_returns_to_control(&KeyEvent::new(
            KeyCode::Char('g'),
            KeyModifiers::CONTROL,
        )));
        assert!(!terminal_returns_to_control(&KeyEvent::new(
            KeyCode::Char('r'),
            KeyModifiers::CONTROL,
        )));
    }

    #[test]
    fn terminal_single_tab_only_alternates_panels_and_double_tab_expands() {
        let mut app = App::new(Preferences::default());
        app.mode = Mode::Terminal;
        app.focus = Focus::Detail;

        assert!(!session_tab(&mut app, true, false));
        assert_eq!(app.focus, Focus::List);
        assert!(!app.expanded);

        assert!(session_tab(&mut app, true, false));
        assert_eq!(app.focus, Focus::Detail);
        assert!(!app.expanded);

        assert!(session_tab(&mut app, true, true));
        assert_eq!(app.focus, Focus::Detail);
        assert!(app.expanded);

        assert!(!session_tab(&mut app, true, false));
        assert_eq!(app.focus, Focus::List);
        assert!(!app.expanded);
    }

    #[test]
    fn session_preview_focus_requests_immediate_provider_input() {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("live", true)],
            ..RegistrySnapshot::default()
        });
        app.focus = Focus::List;

        assert!(session_tab(&mut app, true, false));
        assert!(enter_selected_terminal(&mut app));
        assert_eq!(app.focus, Focus::Detail);
        assert_eq!(app.mode, Mode::Terminal);
    }

    #[test]
    fn clicking_the_session_pane_activates_input_without_a_nav_focus_stop() {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("live", true)],
            ..RegistrySnapshot::default()
        });
        let size = ratatui::layout::Size::new(90, 24);

        let pane = handle_mouse(
            &mut app,
            MouseEvent {
                kind: MouseEventKind::Down(MouseButton::Left),
                column: 50,
                row: 10,
                modifiers: KeyModifiers::NONE,
            },
            size,
        );
        assert_eq!(app.focus, Focus::Detail);
        assert!(pane.activate_session);

        app.focus = Focus::List;
        let nav = handle_mouse(
            &mut app,
            MouseEvent {
                kind: MouseEventKind::Down(MouseButton::Left),
                column: 2,
                row: 1,
                modifiers: KeyModifiers::NONE,
            },
            size,
        );
        assert_eq!(app.focus, Focus::List);
        assert!(!nav.activate_session);
    }

    #[test]
    fn only_two_rapid_consecutive_tabs_form_a_double_tab() {
        let started = Instant::now();
        let mut previous = None;
        assert!(!register_tab(&mut previous, started));
        assert!(register_tab(
            &mut previous,
            started + DOUBLE_TAB_TIME.saturating_sub(Duration::from_millis(1))
        ));
        assert!(previous.is_none());
        assert!(!register_tab(
            &mut previous,
            started + DOUBLE_TAB_TIME + Duration::from_millis(10)
        ));
        assert!(!register_tab(
            &mut previous,
            started + DOUBLE_TAB_TIME.saturating_mul(3)
        ));
    }

    #[test]
    fn terminal_sidebar_selects_a_session_then_returns_to_direct_input() {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("one", true), runtime("two", true)],
            ..RegistrySnapshot::default()
        });
        app.focus = Focus::List;

        assert!(terminal_sidebar_key(
            &mut app,
            &KeyEvent::new(KeyCode::Down, KeyModifiers::NONE)
        ));
        assert_eq!(app.selected_session_name(), Some("two"));
        assert!(terminal_sidebar_key(
            &mut app,
            &KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE)
        ));
        assert_eq!(app.focus, Focus::Detail);
        assert!(!app.expanded);
    }

    #[test]
    fn terminal_sidebar_routes_session_actions_out_of_provider_input() {
        for character in ['n', 'x', 'r', 'q'] {
            assert!(terminal_sidebar_control_key(&KeyEvent::new(
                KeyCode::Char(character),
                KeyModifiers::NONE,
            )));
        }
        assert!(terminal_sidebar_control_key(&KeyEvent::new(
            KeyCode::Char('r'),
            KeyModifiers::CONTROL,
        )));
        assert!(!terminal_sidebar_control_key(&KeyEvent::new(
            KeyCode::Char('a'),
            KeyModifiers::NONE,
        )));
    }

    #[test]
    fn terminal_sidebar_arrows_move_the_global_top_menu_without_a_middle_step() {
        let mut app = App::new(Preferences::default());
        app.mode = Mode::Terminal;
        app.view = View::Sessions;
        app.focus = Focus::List;

        assert!(terminal_top_nav_key(
            &mut app,
            &KeyEvent::new(KeyCode::Right, KeyModifiers::NONE)
        ));
        assert_eq!(app.mode, Mode::Control);
        assert_eq!(app.view, View::Projects);
        assert_eq!(app.focus, Focus::List);

        app.mode = Mode::Terminal;
        assert!(terminal_top_nav_key(
            &mut app,
            &KeyEvent::new(KeyCode::Left, KeyModifiers::NONE)
        ));
        assert_eq!(app.view, View::Sessions);
        assert_eq!(app.mode, Mode::Control);
    }

    #[test]
    fn terminal_history_keys_move_the_local_mirror_not_the_provider() {
        let mut app = App::new(Preferences::default());
        app.preview_height = 20;
        assert!(terminal_scroll_key(
            &mut app,
            &KeyEvent::new(KeyCode::PageUp, KeyModifiers::NONE)
        ));
        assert_eq!(app.preview_scroll, 20);
        assert!(terminal_scroll_key(
            &mut app,
            &KeyEvent::new(KeyCode::Down, KeyModifiers::ALT)
        ));
        assert_eq!(app.preview_scroll, 17);
        assert!(!terminal_scroll_key(
            &mut app,
            &KeyEvent::new(KeyCode::Down, KeyModifiers::NONE)
        ));
    }

    #[test]
    fn pending_creation_waits_for_a_live_runtime_then_selects_it_for_direct_open() {
        let mut app = App::new(Preferences::default());
        let started_at = Instant::now();
        let pending = PendingSession {
            name: "fresh-hermes".into(),
            started_at,
            enter_terminal: true,
        };

        assert_eq!(
            resolve_pending_session(&mut app, &pending, started_at),
            PendingResolution::Waiting
        );
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("fresh-hermes", false)],
            ..RegistrySnapshot::default()
        });
        assert_eq!(
            resolve_pending_session(&mut app, &pending, started_at + Duration::from_secs(1)),
            PendingResolution::Waiting
        );
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("fresh-hermes", true)],
            ..RegistrySnapshot::default()
        });
        assert_eq!(
            resolve_pending_session(&mut app, &pending, started_at + Duration::from_secs(2)),
            PendingResolution::Ready {
                name: "fresh-hermes".into(),
                enter_terminal: true,
            }
        );
        assert_eq!(app.selected_session_name(), Some("fresh-hermes"));
    }

    #[test]
    fn pending_creation_reports_a_provider_that_exits_during_startup() {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("dead-provider", false)],
            ..RegistrySnapshot::default()
        });
        let started_at = Instant::now();
        let pending = PendingSession {
            name: "dead-provider".into(),
            started_at,
            enter_terminal: true,
        };

        assert_eq!(
            resolve_pending_session(&mut app, &pending, started_at + SESSION_START_TIMEOUT),
            PendingResolution::TimedOut {
                name: "dead-provider".into(),
                registered: true,
            }
        );
    }

    #[test]
    fn media_and_lock_keys_are_ignored_safely() {
        assert_eq!(
            rmux_key_token(KeyEvent::new(KeyCode::CapsLock, KeyModifiers::NONE)),
            None
        );
    }

    #[test]
    fn current_session_resolution_uses_the_stable_rmux_pane_identity() {
        let mut queried = Vec::new();
        let resolved = resolve_current_rmux_session_with(
            |name| {
                queried.push(name.to_owned());
                match name {
                    "RMUX_PANE" => Some(" %42 ".into()),
                    "RMUX_SESSION" => Some("fallback".into()),
                    _ => None,
                }
            },
            |pane| {
                assert_eq!(pane, "%42");
                Some("operator-control\n".into())
            },
        );
        assert_eq!(resolved.as_deref(), Some("operator-control"));
        assert_eq!(queried, vec!["RMUX_PANE"]);
    }

    #[test]
    fn oversized_live_snapshot_keeps_the_tail_and_cursor() {
        let cells = ['a', 'b', 'c', 'd']
            .into_iter()
            .flat_map(|character| {
                [
                    PaneCell::new(PaneGlyph::new(character.to_string(), 1)),
                    PaneCell::blank(),
                ]
            })
            .collect();
        let snapshot = PaneSnapshot::new(2, 4, cells, PaneCursor::new(3, 1, true, 2))
            .unwrap()
            .with_revision(17);

        let cropped = crop_snapshot_to_height(snapshot, 2);

        assert_eq!((cropped.cols, cropped.rows), (2, 2));
        assert_eq!(cropped.cell(0, 0).map(PaneCell::text), Some("c"));
        assert_eq!(cropped.cell(1, 0).map(PaneCell::text), Some("d"));
        assert_eq!(cropped.cursor, PaneCursor::new(1, 1, true, 2));
        assert_eq!(cropped.revision, 17);
    }
}
