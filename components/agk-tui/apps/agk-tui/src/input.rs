use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

use crate::{
    model::{App, Focus, Overlay, SessionKind, SessionTarget, SettingsSection, View},
    theme::{CustomColors, RgbColor, Theme},
};

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Action {
    None,
    Quit,
    Reload,
    Refresh,
    PersistPreferences,
    EnterTerminal,
    InstallProvider { id: String },
    OpenAgent { id: String, session: String },
    ResumeConversation { target: SessionTarget },
    CreateSession { kind: SessionKind, name: String },
    RenameSession { target: SessionTarget, name: String },
    CloseSession { target: SessionTarget },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PaletteCommand {
    Open(View),
    OpenSettings(SettingsSection),
    NewSession,
    TogglePreview,
    Refresh,
    Quit,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PaletteItem {
    pub label: &'static str,
    pub hint: &'static str,
    pub command: PaletteCommand,
}

const PALETTE_ITEMS: [PaletteItem; 14] = [
    PaletteItem {
        label: "Open Sessions",
        hint: "1",
        command: PaletteCommand::Open(View::Sessions),
    },
    PaletteItem {
        label: "Open Projects & Missions",
        hint: "2",
        command: PaletteCommand::Open(View::Projects),
    },
    PaletteItem {
        label: "Open Agents",
        hint: "3",
        command: PaletteCommand::Open(View::Agents),
    },
    PaletteItem {
        label: "Open Agentik OS",
        hint: "4",
        command: PaletteCommand::Open(View::Os),
    },
    PaletteItem {
        label: "Open MCP servers",
        hint: "5",
        command: PaletteCommand::Open(View::Mcp),
    },
    PaletteItem {
        label: "Open Skills",
        hint: "6",
        command: PaletteCommand::Open(View::Skills),
    },
    PaletteItem {
        label: "Open Rules",
        hint: "7",
        command: PaletteCommand::Open(View::Rules),
    },
    PaletteItem {
        label: "Open Settings",
        hint: "8",
        command: PaletteCommand::Open(View::Settings),
    },
    PaletteItem {
        label: "Open System Settings",
        hint: "s",
        command: PaletteCommand::OpenSettings(SettingsSection::System),
    },
    PaletteItem {
        label: "Open Help",
        hint: "?",
        command: PaletteCommand::OpenSettings(SettingsSection::Help),
    },
    PaletteItem {
        label: "New session",
        hint: "n",
        command: PaletteCommand::NewSession,
    },
    PaletteItem {
        label: "Toggle live preview",
        hint: "v",
        command: PaletteCommand::TogglePreview,
    },
    PaletteItem {
        label: "Refresh registries",
        hint: "r",
        command: PaletteCommand::Refresh,
    },
    PaletteItem {
        label: "Detach AGK",
        hint: "q",
        command: PaletteCommand::Quit,
    },
];

pub fn palette_items(query: &str) -> Vec<PaletteItem> {
    let terms = query
        .split_whitespace()
        .map(str::to_ascii_lowercase)
        .collect::<Vec<_>>();
    PALETTE_ITEMS
        .iter()
        .copied()
        .filter(|item| {
            let haystack = format!("{} {}", item.label, item.hint).to_ascii_lowercase();
            terms.iter().all(|term| haystack.contains(term))
        })
        .collect()
}

#[cfg(test)]
fn handle_key(app: &mut App, key: KeyEvent, detail_available: bool) -> Action {
    handle_key_for_layout(app, key, detail_available, false)
}

pub fn handle_key_for_layout(
    app: &mut App,
    key: KeyEvent,
    detail_available: bool,
    compact: bool,
) -> Action {
    if key.modifiers == KeyModifiers::CONTROL && key.code == KeyCode::Char('r') {
        app.status = Some("Reloading AGK…".into());
        return Action::Reload;
    }

    if app.overlay.is_open() {
        return handle_overlay_key(app, key, compact);
    }

    if key.modifiers == KeyModifiers::CONTROL && key.code == KeyCode::Char('p') {
        app.overlay = Overlay::Palette {
            query: String::new(),
            selected: 0,
        };
        return Action::None;
    }
    let plain = !key.modifiers.intersects(
        KeyModifiers::CONTROL
            | KeyModifiers::ALT
            | KeyModifiers::SUPER
            | KeyModifiers::HYPER
            | KeyModifiers::META,
    );
    if !plain {
        return Action::None;
    }

    // The top menu is a global horizontal axis, not a separate keyboard
    // focus stop. A mouse click may still mark it focused, but the very next
    // content key acts immediately instead of requiring an activation step.
    if app.focus == Focus::Nav && matches!(key.code, KeyCode::Up | KeyCode::Down | KeyCode::Enter) {
        app.focus = Focus::List;
    }

    match key.code {
        KeyCode::Char('q') => Action::Quit,
        KeyCode::Char('1') if !compact && app.view == View::Sessions && app.focus != Focus::Nav => {
            new_session_name(app, SessionKind::Hermes)
        }
        KeyCode::Char('2') if !compact && app.view == View::Sessions && app.focus != Focus::Nav => {
            new_session_name(app, SessionKind::Codex)
        }
        KeyCode::Char('3') if !compact && app.view == View::Sessions && app.focus != Focus::Nav => {
            new_session_name(app, SessionKind::Claude)
        }
        KeyCode::Char('4') if !compact && app.view == View::Sessions && app.focus != Focus::Nav => {
            new_session_name(app, SessionKind::OpenCode)
        }
        KeyCode::Char('5') if !compact && app.view == View::Sessions && app.focus != Focus::Nav => {
            new_session_name(app, SessionKind::OpenRouter)
        }
        KeyCode::Char('1') => set_view(app, View::Sessions),
        KeyCode::Char('2') => set_view(app, View::Projects),
        KeyCode::Char('3') => set_view(app, View::Agents),
        KeyCode::Char('4') => set_view(app, View::Os),
        KeyCode::Char('5') => set_view(app, View::Mcp),
        KeyCode::Char('6') => set_view(app, View::Skills),
        KeyCode::Char('7') => set_view(app, View::Rules),
        KeyCode::Char('8') => set_view(app, View::Settings),
        KeyCode::Char('s') => open_settings(app, SettingsSection::System),
        KeyCode::Char(',') => set_view(app, View::Settings),
        KeyCode::Char('?') => open_settings(app, SettingsSection::Help),
        KeyCode::Char('/') => {
            app.overlay = Overlay::Search {
                value: app.query.clone(),
                original: app.query.clone(),
            };
            Action::None
        }
        KeyCode::Char('n') if app.view == View::Os && app.os_conversations.is_some() => {
            let context = app
                .os_conversations
                .as_ref()
                .expect("OS conversation context")
                .clone();
            app.overlay = Overlay::NewAgentConversation {
                agent_id: context.agent_id,
                runtime_prefix: context.runtime_prefix,
                value: String::new(),
            };
            Action::None
        }
        KeyCode::Char('n') if app.view == View::Agents && app.agent_conversations.is_some() => {
            let context = app
                .agent_conversations
                .as_ref()
                .expect("agent conversation context")
                .clone();
            app.overlay = Overlay::NewAgentConversation {
                agent_id: context.agent_id,
                runtime_prefix: context.runtime_prefix,
                value: String::new(),
            };
            Action::None
        }
        KeyCode::Char('n') => {
            app.overlay = Overlay::NewKind { selected: 0 };
            Action::None
        }
        KeyCode::Char('x') if app.view == View::Os && app.os_conversations.is_some() => {
            close_conversation_target(app, app.current_os_conversation_target())
        }
        KeyCode::Char('x') if app.view == View::Agents && app.agent_conversations.is_some() => {
            close_conversation_target(app, app.current_agent_conversation_target())
        }
        KeyCode::Char('x') if app.view == View::Sessions && app.focus != Focus::Nav => {
            close_selected_session(app)
        }
        KeyCode::Char('r') if app.view == View::Sessions && app.focus != Focus::Nav => {
            rename_selected_session(app)
        }
        KeyCode::Char('r') | KeyCode::F(5) => Action::Refresh,
        KeyCode::Tab => {
            app.tab(detail_available);
            Action::None
        }
        KeyCode::BackTab => {
            app.back_tab(detail_available);
            Action::None
        }
        KeyCode::Left => {
            app.previous_view();
            Action::None
        }
        KeyCode::Right => {
            app.next_view();
            Action::None
        }
        KeyCode::Char('h') if app.focus == Focus::Nav => {
            app.previous_view();
            Action::None
        }
        KeyCode::Char('l') if app.focus == Focus::Nav => {
            app.next_view();
            Action::None
        }
        KeyCode::Up | KeyCode::Char('k') if app.focus == Focus::List => {
            app.select_previous();
            Action::None
        }
        KeyCode::Down | KeyCode::Char('j') if app.focus == Focus::List => {
            app.select_next();
            Action::None
        }
        KeyCode::Up | KeyCode::Char('k') if app.focus == Focus::Detail => {
            if app.view == View::Sessions {
                app.scroll_preview_up(1);
            } else if app.view == View::Settings
                && app.settings_section() == SettingsSection::Appearance
            {
                app.preview_previous_theme();
            } else if app.view == View::Settings
                && app.settings_section() == SettingsSection::Providers
            {
                app.select_previous_provider();
            } else if app.view == View::Settings
                && app.settings_section() == SettingsSection::Runtime
            {
                return settings_left(app);
            } else {
                app.detail_scroll = app.detail_scroll.saturating_sub(1);
            }
            Action::None
        }
        KeyCode::Down | KeyCode::Char('j') if app.focus == Focus::Detail => {
            if app.view == View::Sessions {
                app.scroll_preview_down(1);
            } else if app.view == View::Settings
                && app.settings_section() == SettingsSection::Appearance
            {
                app.preview_next_theme();
            } else if app.view == View::Settings
                && app.settings_section() == SettingsSection::Providers
            {
                app.select_next_provider();
            } else if app.view == View::Settings
                && app.settings_section() == SettingsSection::Runtime
            {
                return settings_right(app);
            } else {
                app.detail_scroll = app.detail_scroll.saturating_add(1);
            }
            Action::None
        }
        KeyCode::PageUp if app.focus == Focus::Detail => {
            if app.view == View::Sessions {
                app.scroll_preview_up(app.preview_height.max(8));
            } else {
                app.detail_scroll = app.detail_scroll.saturating_sub(8);
            }
            Action::None
        }
        KeyCode::PageDown if app.focus == Focus::Detail => {
            if app.view == View::Sessions {
                app.scroll_preview_down(app.preview_height.max(8));
            } else {
                app.detail_scroll = app.detail_scroll.saturating_add(8);
            }
            Action::None
        }
        KeyCode::Home if app.focus == Focus::Detail => {
            if app.view == View::Sessions {
                app.scroll_preview_home();
            } else {
                app.detail_scroll = 0;
            }
            Action::None
        }
        KeyCode::End if app.view == View::Sessions && app.focus == Focus::Detail => {
            app.scroll_preview_live();
            Action::None
        }
        KeyCode::Char('g') if app.view == View::Sessions && app.focus == Focus::Detail => {
            app.scroll_preview_home();
            Action::None
        }
        KeyCode::Char('G') if app.view == View::Sessions && app.focus == Focus::Detail => {
            app.scroll_preview_live();
            Action::None
        }
        KeyCode::Char('v') if app.view == View::Sessions => toggle_preview(app),
        KeyCode::Char('h') if app.view == View::Settings && app.focus == Focus::Detail => {
            settings_left(app)
        }
        KeyCode::Char('l') if app.view == View::Settings && app.focus == Focus::Detail => {
            settings_right(app)
        }
        KeyCode::Char('e')
            if app.view == View::Settings
                && app.focus == Focus::Detail
                && app.settings_section() == SettingsSection::Appearance
                && app.theme == Theme::Custom =>
        {
            open_custom_theme_editor(app)
        }
        KeyCode::Char(' ') if app.view == View::Settings && app.focus == Focus::Detail => {
            activate_settings(app)
        }
        KeyCode::Enter if app.view == View::Settings && app.focus == Focus::List => {
            app.focus = Focus::Detail;
            Action::None
        }
        KeyCode::Enter if app.view == View::Settings => activate_settings(app),
        KeyCode::Enter if app.view == View::Sessions => {
            open_conversation_target(app, app.current_session().map(SessionTarget::from))
        }
        KeyCode::Enter if app.view == View::Agents => {
            if app.agent_conversations.is_none() {
                if app.enter_agent_conversations() {
                    app.status = Some(
                        "Agent conversations · Enter resumes · n creates · Esc returns".into(),
                    );
                } else {
                    app.status = Some("No agent selected".into());
                }
                Action::None
            } else {
                open_conversation_target(app, app.current_agent_conversation_target())
            }
        }
        KeyCode::Enter if app.view == View::Os => {
            if app.os_conversations.is_none() {
                if app.enter_os_conversations() {
                    app.status =
                        Some("OS conversations · Enter open · n new · x delete · Esc back".into());
                } else {
                    app.status = Some("No responsible catalog agent is assigned".into());
                }
                Action::None
            } else if let Some(runtime) = app.current_os_conversation() {
                open_conversation_target(app, Some(SessionTarget::from(runtime)))
            } else {
                app.status = Some("No conversation yet · press n to create one".into());
                Action::None
            }
        }
        KeyCode::Enter => {
            app.focus = Focus::Detail;
            Action::None
        }
        KeyCode::Esc if app.view == View::Os && app.os_conversations.is_some() => {
            app.leave_os_conversations();
            app.status = Some("Returned to OS registry".into());
            Action::None
        }
        KeyCode::Esc if app.view == View::Agents && app.agent_conversations.is_some() => {
            app.leave_agent_conversations();
            app.status = Some("Returned to agent registry".into());
            Action::None
        }
        KeyCode::Esc => {
            if app.view == View::Settings
                && app.focus == Focus::Detail
                && app.settings_section() == SettingsSection::Appearance
            {
                app.cancel_theme_preview();
                app.status = Some("Theme preview reverted".into());
                return Action::None;
            }
            if app.expanded {
                app.expanded = false;
            } else if !app.query.is_empty() {
                app.query.clear();
                app.selected = 0;
            } else {
                app.focus = Focus::List;
            }
            Action::None
        }
        _ => Action::None,
    }
}

pub fn handle_paste(app: &mut App, text: &str) -> Action {
    match &mut app.overlay {
        Overlay::Search { value, .. } => {
            value.extend(text.chars().filter(|character| !character.is_control()));
            app.query.clone_from(value);
            app.selected = 0;
            app.scroll_preview_live();
        }
        Overlay::Palette { query, selected } => {
            query.extend(text.chars().filter(|character| !character.is_control()));
            *selected = 0;
        }
        Overlay::NewName { value, .. }
        | Overlay::NewAgentConversation { value, .. }
        | Overlay::RenameSession { value, .. } => {
            value.extend(
                text.chars()
                    .filter(|character| character.is_ascii_alphanumeric() || *character == '-')
                    .map(|character| character.to_ascii_lowercase())
                    .take(80usize.saturating_sub(value.len())),
            );
        }
        Overlay::CustomTheme {
            working,
            selected,
            value,
            fresh,
            ..
        } => {
            let pasted = text
                .trim()
                .chars()
                .filter(|character| *character == '#' || character.is_ascii_hexdigit())
                .take(7)
                .collect::<String>();
            if !pasted.is_empty() {
                *value = pasted;
                *fresh = false;
                if let Some(color) = RgbColor::from_hex(value) {
                    working.set(*selected, color);
                    app.preferences.custom_colors = *working;
                }
            }
        }
        Overlay::NewKind { .. } | Overlay::None => {}
    }
    Action::None
}

fn new_session_name(app: &mut App, kind: SessionKind) -> Action {
    app.overlay = Overlay::NewName {
        kind,
        value: String::new(),
    };
    Action::None
}

fn close_selected_session(app: &mut App) -> Action {
    close_conversation_target(app, app.current_session_target())
}

fn open_conversation_target(app: &mut App, target: Option<SessionTarget>) -> Action {
    let Some(target) = target else {
        app.status = Some("No conversation selected".into());
        return Action::None;
    };
    let live = app
        .snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.id == target.id)
        .is_some_and(|runtime| runtime.live);
    if live {
        if app.select_session_by_name(&target.name) {
            return Action::EnterTerminal;
        }
        app.status = Some("Conversation is no longer available".into());
        return Action::None;
    }
    if target.native_session.is_some() {
        app.set_view(View::Sessions);
        app.select_session_by_name(&target.name);
        return Action::ResumeConversation { target };
    }
    app.status = Some("This terminal is offline and has no resumable provider session".into());
    Action::None
}

fn close_conversation_target(app: &mut App, target: Option<SessionTarget>) -> Action {
    let Some(target) = target else {
        app.status = Some("No conversation selected".into());
        return Action::None;
    };
    if !target.managed {
        app.status = Some(
            "Synced Hermes history is preserved; resume it or archive it from Hermes Sessions"
                .into(),
        );
        return Action::None;
    }
    if app.current_rmux_session.as_deref() == Some(target.rmux_session.as_str()) {
        app.status = Some("AGK cannot close the conversation running this interface".into());
        return Action::None;
    }
    Action::CloseSession { target }
}

fn rename_selected_session(app: &mut App) -> Action {
    let Some(target) = app.current_session_target() else {
        app.status = Some("No session selected".into());
        return Action::None;
    };
    app.overlay = Overlay::RenameSession {
        value: target.name.clone(),
        target,
    };
    Action::None
}

fn valid_session_name(name: &str) -> bool {
    (3..=80).contains(&name.len())
        && name
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
        && name
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
}

fn handle_overlay_key(app: &mut App, key: KeyEvent, compact: bool) -> Action {
    let overlay = std::mem::replace(&mut app.overlay, Overlay::None);
    match overlay {
        Overlay::Search {
            mut value,
            original,
        } => match key.code {
            KeyCode::Esc => {
                app.query = original;
                app.selected = 0;
                app.scroll_preview_live();
                Action::None
            }
            KeyCode::Enter => {
                app.query = value;
                app.selected = 0;
                app.scroll_preview_live();
                Action::None
            }
            KeyCode::Backspace => {
                value.pop();
                app.query.clone_from(&value);
                app.selected = 0;
                app.scroll_preview_live();
                app.overlay = Overlay::Search { value, original };
                Action::None
            }
            KeyCode::Char(character) if printable(key.modifiers) => {
                value.push(character);
                app.query.clone_from(&value);
                app.selected = 0;
                app.scroll_preview_live();
                app.overlay = Overlay::Search { value, original };
                Action::None
            }
            _ => {
                app.overlay = Overlay::Search { value, original };
                Action::None
            }
        },
        Overlay::Palette {
            mut query,
            mut selected,
        } => match key.code {
            KeyCode::Esc => Action::None,
            KeyCode::Up => {
                selected = selected.saturating_sub(1);
                app.overlay = Overlay::Palette { query, selected };
                Action::None
            }
            KeyCode::Down => {
                selected = (selected + 1).min(palette_items(&query).len().saturating_sub(1));
                app.overlay = Overlay::Palette { query, selected };
                Action::None
            }
            KeyCode::Backspace => {
                query.pop();
                selected = selected.min(palette_items(&query).len().saturating_sub(1));
                app.overlay = Overlay::Palette { query, selected };
                Action::None
            }
            KeyCode::Char(character) if printable(key.modifiers) => {
                query.push(character);
                selected = 0;
                app.overlay = Overlay::Palette { query, selected };
                Action::None
            }
            KeyCode::Enter => palette_items(&query)
                .get(selected)
                .map(|item| execute_palette(app, item.command))
                .unwrap_or(Action::None),
            _ => {
                app.overlay = Overlay::Palette { query, selected };
                Action::None
            }
        },
        Overlay::NewKind { mut selected } => match key.code {
            KeyCode::Esc => Action::None,
            KeyCode::Char(choice @ '1'..='6') if !compact && printable(key.modifiers) => {
                let index = choice as usize - '1' as usize;
                app.overlay = Overlay::NewName {
                    kind: SessionKind::ALL[index],
                    value: String::new(),
                };
                Action::None
            }
            KeyCode::Up => {
                selected = selected.saturating_sub(1);
                app.overlay = Overlay::NewKind { selected };
                Action::None
            }
            KeyCode::Down => {
                selected = (selected + 1).min(SessionKind::ALL.len() - 1);
                app.overlay = Overlay::NewKind { selected };
                Action::None
            }
            KeyCode::Enter => {
                app.overlay = Overlay::NewName {
                    kind: SessionKind::ALL[selected],
                    value: String::new(),
                };
                Action::None
            }
            _ => {
                app.overlay = Overlay::NewKind { selected };
                Action::None
            }
        },
        Overlay::NewName { kind, mut value } => match key.code {
            KeyCode::Esc => Action::None,
            KeyCode::Backspace => {
                value.pop();
                app.overlay = Overlay::NewName { kind, value };
                Action::None
            }
            KeyCode::Char(character)
                if printable(key.modifiers)
                    && (character.is_ascii_alphanumeric() || character == '-')
                    && value.len() < 80 =>
            {
                value.push(character.to_ascii_lowercase());
                app.overlay = Overlay::NewName { kind, value };
                Action::None
            }
            KeyCode::Enter if valid_session_name(&value) => {
                Action::CreateSession { kind, name: value }
            }
            KeyCode::Enter => {
                app.status =
                    Some("Name must contain 3–80 lowercase letters, numbers or hyphens".into());
                app.overlay = Overlay::NewName { kind, value };
                Action::None
            }
            _ => {
                app.overlay = Overlay::NewName { kind, value };
                Action::None
            }
        },
        Overlay::NewAgentConversation {
            agent_id,
            runtime_prefix,
            mut value,
        } => match key.code {
            KeyCode::Esc => Action::None,
            KeyCode::Backspace => {
                value.pop();
                app.overlay = Overlay::NewAgentConversation {
                    agent_id,
                    runtime_prefix,
                    value,
                };
                Action::None
            }
            KeyCode::Char(character)
                if printable(key.modifiers)
                    && (character.is_ascii_alphanumeric() || character == '-')
                    && value.len() < 40 =>
            {
                value.push(character.to_ascii_lowercase());
                app.overlay = Overlay::NewAgentConversation {
                    agent_id,
                    runtime_prefix,
                    value,
                };
                Action::None
            }
            KeyCode::Enter => {
                let session = format!("{runtime_prefix}-{value}");
                if value.len() >= 3 && valid_session_name(&session) {
                    Action::OpenAgent {
                        id: agent_id,
                        session,
                    }
                } else {
                    app.status = Some(
                        "Conversation name must be 3+ lowercase letters, numbers or hyphens".into(),
                    );
                    app.overlay = Overlay::NewAgentConversation {
                        agent_id,
                        runtime_prefix,
                        value,
                    };
                    Action::None
                }
            }
            _ => {
                app.overlay = Overlay::NewAgentConversation {
                    agent_id,
                    runtime_prefix,
                    value,
                };
                Action::None
            }
        },
        Overlay::RenameSession { target, mut value } => match key.code {
            KeyCode::Esc => Action::None,
            KeyCode::Backspace => {
                value.pop();
                app.overlay = Overlay::RenameSession { target, value };
                Action::None
            }
            KeyCode::Char(character)
                if printable(key.modifiers)
                    && (character.is_ascii_alphanumeric() || character == '-')
                    && value.len() < 80 =>
            {
                value.push(character.to_ascii_lowercase());
                app.overlay = Overlay::RenameSession { target, value };
                Action::None
            }
            KeyCode::Enter if valid_session_name(&value) && value != target.name => {
                Action::RenameSession {
                    target,
                    name: value,
                }
            }
            _ => {
                app.overlay = Overlay::RenameSession { target, value };
                Action::None
            }
        },
        Overlay::CustomTheme {
            original,
            mut working,
            mut selected,
            mut value,
            mut fresh,
        } => match key.code {
            KeyCode::Esc => {
                app.preferences.custom_colors = original;
                Action::None
            }
            KeyCode::Up | KeyCode::Down => {
                let Some(color) = RgbColor::from_hex(&value) else {
                    app.status = Some("Custom colors use #RRGGBB".into());
                    app.overlay = Overlay::CustomTheme {
                        original,
                        working,
                        selected,
                        value,
                        fresh,
                    };
                    return Action::None;
                };
                working.set(selected, color);
                selected = if key.code == KeyCode::Up {
                    (selected + CustomColors::LEN - 1) % CustomColors::LEN
                } else {
                    (selected + 1) % CustomColors::LEN
                };
                value = working.get(selected).hex();
                fresh = true;
                app.preferences.custom_colors = working;
                app.overlay = Overlay::CustomTheme {
                    original,
                    working,
                    selected,
                    value,
                    fresh,
                };
                Action::None
            }
            KeyCode::Backspace => {
                if fresh {
                    value.clear();
                    fresh = false;
                } else {
                    value.pop();
                }
                app.overlay = Overlay::CustomTheme {
                    original,
                    working,
                    selected,
                    value,
                    fresh,
                };
                Action::None
            }
            KeyCode::Char(character)
                if printable(key.modifiers)
                    && (character == '#' || character.is_ascii_hexdigit()) =>
            {
                if fresh {
                    value.clear();
                    fresh = false;
                }
                if value.len() < 7 {
                    value.push(character.to_ascii_uppercase());
                }
                if let Some(color) = RgbColor::from_hex(&value) {
                    working.set(selected, color);
                    app.preferences.custom_colors = working;
                }
                app.overlay = Overlay::CustomTheme {
                    original,
                    working,
                    selected,
                    value,
                    fresh,
                };
                Action::None
            }
            KeyCode::Enter => {
                let Some(color) = RgbColor::from_hex(&value) else {
                    app.status = Some("Custom colors use #RRGGBB".into());
                    app.overlay = Overlay::CustomTheme {
                        original,
                        working,
                        selected,
                        value,
                        fresh,
                    };
                    return Action::None;
                };
                working.set(selected, color);
                app.preferences.custom_colors = working;
                app.theme = Theme::Custom;
                app.commit_theme();
                Action::PersistPreferences
            }
            _ => {
                app.overlay = Overlay::CustomTheme {
                    original,
                    working,
                    selected,
                    value,
                    fresh,
                };
                Action::None
            }
        },
        Overlay::None => Action::None,
    }
}

fn execute_palette(app: &mut App, command: PaletteCommand) -> Action {
    match command {
        PaletteCommand::Open(view) => set_view(app, view),
        PaletteCommand::OpenSettings(section) => open_settings(app, section),
        PaletteCommand::NewSession => {
            app.overlay = Overlay::NewKind { selected: 0 };
            Action::None
        }
        PaletteCommand::TogglePreview => toggle_preview(app),
        PaletteCommand::Refresh => Action::Refresh,
        PaletteCommand::Quit => Action::Quit,
    }
}

fn set_view(app: &mut App, view: View) -> Action {
    app.set_view(view);
    Action::None
}

fn open_settings(app: &mut App, section: SettingsSection) -> Action {
    app.set_view(View::Settings);
    app.settings_section = SettingsSection::ALL
        .iter()
        .position(|candidate| *candidate == section)
        .unwrap_or_default();
    app.focus = Focus::List;
    Action::None
}

fn toggle_preview(app: &mut App) -> Action {
    app.preferences.split_preview = !app.preferences.split_preview;
    app.status = Some(
        if app.preferences.split_preview {
            "Live preview enabled"
        } else {
            "Live preview hidden"
        }
        .into(),
    );
    Action::PersistPreferences
}

fn activate_settings(app: &mut App) -> Action {
    match app.settings_section() {
        SettingsSection::Appearance => {
            app.commit_theme();
            Action::PersistPreferences
        }
        SettingsSection::Providers => {
            app.current_provider()
                .map_or(Action::None, |provider| Action::InstallProvider {
                    id: provider.id.clone(),
                })
        }
        SettingsSection::Sessions => toggle_preview(app),
        SettingsSection::Runtime => Action::Refresh,
        SettingsSection::System => Action::Refresh,
        SettingsSection::Help => Action::None,
        SettingsSection::About => Action::None,
    }
}

fn settings_left(app: &mut App) -> Action {
    match app.settings_section() {
        SettingsSection::Appearance => {
            app.preview_previous_theme();
            Action::None
        }
        SettingsSection::Providers => {
            app.select_previous_provider();
            Action::None
        }
        SettingsSection::Runtime => {
            cycle_refresh(app, false);
            Action::PersistPreferences
        }
        _ => Action::None,
    }
}

fn settings_right(app: &mut App) -> Action {
    match app.settings_section() {
        SettingsSection::Appearance => {
            app.preview_next_theme();
            Action::None
        }
        SettingsSection::Providers => {
            app.select_next_provider();
            Action::None
        }
        SettingsSection::Runtime => {
            cycle_refresh(app, true);
            Action::PersistPreferences
        }
        _ => Action::None,
    }
}

fn open_custom_theme_editor(app: &mut App) -> Action {
    let colors = app.preferences.custom_colors;
    app.overlay = Overlay::CustomTheme {
        original: colors,
        working: colors,
        selected: 0,
        value: colors.get(0).hex(),
        fresh: true,
    };
    Action::None
}

fn cycle_refresh(app: &mut App, forwards: bool) {
    const VALUES: [u64; 4] = [250, 500, 1_000, 2_000];
    let index = VALUES
        .iter()
        .position(|value| *value == app.preferences.refresh_ms)
        .unwrap_or(2);
    app.preferences.refresh_ms = if forwards {
        VALUES[(index + 1) % VALUES.len()]
    } else {
        VALUES[(index + VALUES.len() - 1) % VALUES.len()]
    };
    app.status = Some(format!("Refresh every {} ms", app.preferences.refresh_ms));
}

fn printable(modifiers: KeyModifiers) -> bool {
    !modifiers.intersects(
        KeyModifiers::CONTROL
            | KeyModifiers::ALT
            | KeyModifiers::SUPER
            | KeyModifiers::HYPER
            | KeyModifiers::META,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{AgentRecord, OsPackage, ProviderRecord, RegistrySnapshot, RuntimeRecord};
    use crate::theme::Preferences;

    fn app() -> App {
        App::new(Preferences::default())
    }

    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }

    fn add_session(app: &mut App) {
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![RuntimeRecord {
                id: "runtime-moon".into(),
                name: "moon".into(),
                kind: "hermes".into(),
                environment: "mission".into(),
                client: None,
                project: None,
                mission: None,
                native_session: None,
                hermes_profile: None,
                rmux_session: "mission-moon-hermes".into(),
                cwd: "/work".into(),
                status: "active".into(),
                created_at: 1.0,
                last_activity: 2.0,
                tokens: 0,
                model_usage: Vec::new(),
                managed: true,
                live: true,
            }],
            ..RegistrySnapshot::default()
        });
    }

    fn add_os_agent(app: &mut App) {
        app.set_snapshot(RegistrySnapshot {
            agents: vec![AgentRecord {
                id: "research-agent".into(),
                name: "Research Agent".into(),
                version: "1.0.0".into(),
                description: String::new(),
                scope: vec!["operator".into()],
                runtime: "hermes".into(),
                profile: Some("research".into()),
                os: vec!["research-os@1.0.0".into()],
                catalog_path: "/catalog/research-agent".into(),
                runtime_name: "operator-research-agent".into(),
                runtime_id: None,
                status: "not-started".into(),
                live: false,
                available: true,
            }],
            os_packages: vec![OsPackage {
                id: "research-os".into(),
                name: "Research OS".into(),
                version: "1.0.0".into(),
                description: String::new(),
                scope: vec!["operator".into()],
                dependencies: Vec::new(),
                capabilities: Vec::new(),
                skills: Vec::new(),
                workflows: Vec::new(),
                agents: Vec::new(),
                tools: Vec::new(),
                commands: Vec::new(),
                knowledge: Vec::new(),
                evals: Vec::new(),
                assignments: vec!["profile:operator".into()],
                available: true,
            }],
            ..RegistrySnapshot::default()
        });
    }

    #[test]
    fn every_advertised_view_shortcut_opens_its_view() {
        let cases = [
            ('1', View::Sessions),
            ('2', View::Projects),
            ('3', View::Agents),
            ('4', View::Os),
            ('5', View::Mcp),
            ('6', View::Skills),
            ('7', View::Rules),
            ('8', View::Settings),
        ];
        for (character, view) in cases {
            let mut app = app();
            app.focus = Focus::Nav;
            handle_key(&mut app, key(KeyCode::Char(character)), true);
            assert_eq!(app.view, view);
        }
    }

    #[test]
    fn control_r_requests_a_full_agk_process_reload() {
        let mut app = app();
        assert_eq!(
            handle_key(
                &mut app,
                KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL),
                true,
            ),
            Action::Reload
        );
        assert!(
            app.status
                .as_deref()
                .is_some_and(|value| value.contains("Reloading"))
        );
    }

    #[test]
    fn control_r_can_reload_from_an_open_control_overlay() {
        let mut app = app();
        app.overlay = Overlay::Search {
            value: "mcp".into(),
            original: String::new(),
        };
        assert_eq!(
            handle_key(
                &mut app,
                KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL),
                true,
            ),
            Action::Reload
        );
        assert!(matches!(app.overlay, Overlay::Search { .. }));
    }

    #[test]
    fn custom_theme_editor_live_previews_and_persists_rgb_colors() {
        let mut app = app();
        app.set_view(View::Settings);
        app.settings_section = 0;
        app.focus = Focus::Detail;
        app.theme = Theme::Custom;

        assert_eq!(
            handle_key(&mut app, key(KeyCode::Char('e')), true),
            Action::None
        );
        assert!(matches!(app.overlay, Overlay::CustomTheme { .. }));
        for character in "#112233".chars() {
            assert_eq!(
                handle_key(&mut app, key(KeyCode::Char(character)), true),
                Action::None
            );
        }
        assert_eq!(
            app.preferences.custom_colors.background,
            RgbColor(0x11, 0x22, 0x33)
        );
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::PersistPreferences
        );
        assert_eq!(app.preferences.theme, Theme::Custom);
        assert_eq!(app.overlay, Overlay::None);
    }

    #[test]
    fn overlay_captures_q_and_search_escape_restores_original_filter() {
        let mut app = app();
        app.query = "old".into();
        handle_key(&mut app, key(KeyCode::Char('/')), true);
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Char('q')), true),
            Action::None
        );
        assert_eq!(app.query, "oldq");
        handle_key(&mut app, key(KeyCode::Esc), true);
        assert_eq!(app.query, "old");
        assert!(!app.overlay.is_open());
    }

    #[test]
    fn palette_filters_and_executes_without_leaking_shortcuts() {
        let mut app = app();
        handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char('p'), KeyModifiers::CONTROL),
            true,
        );
        for character in "settings".chars() {
            handle_key(&mut app, key(KeyCode::Char(character)), true);
        }
        handle_key(&mut app, key(KeyCode::Enter), true);
        assert_eq!(app.view, View::Settings);
        assert!(!app.overlay.is_open());
    }

    #[test]
    fn bracketed_paste_populates_active_overlays_without_control_characters() {
        let mut app = app();
        handle_key(&mut app, key(KeyCode::Char('/')), true);
        assert_eq!(handle_paste(&mut app, "operator\n-control"), Action::None);
        assert_eq!(app.query, "operator-control");

        app.overlay = Overlay::NewName {
            kind: SessionKind::Shell,
            value: String::new(),
        };
        handle_paste(&mut app, "Fast SESSION ! 42");
        assert_eq!(
            app.overlay,
            Overlay::NewName {
                kind: SessionKind::Shell,
                value: "fastsession42".into(),
            }
        );
    }

    #[test]
    fn new_session_flow_returns_a_validated_side_effect() {
        let mut app = app();
        handle_key(&mut app, key(KeyCode::Char('n')), true);
        handle_key(&mut app, key(KeyCode::Down), true);
        handle_key(&mut app, key(KeyCode::Enter), true);
        for character in "Moon-1 !".chars() {
            handle_key(&mut app, key(KeyCode::Char(character)), true);
        }
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::CreateSession {
                kind: SessionKind::Codex,
                name: "moon-1".into()
            }
        );
    }

    #[test]
    fn new_session_provider_numbers_match_the_session_shortcuts() {
        for (choice, expected) in [
            ('1', SessionKind::Hermes),
            ('2', SessionKind::Codex),
            ('3', SessionKind::Claude),
            ('4', SessionKind::OpenCode),
            ('5', SessionKind::OpenRouter),
            ('6', SessionKind::Shell),
        ] {
            let mut app = app();
            app.overlay = Overlay::NewKind { selected: 0 };
            handle_key(&mut app, key(KeyCode::Char(choice)), true);
            assert_eq!(
                app.overlay,
                Overlay::NewName {
                    kind: expected,
                    value: String::new(),
                }
            );
        }
    }

    #[test]
    fn invalid_new_session_name_keeps_the_dialog_open_with_feedback() {
        let mut app = app();
        app.overlay = Overlay::NewName {
            kind: SessionKind::Hermes,
            value: "ab".into(),
        };

        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::None
        );
        assert_eq!(
            app.overlay,
            Overlay::NewName {
                kind: SessionKind::Hermes,
                value: "ab".into(),
            }
        );
        assert!(
            app.status
                .as_deref()
                .is_some_and(|status| status.contains("3–80"))
        );
    }

    #[test]
    fn settings_theme_is_live_then_cancelled_or_committed() {
        let mut app = app();
        app.set_view(View::Settings);
        app.focus = Focus::Detail;
        let initial = app.theme;
        handle_key(&mut app, key(KeyCode::Down), true);
        assert_ne!(app.theme, initial);
        handle_key(&mut app, key(KeyCode::Esc), true);
        assert_eq!(app.theme, initial);
        handle_key(&mut app, key(KeyCode::Down), true);
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::PersistPreferences
        );
        assert_eq!(app.committed_theme, app.theme);
    }

    #[test]
    fn settings_enter_requests_setup_for_the_selected_provider() {
        let mut app = app();
        app.set_snapshot(RegistrySnapshot {
            providers: vec![ProviderRecord {
                id: "claude".into(),
                name: "Claude Code".into(),
                installed: false,
                configured: false,
                command: "claude".into(),
            }],
            ..RegistrySnapshot::default()
        });
        app.set_view(View::Settings);
        app.settings_section = 1;
        app.focus = Focus::Detail;
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::InstallProvider {
                id: "claude".into()
            }
        );
    }

    #[test]
    fn session_shortcuts_toggle_preview_and_enter_terminal() {
        let mut app = app();
        add_session(&mut app);
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Char('v')), true),
            Action::PersistPreferences
        );
        assert!(!app.preferences.split_preview);
        handle_key(&mut app, key(KeyCode::Tab), true);
        assert!(!app.expanded);
        assert_eq!(app.focus, Focus::Detail);
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::EnterTerminal
        );
    }

    #[test]
    fn direct_session_shortcuts_open_the_correct_name_dialog() {
        for (key_code, expected) in [
            (KeyCode::Char('1'), SessionKind::Hermes),
            (KeyCode::Char('2'), SessionKind::Codex),
            (KeyCode::Char('3'), SessionKind::Claude),
            (KeyCode::Char('4'), SessionKind::OpenCode),
            (KeyCode::Char('5'), SessionKind::OpenRouter),
        ] {
            let mut app = app();
            app.focus = Focus::List;
            handle_key(&mut app, key(key_code), true);
            assert_eq!(
                app.overlay,
                Overlay::NewName {
                    kind: expected,
                    value: String::new(),
                }
            );
        }
    }

    #[test]
    fn compact_layout_reserves_numbers_for_the_main_menu() {
        let mut app = app();
        app.focus = Focus::List;
        handle_key_for_layout(&mut app, key(KeyCode::Char('3')), true, true);
        assert_eq!(app.view, View::Agents);
        assert_eq!(app.overlay, Overlay::None);

        app.overlay = Overlay::NewKind { selected: 0 };
        handle_key_for_layout(&mut app, key(KeyCode::Char('2')), true, true);
        assert_eq!(app.overlay, Overlay::NewKind { selected: 0 });
        handle_key_for_layout(&mut app, key(KeyCode::Down), true, true);
        handle_key_for_layout(&mut app, key(KeyCode::Enter), true, true);
        assert_eq!(
            app.overlay,
            Overlay::NewName {
                kind: SessionKind::Codex,
                value: String::new(),
            }
        );
    }

    #[test]
    fn content_arrows_never_require_a_top_menu_focus_step() {
        let mut app = app();
        add_session(&mut app);
        app.focus = Focus::List;

        handle_key(&mut app, key(KeyCode::Up), true);
        assert_eq!(app.focus, Focus::List);
        assert_eq!(app.selected, 0);

        app.focus = Focus::Nav;
        handle_key(&mut app, key(KeyCode::Down), true);
        assert_eq!(app.focus, Focus::List);
        assert_eq!(app.selected, 0);
    }

    #[test]
    fn close_is_immediate_and_rename_still_uses_a_validated_dialog() {
        let mut app = app();
        add_session(&mut app);
        let target = app.current_session_target().unwrap();

        assert_eq!(
            handle_key(&mut app, key(KeyCode::Char('x')), true),
            Action::CloseSession {
                target: target.clone()
            }
        );
        assert_eq!(app.overlay, Overlay::None);

        handle_key(&mut app, key(KeyCode::Char('r')), true);
        assert_eq!(
            app.overlay,
            Overlay::RenameSession {
                target: target.clone(),
                value: "moon".into()
            }
        );
        for _ in 0..4 {
            handle_key(&mut app, key(KeyCode::Backspace), true);
        }
        for character in "renamed-session".chars() {
            handle_key(&mut app, key(KeyCode::Char(character)), true);
        }
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::RenameSession {
                target,
                name: "renamed-session".into()
            }
        );
    }

    #[test]
    fn sessions_enter_and_horizontal_arrows_are_direct() {
        let mut app = app();
        add_session(&mut app);

        app.focus = Focus::Nav;
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::EnterTerminal
        );

        app.focus = Focus::List;
        handle_key(&mut app, key(KeyCode::Right), true);
        assert_eq!(app.view, View::Projects);
        assert_eq!(app.focus, Focus::List);

        app.set_view(View::Sessions);
        handle_key(&mut app, key(KeyCode::Left), true);
        assert_eq!(app.view, View::Settings);
        assert_eq!(app.focus, Focus::List);

        app.set_view(View::Settings);
        app.focus = Focus::Detail;
        handle_key(&mut app, key(KeyCode::Right), true);
        assert_eq!(app.view, View::Sessions);
        assert_eq!(app.focus, Focus::List);
    }

    #[test]
    fn os_enter_lists_conversations_then_supports_new_open_and_delete() {
        let mut app = app();
        add_os_agent(&mut app);
        app.set_view(View::Os);

        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::None
        );
        assert_eq!(
            app.os_conversations
                .as_ref()
                .map(|context| context.agent_id.as_str()),
            Some("research-agent")
        );

        handle_key(&mut app, key(KeyCode::Char('n')), true);
        for character in "weekly".chars() {
            handle_key(&mut app, key(KeyCode::Char(character)), true);
        }
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::OpenAgent {
                id: "research-agent".into(),
                session: "operator-research-agent-weekly".into(),
            }
        );

        app.overlay = Overlay::None;
        app.snapshot.runtimes.push(RuntimeRecord {
            id: "runtime-weekly".into(),
            name: "operator-research-agent-weekly".into(),
            kind: "hermes".into(),
            environment: "operator".into(),
            client: None,
            project: None,
            mission: None,
            native_session: None,
            hermes_profile: None,
            rmux_session: "operator-research-agent-weekly".into(),
            cwd: "/work".into(),
            status: "running".into(),
            created_at: 1.0,
            last_activity: 2.0,
            tokens: 0,
            model_usage: Vec::new(),
            managed: true,
            live: true,
        });
        let target = app
            .current_os_conversation_target()
            .expect("OS conversation");
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Char('x')), true),
            Action::CloseSession { target }
        );

        assert_eq!(
            handle_key(&mut app, key(KeyCode::Enter), true),
            Action::EnterTerminal
        );
        assert_eq!(app.view, View::Sessions);
    }

    #[test]
    fn settings_runtime_vertical_arrows_persist_refresh_cadence() {
        let mut app = app();
        app.set_view(View::Settings);
        app.settings_section = 3;
        app.focus = Focus::Detail;
        let initial = app.preferences.refresh_ms;
        assert_eq!(
            handle_key(&mut app, key(KeyCode::Down), true),
            Action::PersistPreferences
        );
        assert_ne!(app.preferences.refresh_ms, initial);
    }
}
