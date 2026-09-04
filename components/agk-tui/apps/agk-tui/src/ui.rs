use ratatui::{
    Frame,
    layout::{Alignment, Constraint, Layout, Rect, Size},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{
        Block, BorderType, Borders, Clear, List, ListItem, ListState, Padding, Paragraph, Wrap,
    },
};
use ratatui_rmux::{PaneState, PaneWidget};

use crate::{
    data::RuntimeRecord,
    input::palette_items,
    model::{App, Density, Focus, Mode, Overlay, SessionKind, SettingsSection, View, density},
    system_info::{UNKNOWN, format_optional_token_total, format_percent, format_token_total},
    theme::{CustomColors, Palette, Theme},
};

/// Borrowed preview payload prepared by the RMUX integration.  The hot tail
/// keeps full styles/cursor data; deep history intentionally falls back to
/// plain captured rows with a cheap-tail/lazy-history model.
#[derive(Clone, Copy)]
pub enum SessionPreview<'a> {
    Live(&'a PaneState),
    History(&'a [String]),
    CurrentSession,
    Unavailable,
}

pub fn draw(frame: &mut Frame, app: &mut App, preview: SessionPreview<'_>) {
    let area = frame.area();
    let mut colors = app.palette();
    // AGK is an overlay on the user's terminal, not a second painted desktop.
    // Reset the large surfaces so the native terminal background remains
    // visible; semantic text, borders and selection colors stay themed.
    if !app.theme.paints_background() {
        colors.background = Color::Reset;
        colors.surface = Color::Reset;
        colors.surface_alt = Color::Reset;
    }
    frame.render_widget(
        Block::default().style(Style::default().bg(colors.background)),
        area,
    );
    let size = density(area.width, area.height);
    if app.mode == Mode::Terminal {
        let rows = Layout::vertical([
            Constraint::Length(nav_height(area.width)),
            Constraint::Length(1),
            Constraint::Min(3),
            Constraint::Length(1),
            Constraint::Length(1),
        ])
        .split(area);
        draw_nav(frame, app, rows[0], colors);
        draw_footer_separator(frame, rows[1], colors);
        draw_terminal_workspace(frame, app, preview, rows[2], size, colors);
        draw_footer_separator(frame, rows[3], colors);
        draw_footer(frame, app, rows[4], colors);
        return;
    }

    let rows = Layout::vertical([
        Constraint::Length(nav_height(area.width)),
        Constraint::Length(1),
        Constraint::Min(3),
        Constraint::Length(1),
        Constraint::Length(1),
    ])
    .split(area);
    draw_nav(frame, app, rows[0], colors);
    draw_footer_separator(frame, rows[1], colors);
    draw_body(frame, app, preview, rows[2], size, colors);
    draw_footer_separator(frame, rows[3], colors);
    draw_footer(frame, app, rows[4], colors);
    draw_overlay(frame, app, area, colors);
}

fn draw_terminal_workspace(
    frame: &mut Frame,
    app: &mut App,
    preview: SessionPreview<'_>,
    area: Rect,
    size: Density,
    colors: Palette,
) {
    let (list_area, pane_area) = terminal_panes(area, size, app.expanded);
    if list_area.width > 0 {
        let records = app.filtered_sessions().collect::<Vec<_>>();
        let items = records
            .iter()
            .map(|runtime| session_list_item(runtime, colors))
            .collect();
        selectable(
            frame,
            list_area,
            items,
            app.selected,
            app.focus == Focus::List,
            &format!(" SESSIONS · {} ", records.len()),
            colors,
        );
    }

    let title = app
        .current_session()
        .map(|runtime| {
            if app.preview_scroll > 0 {
                format!(" {} · PAUSED · -{} ", runtime.name, app.preview_scroll)
            } else {
                format!(
                    " {} · {} · LIVE ",
                    runtime.name,
                    runtime.kind.to_ascii_uppercase()
                )
            }
        })
        .unwrap_or_else(|| " SESSION · OFFLINE ".into());
    let block = panel(&title, app.focus == Focus::Detail, colors);
    let inner = block.inner(pane_area);
    frame.render_widget(block, pane_area);
    app.preview_width = inner.width;
    app.preview_height = inner.height;
    match preview {
        SessionPreview::Live(pane) => frame.render_widget(PaneWidget::new(pane), inner),
        SessionPreview::History(lines) => {
            let visible = usize::from(inner.height);
            let max_scroll = lines.len().saturating_sub(visible).min(u16::MAX as usize) as u16;
            app.preview_max_scroll = max_scroll;
            app.preview_scroll = app.preview_scroll.min(max_scroll);
            let end = lines.len().saturating_sub(usize::from(app.preview_scroll));
            let start = end.saturating_sub(visible);
            frame.render_widget(
                Paragraph::new(Text::from_iter(lines[start..end].iter().map(|line| {
                    Line::styled(line.clone(), Style::default().fg(colors.text))
                }))),
                inner,
            );
        }
        SessionPreview::CurrentSession => frame.render_widget(
            Paragraph::new("This RMUX session is running AGK\n\nCtrl-g  Return")
                .alignment(Alignment::Center)
                .style(Style::default().fg(colors.text_muted).bg(colors.background)),
            inner,
        ),
        SessionPreview::Unavailable => frame.render_widget(
            Paragraph::new("Provider pane unavailable\n\nCtrl-g  Return")
                .alignment(Alignment::Center)
                .style(Style::default().fg(colors.text_muted).bg(colors.background)),
            inner,
        ),
    }
}

fn draw_nav(frame: &mut Frame, app: &App, area: Rect, colors: Palette) {
    let area = horizontal_area(Rect::new(
        area.x,
        area.y.saturating_add(area.height.saturating_sub(1)),
        area.width,
        area.height.min(1),
    ));
    let (start, end) = nav_window(app.view, area.width);
    let views = &View::ALL[start..end];
    let labels_width = views
        .iter()
        .map(|view| nav_label_width(*view))
        .sum::<usize>();
    let gaps = views.len().saturating_sub(1);
    let marker_width = usize::from(start > 0) * 2 + usize::from(end < View::ALL.len()) * 2;
    let gap_width = if start == 0
        && end == View::ALL.len()
        && labels_width
            .saturating_add(marker_width)
            .saturating_add(gaps * 2)
            <= usize::from(area.width)
    {
        2
    } else {
        1
    };
    let mut spans = Vec::new();
    if start > 0 {
        spans.push(Span::styled("‹ ", Style::default().fg(colors.text_muted)));
    }
    for (index, view) in views.iter().enumerate() {
        if index > 0 {
            spans.push(Span::raw(" ".repeat(gap_width)));
        }
        let selected = *view == app.view;
        spans.push(Span::styled(
            nav_label(*view),
            Style::default()
                .fg(if selected { colors.accent } else { colors.text })
                .bg(colors.background)
                .add_modifier(if selected {
                    Modifier::BOLD | Modifier::UNDERLINED
                } else {
                    Modifier::empty()
                }),
        ));
    }
    if end < View::ALL.len() {
        spans.push(Span::styled(" ›", Style::default().fg(colors.text_muted)));
    }
    frame.render_widget(
        Paragraph::new(Line::from(spans).alignment(Alignment::Left))
            .style(Style::default().bg(colors.background)),
        area,
    );
}

pub const fn nav_height(_width: u16) -> u16 {
    2
}

fn nav_label_width(view: View) -> usize {
    nav_label(view).chars().count()
}

fn nav_label(view: View) -> String {
    format!("{} {}", view.hotkey(), view.label().to_ascii_uppercase())
}

fn nav_window_width(start: usize, end: usize) -> usize {
    View::ALL[start..end]
        .iter()
        .map(|view| nav_label_width(*view))
        .sum::<usize>()
        .saturating_add(end.saturating_sub(start + 1))
        .saturating_add(usize::from(start > 0) * 2)
        .saturating_add(usize::from(end < View::ALL.len()) * 2)
}

fn nav_window(selected: View, width: u16) -> (usize, usize) {
    let selected = View::ALL
        .iter()
        .position(|view| *view == selected)
        .unwrap_or_default();
    let available = usize::from(width);
    let mut start = selected;
    let mut end = selected + 1;
    loop {
        let can_grow_left = start > 0 && nav_window_width(start - 1, end) <= available;
        let can_grow_right = end < View::ALL.len() && nav_window_width(start, end + 1) <= available;
        match (can_grow_left, can_grow_right) {
            (false, false) => break,
            (true, false) => start -= 1,
            (false, true) => end += 1,
            (true, true) => {
                let left_count = selected.saturating_sub(start);
                let right_count = end.saturating_sub(selected + 1);
                if left_count <= right_count {
                    start -= 1;
                } else {
                    end += 1;
                }
            }
        }
    }
    (start, end)
}

fn draw_body(
    frame: &mut Frame,
    app: &mut App,
    preview: SessionPreview<'_>,
    area: Rect,
    size: Density,
    colors: Palette,
) {
    let area = board_area(area);
    match app.view {
        View::Sessions => draw_sessions(frame, app, preview, area, size, colors),
        View::Projects => draw_projects(frame, app, area, size, colors),
        View::Agents => draw_agents(frame, app, area, size, colors),
        View::Os => draw_os(frame, app, area, size, colors),
        View::Mcp => draw_mcp(frame, app, area, size, colors),
        View::Skills => draw_skills(frame, app, area, size, colors),
        View::Rules => draw_rules(frame, app, area, size, colors),
        View::Settings => draw_settings(frame, app, area, size, colors),
    }
}

fn panes(app: &App, area: Rect, size: Density) -> (Rect, Rect) {
    let hidden = Rect::new(area.right(), area.y, 0, area.height);
    // Mobile stays single-column; standard and wide terminals use the dense
    // Operator Grid split so the active work remains visible beside its list.
    if app.expanded || size == Density::Compact {
        if app.focus == Focus::Detail {
            return (hidden, area);
        }
        return (area, hidden);
    }
    let list_width = operator_grid_list_width(area, size);
    let columns = Layout::horizontal([Constraint::Length(list_width), Constraint::Min(1)])
        .spacing(1)
        .split(area);
    (columns[0], columns[1])
}

fn terminal_panes(area: Rect, size: Density, expanded: bool) -> (Rect, Rect) {
    let area = horizontal_area(area);
    let hidden = Rect::new(area.x, area.y, 0, area.height);
    if expanded || area.width < 36 {
        return (hidden, area);
    }
    let list_width = operator_grid_list_width(area, size);
    let columns = Layout::horizontal([Constraint::Length(list_width), Constraint::Min(1)])
        .spacing(1)
        .split(area);
    (columns[0], columns[1])
}

/// The session list keeps one stable width before and after entering a live
/// provider. Changing interaction mode must never collapse its information.
fn operator_grid_list_width(area: Rect, size: Density) -> u16 {
    match size {
        Density::Compact => area
            .width
            .saturating_mul(35)
            .saturating_div(100)
            .clamp(16, 22),
        Density::Standard => area
            .width
            .saturating_mul(34)
            .saturating_div(100)
            .clamp(24, 32),
        Density::Wide => area
            .width
            .saturating_mul(30)
            .saturating_div(100)
            .clamp(32, 46),
    }
}

pub fn terminal_preview_area(size: Size, expanded: bool) -> Rect {
    let content = terminal_content_area(size);
    let (_, pane) = terminal_panes(content, density(size.width, size.height), expanded);
    Block::default()
        .borders(Borders::ALL)
        .padding(Padding::horizontal(1))
        .inner(pane)
}

pub fn terminal_focus_at(size: Size, expanded: bool, column: u16, row: u16) -> Option<Focus> {
    let content = terminal_content_area(size);
    if column >= size.width || !content.contains((column, row).into()) {
        return None;
    }
    let (list, pane) = terminal_panes(content, density(size.width, size.height), expanded);
    if list.contains((column, row).into()) {
        Some(Focus::List)
    } else if pane.contains((column, row).into()) {
        Some(Focus::Detail)
    } else {
        None
    }
}

fn terminal_content_area(size: Size) -> Rect {
    let header = nav_height(size.width).saturating_add(1);
    Rect::new(
        0,
        header,
        size.width,
        size.height.saturating_sub(header.saturating_add(2)),
    )
}

/// Keep boards away from the physical terminal edges without sacrificing the
/// useful height of very small mobile terminals.  Internal block padding and
/// inter-panel gaps complete the spacing system inside this outer gutter.
fn board_area(area: Rect) -> Rect {
    horizontal_area(area)
}

fn horizontal_area(area: Rect) -> Rect {
    let gutter = u16::from(area.width >= 32);
    Rect::new(
        area.x.saturating_add(gutter),
        area.y,
        area.width.saturating_sub(gutter.saturating_mul(2)),
        area.height,
    )
}

/// Resolve the panel under a mouse coordinate using the same responsive
/// geometry as the renderer.  Clicks establish focus and wheel events operate
/// on the panel under the pointer instead of whichever panel happened to be
/// focused previously.
pub fn focus_at(app: &App, size: Size, column: u16, row: u16) -> Option<Focus> {
    if column >= size.width || row >= size.height {
        return None;
    }
    let nav_height = nav_height(size.width);
    if row < nav_height {
        let nav = horizontal_area(Rect::new(0, nav_height.saturating_sub(1), size.width, 1));
        return nav.contains((column, row).into()).then_some(Focus::Nav);
    }
    let header_height = nav_height.saturating_add(1);
    let body_height = size.height.saturating_sub(header_height.saturating_add(2));
    let body = board_area(Rect::new(0, header_height, size.width, body_height));
    if !body.contains((column, row).into()) {
        return None;
    }
    let density = density(size.width, size.height);
    let (mut list, mut detail) = if app.view == View::Settings {
        settings_panes(app, body, density)
    } else {
        panes(app, body, density)
    };
    if app.view == View::Sessions && !app.preferences.split_preview && !app.expanded {
        if app.focus == Focus::Detail {
            list.width = 0;
            detail = body;
        } else {
            list = body;
            detail.width = 0;
        }
    }
    if list.contains((column, row).into()) {
        Some(Focus::List)
    } else if detail.contains((column, row).into()) {
        Some(Focus::Detail)
    } else {
        None
    }
}

fn draw_sessions(
    frame: &mut Frame,
    app: &mut App,
    preview: SessionPreview<'_>,
    area: Rect,
    size: Density,
    colors: Palette,
) {
    let (mut list_area, mut preview_area) = panes(app, area, size);
    if !app.preferences.split_preview && !app.expanded {
        if app.focus == Focus::Detail {
            list_area.width = 0;
            preview_area = area;
        } else {
            list_area = area;
            preview_area.width = 0;
        }
    }
    if list_area.width > 0 {
        let records = app.filtered_sessions().collect::<Vec<_>>();
        let items = records
            .iter()
            .map(|runtime| session_list_item(runtime, colors))
            .collect();
        let title = if app.query.is_empty() {
            format!(" SESSIONS · {} ", records.len())
        } else {
            format!(" FILTER · {} · {} ", app.query, records.len())
        };
        selectable(
            frame,
            list_area,
            items,
            app.selected,
            app.focus == Focus::List,
            &title,
            colors,
        );
    }
    if preview_area.width > 0 {
        let base_title = app
            .current_session()
            .map(|runtime| runtime.name.clone())
            .unwrap_or_else(|| "LIVE PREVIEW".into());
        let inner_height = preview_area.height.saturating_sub(2);
        let (title, history_window) = match preview {
            SessionPreview::History(lines) => {
                let viewport = usize::from(inner_height.max(1));
                let max_scroll = lines.len().saturating_sub(viewport).min(u16::MAX as usize) as u16;
                app.preview_max_scroll = max_scroll;
                app.preview_scroll = app.preview_scroll.min(max_scroll);
                let scroll = usize::from(app.preview_scroll);
                let end = lines.len().saturating_sub(scroll);
                let start = end.saturating_sub(viewport);
                (
                    format!(" {base_title} · ↑ {} FROM LIVE ", app.preview_scroll),
                    Some(&lines[start..end]),
                )
            }
            SessionPreview::CurrentSession => {
                app.preview_scroll = 0;
                app.preview_max_scroll = 0;
                (format!(" {base_title} · AGK CONTROL "), None)
            }
            SessionPreview::Live(_) => {
                app.preview_scroll = 0;
                app.preview_max_scroll = 0;
                (format!(" {base_title} · LIVE PREVIEW "), None)
            }
            SessionPreview::Unavailable => {
                app.preview_scroll = 0;
                app.preview_max_scroll = 0;
                (format!(" {base_title} · OFFLINE "), None)
            }
        };
        let block = panel(&title, app.focus == Focus::Detail, colors);
        let inner = block.inner(preview_area);
        frame.render_widget(block, preview_area);
        app.preview_width = inner.width;
        app.preview_height = inner.height;
        match preview {
            SessionPreview::Live(pane) => frame.render_widget(PaneWidget::new(pane), inner),
            SessionPreview::History(_) => {
                let rows = history_window.unwrap_or_default().iter().map(|line| {
                    Line::styled(line.clone(), Style::default().fg(colors.text))
                });
                frame.render_widget(
                    Paragraph::new(Text::from_iter(rows))
                        .style(Style::default().fg(colors.text).bg(colors.surface)),
                    inner,
                );
            }
            SessionPreview::CurrentSession => frame.render_widget(
                Paragraph::new(
                    "This is the RMUX session running AGK.\n\nIt stays visible, but its preview is disabled to prevent a recursive mirror.",
                )
                .alignment(Alignment::Center)
                .wrap(Wrap { trim: true })
                .style(Style::default().fg(colors.text_muted).bg(colors.surface)),
                inner,
            ),
            SessionPreview::Unavailable if size != Density::Compact => frame.render_widget(
                Paragraph::new(
                    "No live pane snapshot\n\nEnter  Open terminal\nTab  Switch panels\nv  Toggle split preview",
                )
                .alignment(Alignment::Center)
                .wrap(Wrap { trim: true })
                .style(Style::default().fg(colors.text_muted).bg(colors.surface)),
                inner,
            ),
            SessionPreview::Unavailable => {}
        }
    } else {
        app.preview_width = 0;
        app.preview_height = 0;
    }
}

fn session_list_item(runtime: &RuntimeRecord, colors: Palette) -> ListItem<'static> {
    let scope = [
        runtime.client.as_deref(),
        runtime.project.as_deref(),
        runtime.mission.as_deref(),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>()
    .join(" / ");
    let mut lines = vec![
        Line::from(vec![
            Span::styled(
                if runtime.live { "● " } else { "○ " },
                Style::default().fg(if runtime.live {
                    colors.success
                } else {
                    colors.text_muted
                }),
            ),
            Span::styled(
                runtime.name.clone(),
                Style::default()
                    .fg(colors.text)
                    .add_modifier(Modifier::BOLD),
            ),
        ]),
        Line::styled(
            format!("  {} · {}", runtime.kind, runtime.status),
            Style::default().fg(colors.text_muted),
        ),
        Line::styled(
            format!(
                "  {}",
                if scope.is_empty() {
                    runtime.cwd.as_str()
                } else {
                    scope.as_str()
                }
            ),
            Style::default().fg(colors.text_muted),
        ),
    ];
    if let Some(usage) = runtime.model_usage.first() {
        lines.push(Line::styled(
            format!(
                "  {} · TKN {}",
                usage.model,
                format_token_total(usage.io_tokens())
            ),
            Style::default().fg(colors.text_muted),
        ));
    }
    ListItem::new(lines)
}

fn draw_projects(frame: &mut Frame, app: &App, area: Rect, size: Density, colors: Palette) {
    let (list_area, detail_area) = panes(app, area, size);
    if list_area.width > 0 {
        let items = app
            .filtered_objects()
            .map(|object| {
                ListItem::new(vec![
                    Line::from(vec![
                        Span::styled(
                            format!("{}  ", object.kind.to_ascii_uppercase()),
                            Style::default()
                                .fg(kind_color(&object.kind, colors))
                                .add_modifier(Modifier::BOLD),
                        ),
                        Span::styled(object.name.clone(), Style::default().fg(colors.text)),
                    ]),
                    Line::styled(
                        format!("  {} · {}", object.slug, object.status),
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            })
            .collect();
        selectable(
            frame,
            list_area,
            items,
            app.selected,
            app.focus == Focus::List,
            " CLIENTS · PROJECTS · MISSIONS ",
            colors,
        );
    }
    if detail_area.width > 0 {
        let text = app.current_object().map_or_else(
            || Text::from("No canonical Agentik control objects found."),
            |object| {
                Text::from(vec![
                    field("Name", &object.name, colors),
                    field("Kind", &object.kind, colors),
                    field("Status", &object.status, colors),
                    field("Slug", &object.slug, colors),
                    field("ID", &object.id, colors),
                    field("Parent", object.parent_id.as_deref().unwrap_or("—"), colors),
                    field("Path", object.path.as_deref().unwrap_or("—"), colors),
                    Line::raw(""),
                    Line::styled(
                        "Source  ~/.agentik/control.db",
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            },
        );
        detail(frame, detail_area, text, " AGENTIK OBJECT ", app, colors);
    }
}

fn draw_agents(frame: &mut Frame, app: &App, area: Rect, size: Density, colors: Palette) {
    let (list_area, detail_area) = panes(app, area, size);
    if let Some(context) = &app.agent_conversations {
        if list_area.width > 0 {
            let items = app
                .filtered_agent_conversations()
                .map(|runtime| {
                    ListItem::new(vec![
                        Line::from(vec![
                            Span::styled(
                                if runtime.live { "● " } else { "↻ " },
                                Style::default().fg(if runtime.live {
                                    colors.success
                                } else {
                                    colors.info
                                }),
                            ),
                            Span::styled(
                                runtime.name.clone(),
                                Style::default()
                                    .fg(colors.text)
                                    .add_modifier(Modifier::BOLD),
                            ),
                        ]),
                        Line::styled(
                            format!("  {} · {}", runtime.kind, runtime.status),
                            Style::default().fg(colors.text_muted),
                        ),
                    ])
                })
                .collect::<Vec<_>>();
            selectable(
                frame,
                list_area,
                items,
                app.selected,
                app.focus == Focus::List,
                " AGENT CONVERSATIONS ",
                colors,
            );
        }
        if detail_area.width > 0 {
            let text = app.current_agent_conversation().map_or_else(
                || {
                    Text::from(vec![
                        field("Agent", &context.agent_name, colors),
                        field("Profile", &context.agent_id, colors),
                        Line::raw(""),
                        Line::styled(
                            "No conversation yet.",
                            Style::default().fg(colors.text),
                        ),
                        Line::styled(
                            "n creates a dedicated conversation · Esc returns",
                            Style::default().fg(colors.text_muted),
                        ),
                    ])
                },
                |runtime| {
                    Text::from(vec![
                        field("Agent", &context.agent_name, colors),
                        field("Conversation", &runtime.name, colors),
                        field("Status", &runtime.status, colors),
                        field(
                            "Hermes",
                            runtime.native_session.as_deref().unwrap_or("pending"),
                            colors,
                        ),
                        field(
                            "Profile",
                            runtime.hermes_profile.as_deref().unwrap_or("default"),
                            colors,
                        ),
                        Line::raw(""),
                        Line::styled(
                            "Enter opens or resumes · n creates · x closes live runtime · Esc returns",
                            Style::default().fg(colors.text_muted),
                        ),
                    ])
                },
            );
            detail(
                frame,
                detail_area,
                text,
                " AGENT CONVERSATION ",
                app,
                colors,
            );
        }
        return;
    }
    if list_area.width > 0 {
        let items = app
            .filtered_agents()
            .map(|agent| {
                ListItem::new(vec![
                    Line::from(vec![
                        Span::styled(
                            if agent.live { "● " } else { "○ " },
                            Style::default().fg(if agent.live {
                                colors.success
                            } else {
                                colors.text_muted
                            }),
                        ),
                        Span::styled(
                            agent.name.clone(),
                            Style::default()
                                .fg(colors.text)
                                .add_modifier(Modifier::BOLD),
                        ),
                    ]),
                    Line::styled(
                        format!("  {} · {}", agent.runtime, agent.status),
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            })
            .collect();
        selectable(
            frame,
            list_area,
            items,
            app.selected,
            app.focus == Focus::List,
            " AGENT REGISTRY ",
            colors,
        );
    }
    if detail_area.width > 0 {
        let text = app.current_agent().map_or_else(
            || Text::from("No bundled or user agents were discovered."),
            |agent| {
                Text::from(vec![
                    field("Agent", &agent.name, colors),
                    field("Version", &agent.version, colors),
                    field("Status", &agent.status, colors),
                    field("Runtime", &agent.runtime, colors),
                    field(
                        "Profile",
                        agent.profile.as_deref().unwrap_or("default"),
                        colors,
                    ),
                    field("OS", &join(&agent.os), colors),
                    field(
                        "Session",
                        if agent.runtime_name.is_empty() {
                            "—"
                        } else {
                            &agent.runtime_name
                        },
                        colors,
                    ),
                    field("Scope", &join(&agent.scope), colors),
                    Line::raw(""),
                    Line::styled(agent.description.clone(), Style::default().fg(colors.text)),
                    Line::raw(""),
                    Line::styled(
                        "Enter lists this agent's synced conversations.",
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            },
        );
        detail(frame, detail_area, text, " AGENT DETAIL ", app, colors);
    }
}

fn draw_os(frame: &mut Frame, app: &App, area: Rect, size: Density, colors: Palette) {
    let (list_area, detail_area) = panes(app, area, size);
    if let Some(context) = &app.os_conversations {
        if list_area.width > 0 {
            let items = app
                .filtered_os_conversations()
                .map(|runtime| {
                    ListItem::new(vec![
                        Line::from(vec![
                            Span::styled(
                                if runtime.live { "● " } else { "○ " },
                                Style::default().fg(if runtime.live {
                                    colors.success
                                } else {
                                    colors.warning
                                }),
                            ),
                            Span::styled(
                                runtime.name.clone(),
                                Style::default()
                                    .fg(colors.text)
                                    .add_modifier(Modifier::BOLD),
                            ),
                        ]),
                        Line::styled(
                            format!("  {} · {}", runtime.kind, runtime.status),
                            Style::default().fg(colors.text_muted),
                        ),
                    ])
                })
                .collect::<Vec<_>>();
            selectable(
                frame,
                list_area,
                items,
                app.selected,
                app.focus == Focus::List,
                " OS CONVERSATIONS ",
                colors,
            );
        }
        if detail_area.width > 0 {
            let package_name = app
                .os_context_package()
                .map(|package| package.name.as_str())
                .unwrap_or(context.reference.as_str());
            let text = app.current_os_conversation().map_or_else(
                || {
                    Text::from(vec![
                        field("OS", package_name, colors),
                        field("Agent", &context.agent_id, colors),
                        Line::raw(""),
                        Line::styled("No conversation yet.", Style::default().fg(colors.text)),
                        Line::styled(
                            "n creates a new dedicated conversation · Esc returns to OS registry",
                            Style::default().fg(colors.text_muted),
                        ),
                    ])
                },
                |runtime| {
                    Text::from(vec![
                        field("OS", package_name, colors),
                        field("Agent", &context.agent_id, colors),
                        field("Conversation", &runtime.name, colors),
                        field("Status", &runtime.status, colors),
                        field("Runtime", &runtime.kind, colors),
                        Line::raw(""),
                        Line::styled(
                            "Enter opens · n creates · x closes live runtime · Esc returns",
                            Style::default().fg(colors.text_muted),
                        ),
                    ])
                },
            );
            detail(frame, detail_area, text, " OS CONVERSATION ", app, colors);
        }
        return;
    }
    if list_area.width > 0 {
        let items = app
            .filtered_os()
            .map(|package| {
                ListItem::new(vec![
                    Line::from(vec![
                        Span::styled(
                            if package.available { "● " } else { "○ " },
                            Style::default().fg(if package.available {
                                colors.success
                            } else {
                                colors.warning
                            }),
                        ),
                        Span::styled(
                            package.name.clone(),
                            Style::default()
                                .fg(colors.text)
                                .add_modifier(Modifier::BOLD),
                        ),
                    ]),
                    Line::styled(
                        format!(
                            "  {} · {} assignments",
                            package.version,
                            package.assignments.len()
                        ),
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            })
            .collect();
        selectable(
            frame,
            list_area,
            items,
            app.selected,
            app.focus == Focus::List,
            " AGENTIK OS REGISTRY ",
            colors,
        );
    }
    if detail_area.width > 0 {
        let owner = app.current_os_agent();
        let owner_name = owner.map(|agent| agent.name.as_str()).unwrap_or("—");
        let owner_profile = owner
            .and_then(|agent| agent.profile.as_deref())
            .unwrap_or("default");
        let owner_session = owner
            .map(|agent| agent.runtime_name.as_str())
            .unwrap_or("—");
        let text = app.current_os().map_or_else(
            || Text::from(vec![
                Line::raw("No Operative System package is installed yet."),
                Line::raw(""),
                Line::styled(
                    "Master OS Builder is available under Agents to build the first validated OS.",
                    Style::default().fg(colors.info),
                ),
                Line::raw("OS packages remain versioned objects; the builder itself is an agent."),
            ]),
            |package| {
                Text::from(vec![
                    field("OS", &package.name, colors),
                    field("Version", &package.version, colors),
                    field("ID", &package.id, colors),
                    field("Assigned", &join(&package.assignments), colors),
                    field("Scope", &join(&package.scope), colors),
                    field("Agents", &join(&package.agents), colors),
                    field("Owner", owner_name, colors),
                    field("Profile", owner_profile, colors),
                    field("Session", owner_session, colors),
                    field("Skills", &join(&package.skills), colors),
                    field("Workflows", &join(&package.workflows), colors),
                    Line::raw(""),
                    Line::styled(
                        package.description.clone(),
                        Style::default().fg(colors.text),
                    ),
                    Line::raw(""),
                    Line::styled(
                        "Enter lists this OS conversations (open / new / delete).",
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            },
        );
        detail(frame, detail_area, text, " OPERATIVE SYSTEM ", app, colors);
    }
}

fn draw_mcp(frame: &mut Frame, app: &App, area: Rect, size: Density, colors: Palette) {
    let (list_area, detail_area) = panes(app, area, size);
    if list_area.width > 0 {
        let items = app
            .filtered_mcp()
            .map(|record| {
                ListItem::new(Line::from(vec![
                    Span::styled(
                        "● ",
                        Style::default().fg(status_color(&record.status, colors)),
                    ),
                    Span::styled(record.name.clone(), Style::default().fg(colors.text)),
                    Span::styled(
                        format!(
                            "  {} · {} · {}",
                            record.sources.join(" + "),
                            record.transport,
                            record.status
                        ),
                        Style::default().fg(colors.text_muted),
                    ),
                ]))
            })
            .collect();
        selectable(
            frame,
            list_area,
            items,
            app.selected,
            app.focus == Focus::List,
            " MCP REGISTRY ",
            colors,
        );
    }
    if detail_area.width > 0 {
        let text = app.current_mcp().map_or_else(
            || Text::from("No MCP servers are configured."),
            |record| {
                let mut lines = vec![
                    field("Server", &record.name, colors),
                    field("Sources", &record.sources.join(" + "), colors),
                    field("Transport", &record.transport, colors),
                    field("Status", &record.status, colors),
                    Line::raw(""),
                    Line::styled(
                        "Credentials and arguments are intentionally redacted.",
                        Style::default().fg(colors.text_muted),
                    ),
                ];
                if record.name == "Composio" {
                    lines.extend([Line::raw(""), heading("COMPOSIO TOOLKITS", colors)]);
                    if record.toolkits.is_empty() {
                        lines.push(Line::styled(
                            "No connected toolkit cached yet.",
                            Style::default().fg(colors.text_muted),
                        ));
                    } else {
                        lines.extend(record.toolkits.iter().map(|toolkit| {
                            Line::from(vec![
                                Span::styled(
                                    "● ",
                                    Style::default().fg(status_color(&toolkit.status, colors)),
                                ),
                                Span::styled(
                                    format!("{:<18}", toolkit.name.to_ascii_uppercase()),
                                    Style::default().fg(colors.text),
                                ),
                                Span::styled(
                                    format!(
                                        "{} · {} connection(s)",
                                        toolkit.status, toolkit.connections
                                    ),
                                    Style::default().fg(colors.text_muted),
                                ),
                            ])
                        }));
                    }
                    lines.extend([
                        Line::raw(""),
                        field("Login", "agk composio login", colors),
                        field("Connect", "agk composio connect <toolkit>", colors),
                        field("Connections", "agk composio list", colors),
                        field("Tools", "agk composio list <toolkit>", colors),
                        field("Discover", "composio search <task>", colors),
                    ]);
                }
                Text::from(lines)
            },
        );
        detail(frame, detail_area, text, " MCP DETAIL ", app, colors);
    }
}

fn draw_skills(frame: &mut Frame, app: &App, area: Rect, size: Density, colors: Palette) {
    let (list_area, detail_area) = panes(app, area, size);
    if list_area.width > 0 {
        let items = app
            .filtered_skills()
            .map(|record| {
                ListItem::new(Line::from(vec![
                    Span::styled("◆ ", Style::default().fg(colors.accent_alt)),
                    Span::styled(record.name.clone(), Style::default().fg(colors.text)),
                    Span::styled(
                        format!("  {}", record.source),
                        Style::default().fg(colors.text_muted),
                    ),
                ]))
            })
            .collect();
        selectable(
            frame,
            list_area,
            items,
            app.selected,
            app.focus == Focus::List,
            " INSTALLED SKILLS ",
            colors,
        );
    }
    if detail_area.width > 0 {
        let text = app.current_skill().map_or_else(
            || Text::from("No Hermes, Claude, or Codex skills were discovered."),
            |record| {
                Text::from(vec![
                    field("Skill", &record.name, colors),
                    field("Source", &record.source, colors),
                    field("Status", &record.status, colors),
                    Line::raw(""),
                    Line::styled(
                        "Skill contents remain owned by their native registry.",
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            },
        );
        detail(frame, detail_area, text, " SKILL DETAIL ", app, colors);
    }
}

fn draw_rules(frame: &mut Frame, app: &App, area: Rect, size: Density, colors: Palette) {
    let (list_area, detail_area) = panes(app, area, size);
    if list_area.width > 0 {
        let items = app
            .filtered_rules()
            .map(|rule| {
                ListItem::new(vec![
                    Line::from(vec![
                        Span::styled(
                            if rule.enabled { "● " } else { "○ " },
                            Style::default().fg(if rule.enabled {
                                colors.success
                            } else {
                                colors.text_muted
                            }),
                        ),
                        Span::styled(
                            rule.title.clone(),
                            Style::default()
                                .fg(colors.text)
                                .add_modifier(Modifier::BOLD),
                        ),
                    ]),
                    Line::styled(
                        format!("  {}", rule.id),
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            })
            .collect();
        selectable(
            frame,
            list_area,
            items,
            app.selected,
            app.focus == Focus::List,
            &format!(" RULES · {} ", app.snapshot.rules.len()),
            colors,
        );
    }
    if detail_area.width > 0 {
        let text = app.current_rule().map_or_else(
            || Text::from("No global rules are installed."),
            |rule| {
                let applies = if rule.providers.iter().any(|provider| provider == "*") {
                    "ALL PROVIDERS".into()
                } else {
                    rule.providers.join(" · ").to_ascii_uppercase()
                };
                Text::from(vec![
                    field("Rule", &rule.title, colors),
                    field("ID", &rule.id, colors),
                    field("Enabled", if rule.enabled { "YES" } else { "NO" }, colors),
                    field("Scope", &applies, colors),
                    Line::raw(""),
                    heading("CONTENT", colors),
                    Line::raw(""),
                    Line::styled(rule.content.clone(), Style::default().fg(colors.text)),
                    Line::raw(""),
                    Line::styled(
                        "Installed rules are projected into Hermes, Claude Code, Codex, OpenCode and OpenRouter sessions.",
                        Style::default().fg(colors.text_muted),
                    ),
                ])
            },
        );
        detail(frame, detail_area, text, " RULE DETAIL ", app, colors);
    }
}

fn draw_system(frame: &mut Frame, app: &App, area: Rect, colors: Palette) {
    let mut lines = vec![
        heading("HOST", colors),
        field(
            "Working dir",
            &app.footer
                .cwd
                .as_deref()
                .map(|path| path.to_string_lossy().into_owned())
                .unwrap_or_else(|| UNKNOWN.into()),
            colors,
        ),
        field(
            "Git branch",
            app.footer.git_branch.as_deref().unwrap_or("—"),
            colors,
        ),
        field("CPU", &format_percent(app.footer.cpu_percent), colors),
        field("RAM", &format_percent(app.footer.ram_percent), colors),
        field("Disk", &format_percent(app.footer.disk_percent), colors),
        Line::raw(""),
        heading("REGISTRIES", colors),
        field("Sessions", &app.snapshot.runtimes.len().to_string(), colors),
        field("Objects", &app.snapshot.objects.len().to_string(), colors),
        field("Agents", &app.snapshot.agents.len().to_string(), colors),
        field(
            "OS packages",
            &app.snapshot.os_packages.len().to_string(),
            colors,
        ),
        field(
            "MCP servers",
            &app.snapshot.mcp_servers.len().to_string(),
            colors,
        ),
        field("Skills", &app.snapshot.skills.len().to_string(), colors),
        field("Rules", &app.snapshot.rules.len().to_string(), colors),
        field(
            "Tokens",
            &if app.snapshot.model_usage.is_empty() {
                UNKNOWN.to_owned()
            } else {
                format_token_total(app.snapshot.token_total)
            },
            colors,
        ),
    ];
    lines.extend([Line::raw(""), heading("MODEL USAGE", colors)]);
    if app.snapshot.model_usage.is_empty() {
        lines.push(Line::styled(
            "No attributed Hermes model usage yet",
            Style::default().fg(colors.text_muted),
        ));
    } else {
        for usage in &app.snapshot.model_usage {
            lines.push(Line::from(vec![
                Span::styled(
                    format!("● {}", usage.model),
                    Style::default()
                        .fg(colors.text)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    format!(" · {}", usage.provider),
                    Style::default().fg(colors.text_muted),
                ),
            ]));
            lines.push(Line::styled(
                format!(
                    "  I/O {} · cache R {}/W {} · reasoning {} · {} calls",
                    format_token_total(usage.io_tokens()),
                    format_token_total(usage.cache_read_tokens),
                    format_token_total(usage.cache_write_tokens),
                    format_token_total(usage.reasoning_tokens),
                    usage.api_calls,
                ),
                Style::default().fg(colors.text_muted),
            ));
        }
    }
    if !app.snapshot.profiles.is_empty() {
        lines.extend([Line::raw(""), heading("PROFILES", colors)]);
        lines.extend(app.snapshot.profiles.iter().map(|profile| {
            let ready = profile.workspace_exists
                && profile.hermes_state_exists
                && profile.runtime_identity_matches
                && profile.gateway_state.as_deref() == Some("running")
                && profile.discord_state.as_deref() == Some("connected");
            let sessions = profile
                .rmux_sessions
                .map(|count| count.to_string())
                .unwrap_or_else(|| "—".into());
            Line::from(vec![
                Span::styled(
                    if ready { "● " } else { "○ " },
                    Style::default().fg(if ready {
                        colors.success
                    } else {
                        colors.warning
                    }),
                ),
                Span::styled(
                    format!("{:<9}", profile.display_name),
                    Style::default()
                        .fg(colors.text)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    format!(
                        " {sessions} sessions · {}",
                        profile.gateway_state.as_deref().unwrap_or("offline")
                    ),
                    Style::default().fg(colors.text_muted),
                ),
            ])
        }));
    }
    lines.extend([Line::raw(""), heading("HEALTH", colors)]);
    if app.snapshot.warnings.is_empty() {
        lines.push(Line::styled(
            "✓ Registries loaded without warnings",
            Style::default().fg(colors.success),
        ));
    } else {
        lines.extend(app.snapshot.warnings.iter().map(|warning| {
            Line::styled(format!("! {warning}"), Style::default().fg(colors.warning))
        }));
    }
    frame.render_widget(
        Paragraph::new(lines)
            .scroll((app.detail_scroll, 0))
            .wrap(Wrap { trim: true })
            .style(Style::default().fg(colors.text).bg(colors.surface))
            .block(panel(
                " SYSTEM & REGISTRY HEALTH ",
                app.focus == Focus::Detail,
                colors,
            )),
        area,
    );
}

fn settings_panes(app: &App, area: Rect, size: Density) -> (Rect, Rect) {
    let hidden = Rect::new(area.right(), area.y, 0, area.height);
    if size == Density::Compact {
        if app.focus == Focus::Detail {
            (hidden, area)
        } else {
            (area, hidden)
        }
    } else {
        let columns = Layout::horizontal([Constraint::Length(24), Constraint::Min(30)])
            .spacing(1)
            .split(area);
        (columns[0], columns[1])
    }
}

fn draw_settings(frame: &mut Frame, app: &App, area: Rect, size: Density, colors: Palette) {
    let (nav_area, content_area) = settings_panes(app, area, size);
    if nav_area.width > 0 {
        let items = SettingsSection::ALL
            .iter()
            .map(|section| ListItem::new(section.label()))
            .collect();
        selectable(
            frame,
            nav_area,
            items,
            app.settings_section,
            app.focus == Focus::List,
            " SETTINGS ",
            colors,
        );
    }
    if content_area.width == 0 {
        return;
    }
    match app.settings_section() {
        SettingsSection::Appearance => draw_appearance(frame, app, content_area, colors),
        SettingsSection::Providers => draw_providers(frame, app, content_area, colors),
        SettingsSection::Sessions => detail(
            frame,
            content_area,
            Text::from(vec![
                heading("Session display", colors),
                Line::raw(""),
                field(
                    "Live preview",
                    if app.preferences.split_preview {
                        "ON"
                    } else {
                        "OFF"
                    },
                    colors,
                ),
                Line::raw(""),
                Line::styled(
                    "Enter / Space toggles and persists split preview.",
                    Style::default().fg(colors.text_muted),
                ),
            ]),
            " SESSION SETTINGS ",
            app,
            colors,
        ),
        SettingsSection::Runtime => detail(
            frame,
            content_area,
            Text::from(vec![
                heading("Registry refresh", colors),
                Line::raw(""),
                field(
                    "Cadence",
                    &format!("{} ms", app.preferences.refresh_ms),
                    colors,
                ),
                Line::raw(""),
                Line::styled(
                    "↑ / ↓ changes cadence. Enter refreshes now.",
                    Style::default().fg(colors.text_muted),
                ),
            ]),
            " RUNTIME SETTINGS ",
            app,
            colors,
        ),
        SettingsSection::System => draw_system(frame, app, content_area, colors),
        SettingsSection::Help => draw_help(frame, app, content_area, size, colors),
        SettingsSection::About => detail(
            frame,
            content_area,
            Text::from(vec![
                heading("AGK Native TUI", colors),
                Line::raw(""),
                Line::styled(
                    "Hermes is the agent core. RMUX owns durable terminal sessions. Agentik registries own mission state. This TUI is their native presentation surface.",
                    Style::default().fg(colors.text),
                ),
                Line::raw(""),
                Line::styled(
                    "The renderer never mutates registry files.",
                    Style::default().fg(colors.text_muted),
                ),
            ]),
            " ABOUT ",
            app,
            colors,
        ),
    }
}

fn draw_providers(frame: &mut Frame, app: &App, area: Rect, colors: Palette) {
    let mut lines = vec![
        heading("Terminal providers", colors),
        Line::styled(
            "↑/↓ select · Enter install or repair",
            Style::default().fg(colors.text_muted),
        ),
        Line::raw(""),
    ];
    for (index, provider) in app.snapshot.providers.iter().enumerate() {
        let selected = index == app.provider_selected;
        let (status, status_color) = if !provider.installed {
            ("NOT INSTALLED", colors.error)
        } else if !provider.configured {
            ("SETUP REQUIRED", colors.warning)
        } else {
            ("READY", colors.success)
        };
        lines.push(Line::from(vec![
            Span::styled(
                if selected { "▶ " } else { "  " },
                Style::default().fg(colors.accent),
            ),
            Span::styled(
                format!("{:<22}", provider.name),
                Style::default()
                    .fg(if selected { colors.accent } else { colors.text })
                    .add_modifier(if selected {
                        Modifier::BOLD
                    } else {
                        Modifier::empty()
                    }),
            ),
            Span::styled(status, Style::default().fg(status_color)),
        ]));
    }
    if let Some(provider) = app.current_provider() {
        lines.extend([
            Line::raw(""),
            field("Command", &provider.command, colors),
            Line::styled(
                "Installer runs in the foreground, then AGK verifies the executable and setup.",
                Style::default().fg(colors.text_muted),
            ),
        ]);
    }
    detail(
        frame,
        area,
        Text::from(lines),
        " PROVIDERS · INSTALL & VERIFY ",
        app,
        colors,
    );
}

fn draw_appearance(frame: &mut Frame, app: &App, area: Rect, colors: Palette) {
    let mut lines = vec![
        heading("Theme", colors),
        Line::styled(
            "↑/↓ live preview · Enter save · E edit Custom · Esc revert",
            Style::default().fg(colors.text_muted),
        ),
        Line::raw(""),
    ];
    // Fifteen choices stay visible without turning Appearance into a tall,
    // scrolling list. Narrow panes retain the simple one-column layout.
    let column_count = usize::from(area.width >= 58) + 1;
    let column_width = usize::from(area.width.saturating_sub(4)) / column_count;
    let row_count = Theme::ALL.len().div_ceil(column_count);
    for row_index in 0..row_count {
        let mut row = Vec::new();
        for column in 0..column_count {
            let index = row_index + column * row_count;
            let Some(theme) = Theme::ALL.get(index) else {
                continue;
            };
            if column > 0 {
                row.push(Span::raw(" "));
            }
            let selected = *theme == app.theme;
            row.push(Span::styled(
                if selected { "▶ " } else { "  " },
                Style::default().fg(colors.accent),
            ));
            let label_width = column_width.saturating_sub(11).clamp(8, 16);
            row.push(Span::styled(
                format!("{:<label_width$}", theme.name()),
                Style::default()
                    .fg(if selected { colors.accent } else { colors.text })
                    .add_modifier(if selected {
                        Modifier::BOLD
                    } else {
                        Modifier::empty()
                    }),
            ));
            for swatch in theme
                .swatches_with_custom(app.preferences.custom_colors)
                .into_iter()
                .take(3)
            {
                row.push(Span::styled("  ", Style::default().bg(swatch)));
                row.push(Span::raw(" "));
            }
        }
        lines.push(Line::from(row));
    }
    lines.extend([
        Line::raw(""),
        Line::styled(app.theme.description(), Style::default().fg(colors.text)),
        Line::styled(
            if app.theme == Theme::Custom {
                "E opens the RGB editor · 10 semantic colors · live preview"
            } else if app.theme.paints_background() {
                "This theme deliberately paints the full terminal canvas."
            } else {
                "Uses your terminal background with themed content and controls."
            },
            Style::default().fg(colors.text_muted),
        ),
        Line::styled(
            if app.theme == app.committed_theme {
                "Saved theme"
            } else {
                "Previewing — Enter to persist, Esc to revert"
            },
            Style::default().fg(if app.theme == app.committed_theme {
                colors.success
            } else {
                colors.warning
            }),
        ),
    ]);
    detail(
        frame,
        area,
        Text::from(lines),
        " APPEARANCE · LIVE PREVIEW ",
        app,
        colors,
    );
}

fn draw_help(frame: &mut Frame, app: &App, area: Rect, size: Density, colors: Palette) {
    let mut lines = vec![
        heading("NAVIGATION", colors),
        help_key("←/→", "Always change the top menu", colors),
        help_key("1–8", "Open a numbered top menu", colors),
        help_key("↑/↓  k/j", "Choose content or scroll detail", colors),
        help_key("Enter", "Open or activate the selected content", colors),
        help_key(
            "Tab / Shift-Tab",
            "Toggle list and detail when both are available",
            colors,
        ),
        Line::raw(""),
        heading("SESSIONS", colors),
        help_key("Enter", "Open selected pane and type immediately", colors),
        help_key(
            "Tab",
            "Alternate list/provider; provider input is immediate",
            colors,
        ),
        help_key("Click pane", "Focus provider input immediately", colors),
        help_key("Tab Tab", "Rapid double Tab hides the left panel", colors),
        help_key("Ctrl-g", "Return to the main AGK menu", colors),
        help_key(
            "Ctrl-r",
            "Forwarded to the active terminal provider",
            colors,
        ),
        help_key("v", "Toggle persistent split preview", colors),
        help_key(
            "n",
            "Choose provider, create session, then open it when RMUX is live",
            colors,
        ),
    ];
    if size != Density::Compact {
        lines.push(help_key(
            "1/2/3/4/5",
            "New Hermes / Codex / Claude Code / OpenCode / Hermes OpenRouter",
            colors,
        ));
    }
    lines.extend([
        help_key("x / r", "Close immediately / rename session", colors),
        Line::raw(""),
        heading("COMMANDS", colors),
        help_key("/", "Search; Enter accepts, Esc restores", colors),
        help_key("Ctrl-p", "Command palette", colors),
        help_key(
            "Ctrl-r",
            "Reload AGK in Control Mode; forwarded inside a provider terminal",
            colors,
        ),
        help_key("F5", "Refresh RMUX and MCP registries", colors),
        help_key(
            "PgUp/PgDn · g/G",
            "Browse RMUX history / return live",
            colors,
        ),
        Line::raw(""),
        heading("SETTINGS & CONTROL", colors),
        help_key("↑/↓", "Live theme preview / refresh cadence", colors),
        help_key("Enter", "Persist selected setting", colors),
        help_key("Esc", "Revert preview, collapse, or clear filter", colors),
        help_key("q", "Detach AGK; work sessions keep running", colors),
    ]);
    let help = Text::from(lines);
    frame.render_widget(
        Paragraph::new(help)
            .scroll((app.detail_scroll, 0))
            .wrap(Wrap { trim: false })
            .style(Style::default().fg(colors.text).bg(colors.surface))
            .block(panel(" COMPLETE KEYBOARD REFERENCE ", true, colors)),
        area,
    );
}

fn draw_footer_separator(frame: &mut Frame, area: Rect, colors: Palette) {
    let area = horizontal_area(area);
    frame.render_widget(
        Paragraph::new("─".repeat(usize::from(area.width)))
            .style(Style::default().fg(colors.border).bg(colors.background)),
        area,
    );
}

fn draw_footer(frame: &mut Frame, app: &App, area: Rect, colors: Palette) {
    let area = horizontal_area(area);
    let live = app
        .snapshot
        .runtimes
        .iter()
        .filter(|runtime| runtime.live)
        .count();
    let tokens = format_optional_token_total(app.footer.token_total);
    let full_metrics = format!(
        "TKN {} · RAM {} · CPU {} · DISK {} · ● {live} LIVE",
        tokens,
        format_percent(app.footer.ram_percent),
        format_percent(app.footer.cpu_percent),
        format_percent(app.footer.disk_percent),
    );
    let model_metrics = app
        .footer
        .token_model
        .as_deref()
        .map(|model| format!("{model} · {full_metrics}"));
    let compact_metrics = format!(
        "TKN {}  RAM {}  CPU {}  DISK {}  ● {live} LIVE",
        tokens,
        format_percent(app.footer.ram_percent),
        format_percent(app.footer.cpu_percent),
        format_percent(app.footer.disk_percent),
    );
    let right_budget = area.width.saturating_sub(8) as usize;
    let full_context_width = footer_context(app, usize::MAX).chars().count();
    let metrics = if let Some(model_metrics) = model_metrics.filter(|value| {
        value
            .chars()
            .count()
            .saturating_add(full_context_width)
            .saturating_add(2)
            <= usize::from(area.width)
    }) {
        model_metrics
    } else if full_metrics.chars().count() <= right_budget {
        full_metrics
    } else {
        abbreviate(&compact_metrics, right_budget)
    };
    let right_width = (metrics.chars().count() as u16 + 1).min(area.width);
    let columns =
        Layout::horizontal([Constraint::Min(0), Constraint::Length(right_width)]).split(area);
    let left = footer_context(app, usize::from(columns[0].width));
    frame.render_widget(
        Paragraph::new(left).style(Style::default().fg(colors.text).bg(colors.background)),
        columns[0],
    );
    frame.render_widget(
        Paragraph::new(format!(" {metrics}"))
            .alignment(Alignment::Right)
            .style(Style::default().fg(colors.text_muted).bg(colors.background)),
        columns[1],
    );
}

fn draw_overlay(frame: &mut Frame, app: &App, area: Rect, colors: Palette) {
    let compact = density(area.width, area.height) == Density::Compact;
    let (rect, title, lines) = match &app.overlay {
        Overlay::None => return,
        Overlay::Search { value, .. } => (
            centered(area, 70, 5),
            " SEARCH ",
            vec![
                Line::styled(format!("/{value}▌"), Style::default().fg(colors.text)),
                Line::styled(
                    "Enter accept · Esc restore · Backspace edit",
                    Style::default().fg(colors.text_muted),
                ),
            ],
        ),
        Overlay::Palette { query, selected } => {
            let items = palette_items(query);
            let mut lines = vec![
                Line::from(vec![
                    Span::styled("› ", Style::default().fg(colors.accent)),
                    Span::styled(format!("{query}▌"), Style::default().fg(colors.text)),
                ]),
                Line::raw(""),
            ];
            lines.extend(items.iter().enumerate().map(|(index, item)| {
                Line::from(vec![
                    Span::styled(
                        if index == *selected { "▶ " } else { "  " },
                        Style::default().fg(colors.accent),
                    ),
                    Span::styled(
                        format!("{:<34}", item.label),
                        Style::default()
                            .fg(if index == *selected {
                                colors.selection_text
                            } else {
                                colors.text
                            })
                            .bg(if index == *selected {
                                colors.selection_bg
                            } else {
                                colors.surface_alt
                            }),
                    ),
                    Span::styled(item.hint, Style::default().fg(colors.text_muted)),
                ])
            }));
            (
                centered(area, 68, (items.len() as u16 + 5).min(20)),
                " COMMAND PALETTE · CTRL-P ",
                lines,
            )
        }
        Overlay::NewKind { selected } => (
            centered(area, 46, 9),
            " NEW SESSION · TYPE ",
            SessionKind::ALL
                .iter()
                .enumerate()
                .map(|(index, kind)| {
                    Line::from(vec![
                        Span::styled(
                            if index == *selected { "▶ " } else { "  " },
                            Style::default().fg(colors.accent),
                        ),
                        Span::styled(
                            if compact {
                                kind.label().to_owned()
                            } else {
                                format!("{}. {}", index + 1, kind.label())
                            },
                            Style::default().fg(colors.text),
                        ),
                    ])
                })
                .collect(),
        ),
        Overlay::NewName { kind, value } => (
            centered(area, 56, 7),
            " NEW SESSION · NAME ",
            vec![
                field("Type", kind.label(), colors),
                Line::raw(""),
                Line::styled(format!("> {value}▌"), Style::default().fg(colors.text)),
                Line::styled(
                    "3–80 lowercase letters, numbers or - · Enter create · Esc cancel",
                    Style::default().fg(colors.text_muted),
                ),
            ],
        ),
        Overlay::NewAgentConversation {
            agent_id,
            runtime_prefix,
            value,
        } => (
            centered(area, 66, 9),
            " NEW AGENT CONVERSATION ",
            vec![
                field("Agent", agent_id, colors),
                field("Runtime", &format!("{runtime_prefix}-{value}"), colors),
                Line::raw(""),
                Line::styled(format!("> {value}▌"), Style::default().fg(colors.text)),
                Line::styled(
                    "3+ lowercase letters, numbers or - · Enter create · Esc cancel",
                    Style::default().fg(colors.text_muted),
                ),
            ],
        ),
        Overlay::RenameSession { target, value } => (
            centered(area, 58, 7),
            " RENAME SESSION ",
            vec![
                field("Current", &target.name, colors),
                Line::raw(""),
                Line::styled(format!("> {value}▌"), Style::default().fg(colors.text)),
                Line::styled(
                    "3–80 lowercase letters, numbers or - · Enter rename · Esc cancel",
                    Style::default().fg(colors.text_muted),
                ),
            ],
        ),
        Overlay::CustomTheme {
            working,
            selected,
            value,
            ..
        } => {
            let mut lines = vec![Line::styled(
                "↑/↓ choose · type #RRGGBB · Enter save · Esc cancel",
                Style::default().fg(colors.text_muted),
            )];
            lines.extend((0..CustomColors::LEN).map(|index| {
                let active = index == *selected;
                let rgb = working.get(index);
                Line::from(vec![
                    Span::styled(
                        if active { "▶ " } else { "  " },
                        Style::default().fg(colors.accent),
                    ),
                    Span::styled(
                        format!("{:<13}", CustomColors::label(index)),
                        Style::default().fg(if active { colors.accent } else { colors.text }),
                    ),
                    Span::styled("  ", Style::default().bg(rgb.color())),
                    Span::raw("  "),
                    Span::styled(
                        if active {
                            format!("{value}▌")
                        } else {
                            rgb.hex()
                        },
                        Style::default()
                            .fg(if active {
                                colors.selection_text
                            } else {
                                colors.text_muted
                            })
                            .bg(if active {
                                colors.selection_bg
                            } else {
                                colors.surface_alt
                            }),
                    ),
                ])
            }));
            (
                centered(area, 56, CustomColors::LEN as u16 + 4),
                " CUSTOM THEME ",
                lines,
            )
        }
    };
    frame.render_widget(Clear, rect);
    frame.render_widget(
        Paragraph::new(lines)
            .wrap(Wrap { trim: true })
            .style(Style::default().fg(colors.text).bg(colors.surface_alt))
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .title(title)
                    .padding(Padding::horizontal(1))
                    .border_style(Style::default().fg(colors.accent)),
            ),
        rect,
    );
}

fn selectable(
    frame: &mut Frame,
    area: Rect,
    items: Vec<ListItem<'static>>,
    selected: usize,
    focused: bool,
    title: &str,
    colors: Palette,
) {
    let empty = items.is_empty();
    let items = if empty {
        vec![ListItem::new(Line::styled(
            "No matching records",
            Style::default().fg(colors.text_muted),
        ))]
    } else {
        items
    };
    let mut state = ListState::default().with_selected((!empty).then_some(selected));
    let list = List::new(items)
        .style(Style::default().fg(colors.text).bg(colors.surface))
        .block(panel(title, focused, colors))
        .highlight_style(
            Style::default()
                .fg(colors.selection_text)
                .bg(colors.selection_bg)
                .add_modifier(Modifier::BOLD),
        )
        .highlight_symbol("▶ ");
    frame.render_stateful_widget(list, area, &mut state);
}

fn detail(
    frame: &mut Frame,
    area: Rect,
    text: Text<'static>,
    title: &str,
    app: &App,
    colors: Palette,
) {
    frame.render_widget(
        Paragraph::new(text)
            .scroll((app.detail_scroll, 0))
            .wrap(Wrap { trim: true })
            .style(Style::default().fg(colors.text).bg(colors.surface))
            .block(panel(title, app.focus == Focus::Detail, colors)),
        area,
    );
}

fn panel<'a>(title: &'a str, focused: bool, colors: Palette) -> Block<'a> {
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Plain)
        .title(title)
        .padding(Padding::horizontal(1))
        .style(Style::default().bg(colors.surface))
        .border_style(Style::default().fg(if focused {
            colors.border_focused
        } else {
            colors.border
        }))
}

fn field(label: &str, value: &str, colors: Palette) -> Line<'static> {
    Line::from(vec![
        Span::styled(
            format!("{label:<14}"),
            Style::default().fg(colors.text_muted),
        ),
        Span::styled(value.to_owned(), Style::default().fg(colors.text)),
    ])
}

fn heading(label: &str, colors: Palette) -> Line<'static> {
    Line::styled(
        label.to_owned(),
        Style::default()
            .fg(colors.accent)
            .add_modifier(Modifier::BOLD),
    )
}

fn help_key(key: &str, description: &str, colors: Palette) -> Line<'static> {
    Line::from(vec![
        Span::styled(
            format!("  {key:<18}"),
            Style::default()
                .fg(colors.accent_alt)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(description.to_owned(), Style::default().fg(colors.text)),
    ])
}

fn join(values: &[String]) -> String {
    if values.is_empty() {
        "—".into()
    } else {
        values.join(", ")
    }
}

fn kind_color(kind: &str, colors: Palette) -> Color {
    match kind.to_ascii_lowercase().as_str() {
        "client" => colors.info,
        "project" => colors.accent_alt,
        "mission" => colors.accent,
        _ => colors.text_muted,
    }
}

fn status_color(status: &str, colors: Palette) -> Color {
    match status.to_ascii_lowercase().as_str() {
        "active" | "available" | "configured" | "connected" | "live" | "ready" | "running" => {
            colors.success
        }
        "failed" | "error" | "unavailable" => colors.error,
        _ => colors.warning,
    }
}

fn centered(area: Rect, width_percent: u16, height: u16) -> Rect {
    let width = area
        .width
        .saturating_mul(width_percent)
        .saturating_div(100)
        .clamp(20.min(area.width), area.width);
    let height = height.min(area.height);
    Rect::new(
        area.x + area.width.saturating_sub(width) / 2,
        area.y + area.height.saturating_sub(height) / 2,
        width,
        height,
    )
}

fn footer_context(app: &App, width: usize) -> String {
    const BRAND: &str = "AGK";
    if let Some(status) = app.status.as_deref() {
        return abbreviate(&format!("{BRAND} · {status}"), width);
    }
    let session = app.selected_session_name().unwrap_or(UNKNOWN);
    let project = footer_project(app);
    let branch = app.footer.git_branch.as_deref().unwrap_or(UNKNOWN);
    let values = [Some(session), project, Some(branch)]
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
    for count in (1..=values.len()).rev() {
        let separators = count * 3;
        let value_budget = width.saturating_sub(BRAND.chars().count() + separators);
        let value_width = value_budget / count;
        if value_width < 3 {
            continue;
        }
        let rendered = values[..count]
            .iter()
            .map(|value| abbreviate(value, value_width))
            .collect::<Vec<_>>();
        return abbreviate(&format!("{BRAND} · {}", rendered.join(" · ")), width);
    }
    abbreviate(BRAND, width)
}

fn footer_project(app: &App) -> Option<&str> {
    if app.view == View::Projects {
        return app
            .current_object()
            .filter(|object| object.kind.eq_ignore_ascii_case("project"))
            .map(|object| object.name.as_str());
    }
    let session = app.selected_session_name()?;
    app.snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.name == session)
        .and_then(|runtime| runtime.project.as_deref())
}

fn abbreviate(value: &str, width: usize) -> String {
    let characters = value.chars().collect::<Vec<_>>();
    if characters.len() <= width {
        return value.into();
    }
    if width == 0 {
        return String::new();
    }
    if width <= 2 {
        return "…".repeat(width);
    }
    let left = (width - 1) / 2;
    let right = width - left - 1;
    characters[..left]
        .iter()
        .chain(std::iter::once(&'…'))
        .chain(characters[characters.len() - right..].iter())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{
        CapabilityRecord, CapabilityToolkitRecord, ModelUsageRecord, ProviderRecord,
        RegistrySnapshot, RuleRecord, RuntimeRecord,
    };
    use crate::theme::Preferences;
    use ratatui::{Terminal, backend::TestBackend};

    fn test_app() -> App {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![RuntimeRecord {
                id: "runtime-moon".into(),
                name: "moon".into(),
                kind: "hermes".into(),
                environment: "mission".into(),
                client: Some("acme".into()),
                project: Some("luna".into()),
                mission: Some("launch".into()),
                native_session: Some("hermes-moon".into()),
                hermes_profile: None,
                rmux_session: "mission-moon-hermes".into(),
                cwd: "/work/luna".into(),
                status: "active".into(),
                created_at: 1.0,
                last_activity: 2.0,
                tokens: 12_300,
                model_usage: vec![ModelUsageRecord {
                    model: "claude-sonnet-4-6".into(),
                    provider: "anthropic".into(),
                    input_tokens: 10_000,
                    output_tokens: 2_300,
                    api_calls: 3,
                    last_used_at: 2.0,
                    ..ModelUsageRecord::default()
                }],
                managed: true,
                live: true,
            }],
            providers: vec![ProviderRecord {
                id: "hermes".into(),
                name: "Hermes".into(),
                installed: true,
                configured: true,
                command: "hermes".into(),
            }],
            ..RegistrySnapshot::default()
        });
        app.footer.cwd = Some("/work/hermes-agent".into());
        app.footer.git_branch = Some("agk/native".into());
        app.footer.cpu_percent = Some(12.0);
        app.footer.ram_percent = Some(34.0);
        app.footer.disk_percent = Some(56.0);
        app.footer.session_count = 2;
        app.footer.token_total = Some(12_300);
        app.footer.token_model = Some("claude-sonnet-4-6".into());
        app.footer.local_time = "13:37:00".into();
        app
    }

    fn render(mut app: App, width: u16, height: u16) -> String {
        let backend = TestBackend::new(width, height);
        let mut terminal = Terminal::new(backend).unwrap();
        terminal
            .draw(|frame| draw(frame, &mut app, SessionPreview::Unavailable))
            .unwrap();
        terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(|cell| cell.symbol())
            .collect()
    }

    #[test]
    fn every_view_renders_at_every_density() {
        for view in View::ALL {
            for (width, height) in [(60, 16), (90, 24), (140, 40)] {
                let mut app = test_app();
                app.set_view(view);
                assert!(render(app, width, height).contains("AGK"));
            }
        }
    }

    #[test]
    fn footer_is_one_clean_line_with_context_metrics_and_live_count() {
        let output = render(test_app(), 160, 32);
        for value in [
            "AGK · moon · luna · agk/native",
            "TKN 12.3K",
            "RAM 34%",
            "CPU 12%",
            "DISK 56%",
            "● 1 LIVE",
        ] {
            assert!(output.contains(value), "missing {value:?}");
        }
        for removed in [
            "MISSION CONTROL",
            "CWD ",
            "GIT ",
            "SESSION ",
            "SESS ",
            "13:37:00",
            "navigation",
        ] {
            assert!(
                !output.contains(removed),
                "obsolete footer/header text {removed:?}"
            );
        }
    }

    #[test]
    fn transient_status_is_visible_in_the_one_line_footer() {
        let mut app = test_app();
        app.status = Some("Session creation failed: duplicate name".into());
        let screen = render(app, 120, 24);

        assert!(screen.contains("AGK · Session creation failed: duplicate name"));
    }

    #[test]
    fn settings_uses_left_navigation_and_live_theme_content() {
        let mut app = test_app();
        app.set_view(View::Settings);
        let output = render(app, 140, 40);
        assert!(output.contains("Appearance"));
        assert!(output.contains("APPEARANCE · LIVE PREVIEW"));
        assert!(output.contains("Classic Dark"));
        assert!(output.contains("Classic Light"));
        assert!(output.contains("Hermes Dark"));
        assert!(output.contains("Claude Light"));
        assert!(output.contains("Codex Dark"));
    }

    #[test]
    fn appearance_exposes_all_built_in_themes_and_the_custom_rgb_editor() {
        let mut app = test_app();
        app.set_view(View::Settings);
        app.settings_section = 0;
        app.focus = Focus::Detail;
        let output = render(app, 140, 40);
        for name in [
            "Pure Black",
            "Pure White",
            "Midnight",
            "Graphite",
            "Terminal Amber",
            "Terminal Green",
            "Custom",
        ] {
            assert!(output.contains(name), "missing theme {name:?}");
        }

        let mut app = test_app();
        app.theme = Theme::Custom;
        let colors = app.preferences.custom_colors;
        app.overlay = Overlay::CustomTheme {
            original: colors,
            working: colors,
            selected: 0,
            value: colors.background.hex(),
            fresh: true,
        };
        let output = render(app, 90, 24);
        assert!(output.contains("CUSTOM THEME"));
        assert!(output.contains("Background"));
        assert!(output.contains("#0C0E12"));
        assert!(output.contains("Enter save"));
    }

    #[test]
    fn settings_reports_provider_readiness_and_install_action_hint() {
        let mut app = test_app();
        app.set_view(View::Settings);
        app.settings_section = 1;
        app.focus = Focus::Detail;
        let output = render(app, 140, 40);
        assert!(output.contains("PROVIDERS · INSTALL & VERIFY"));
        assert!(output.contains("Hermes"));
        assert!(output.contains("READY"));
        assert!(output.contains("Enter install or repair"));
    }

    #[test]
    fn rules_use_operator_grid_list_detail_and_show_global_scope() {
        let mut app = test_app();
        app.snapshot.rules = vec![RuleRecord {
            id: "verify-runtime".into(),
            title: "Verify the real runtime".into(),
            content: "Test the complete user-visible flow.".into(),
            providers: vec!["*".into()],
            enabled: true,
            source: "/etc/agk-terminal/rules.yaml".into(),
        }];
        app.set_view(View::Rules);
        let output = render(app, 140, 32);
        for expected in [
            "RULES · 1",
            "Verify the real runtime",
            "ALL PROVIDERS",
            "Test the complete user-visible flow.",
        ] {
            assert!(output.contains(expected), "missing {expected:?}");
        }
    }

    #[test]
    fn help_documents_all_interaction_layers() {
        let mut app = test_app();
        app.set_view(View::Settings);
        app.settings_section = SettingsSection::ALL
            .iter()
            .position(|section| *section == SettingsSection::Help)
            .unwrap();
        app.focus = Focus::Detail;
        let output = render(app, 140, 48);
        for value in [
            "Tab / Shift-Tab",
            "Tab Tab",
            "Ctrl-g",
            "Ctrl-p",
            "Esc",
            "Enter",
        ] {
            assert!(output.contains(value), "missing {value:?}");
        }
    }

    #[test]
    fn terminal_mode_reserves_the_last_row_for_the_footer() {
        let mut app = test_app();
        app.mode = Mode::Terminal;
        let output = render(app, 100, 28);
        assert!(output.contains("Ctrl-g"));
        assert!(output.contains("AGK · moon · luna · agk/native"));
        assert!(output.contains("TKN 12.3K"));
        assert!(output.contains("RAM 34%"));
        assert!(output.contains("CPU 12%"));
        assert!(output.contains("DISK 56%"));
        assert!(output.contains("● 1 LIVE"));
        assert!(!output.contains("MISSION CONTROL"));
        assert!(output.contains("1 SESSIONS"));
    }

    #[test]
    fn top_menu_survives_full_session_and_control_return() {
        let mut app = test_app();
        let backend = TestBackend::new(100, 28);
        let mut terminal = Terminal::new(backend).unwrap();

        for (mode, expanded, focus) in [
            (Mode::Control, false, Focus::List),
            (Mode::Terminal, false, Focus::Detail),
            (Mode::Terminal, true, Focus::Detail),
            (Mode::Control, false, Focus::List),
        ] {
            app.mode = mode;
            app.expanded = expanded;
            app.focus = focus;
            terminal.clear().unwrap();
            terminal
                .draw(|frame| draw(frame, &mut app, SessionPreview::Unavailable))
                .unwrap();
            let top_menu = terminal
                .backend()
                .buffer()
                .content
                .chunks(100)
                .nth(1)
                .unwrap()
                .iter()
                .map(|cell| cell.symbol())
                .collect::<String>();
            assert!(top_menu.contains("1 SESSIONS"));
            assert!(top_menu.contains("8 SETTINGS"));
            assert!(!top_menu.contains("9 HELP"));
        }
    }

    #[test]
    fn system_view_reports_exact_usage_by_model_and_provider() {
        let mut app = test_app();
        app.snapshot.model_usage = app.snapshot.runtimes[0].model_usage.clone();
        app.snapshot.token_total = 12_300;
        app.set_view(View::Settings);
        app.settings_section = SettingsSection::ALL
            .iter()
            .position(|section| *section == SettingsSection::System)
            .unwrap();
        app.focus = Focus::Detail;
        let output = render(app, 140, 40);
        assert!(output.contains("MODEL USAGE"));
        assert!(output.contains("claude-sonnet-4-6"));
        assert!(output.contains("anthropic"));
        assert!(output.contains("I/O 12.3K"));
        assert!(output.contains("3 calls"));
    }

    #[test]
    fn hidden_split_still_allows_focused_live_preview() {
        let mut app = test_app();
        app.preferences.split_preview = false;
        app.focus = Focus::Detail;
        let output = render(app, 100, 28);
        assert!(output.contains("moon · OFFLINE"));
        assert!(!output.contains("SESSIONS · 1"));
    }

    #[test]
    fn compact_offline_preview_keeps_the_board_but_removes_instruction_noise() {
        let mut app = test_app();
        app.focus = Focus::Detail;
        let output = render(app, 60, 20);
        assert!(output.contains("moon · OFFLINE"));
        for removed in [
            "No live pane snapshot",
            "Fullscreen terminal",
            "Expand",
            "Toggle split preview",
        ] {
            assert!(
                !output.contains(removed),
                "mobile preview leaked {removed:?}"
            );
        }
    }

    #[test]
    fn compact_provider_picker_uses_arrows_without_numbered_providers() {
        let mut app = test_app();
        app.overlay = Overlay::NewKind { selected: 0 };
        let output = render(app, 60, 20);
        assert!(output.contains("Hermes"));
        assert!(output.contains("Claude"));
        assert!(!output.contains("1. Hermes"));
        assert!(!output.contains("3. Claude"));
    }

    #[test]
    fn standard_density_uses_the_operator_grid_split() {
        let output = render(test_app(), 90, 24);
        assert!(output.contains("SESSIONS · 1"));
        assert!(output.contains("moon · OFFLINE"));
        assert!(output.contains("8 SETTINGS"), "full navigation was clipped");
    }

    #[test]
    fn compact_navigation_is_one_line_and_keeps_every_selected_label_complete() {
        for view in View::ALL {
            let mut app = test_app();
            app.set_view(view);
            let output = render(app, 45, 16);
            let label = nav_label(view);
            assert!(output.contains(&label), "missing selected {label:?}");
        }
        assert_eq!(nav_height(20), 2);
        assert_eq!(nav_height(45), 2);
        assert_eq!(nav_height(120), 2);
        assert_eq!(nav_window(View::Sessions, 45).0, 0);
        assert_eq!(nav_window(View::Settings, 45).1, View::ALL.len());
    }

    #[test]
    fn top_menu_is_uppercase_left_aligned_with_gap_and_separator() {
        let mut app = test_app();
        let backend = TestBackend::new(60, 18);
        let mut terminal = Terminal::new(backend).unwrap();
        terminal
            .draw(|frame| draw(frame, &mut app, SessionPreview::Unavailable))
            .unwrap();
        let active = &terminal.backend().buffer()[(1, 1)];
        assert_eq!(active.bg, Color::Reset);
        assert_eq!(active.fg, app.palette().accent);
        let rows = terminal
            .backend()
            .buffer()
            .content
            .chunks(60)
            .take(3)
            .map(|row| row.iter().map(|cell| cell.symbol()).collect::<String>())
            .collect::<Vec<_>>();
        assert_eq!(rows[0], " ".repeat(60));
        assert!(rows[1].starts_with(" 1 SESSIONS"));
        assert_eq!(rows[2], format!(" {} ", "─".repeat(58)));
    }

    #[test]
    fn desktop_top_menu_uses_compact_two_space_gaps() {
        let output = render(test_app(), 120, 24);
        assert!(output.contains("1 SESSIONS  2 PROJECTS"));
        assert!(!output.contains("1 SESSIONS   2 PROJECTS"));
    }

    #[test]
    fn boards_use_responsive_gutters_internal_padding_and_panel_gaps() {
        let roomy = board_area(Rect::new(0, 3, 140, 35));
        assert_eq!(roomy, Rect::new(1, 3, 138, 35));

        let mobile = board_area(Rect::new(0, 3, 60, 11));
        assert_eq!(mobile, Rect::new(1, 3, 58, 11));

        let app = test_app();
        let (list, detail) = panes(&app, roomy, Density::Wide);
        assert_eq!(detail.x, list.right() + 1);

        let inner = panel(" TEST ", false, app.palette()).inner(list);
        assert_eq!(inner.x, list.x + 2, "border plus one-cell padding");
        assert_eq!(inner.right() + 2, list.right());
    }

    #[test]
    fn mouse_focus_uses_the_same_board_gutters_and_settings_gap() {
        let size = Size::new(90, 24);
        let mut app = test_app();
        assert_eq!(focus_at(&app, size, 0, 3), None);
        assert_eq!(focus_at(&app, size, 1, 1), Some(Focus::Nav));
        assert_eq!(focus_at(&app, size, 1, 2), None);
        assert_eq!(focus_at(&app, size, 1, 3), Some(Focus::List));

        app.set_view(View::Settings);
        assert_eq!(focus_at(&app, size, 25, 6), None);
        assert_eq!(focus_at(&app, size, 26, 6), Some(Focus::Detail));
    }

    #[test]
    fn interactive_terminal_keeps_a_padded_sidebar_until_expanded() {
        let size = Size::new(60, 20);
        assert_eq!(terminal_preview_area(size, false), Rect::new(24, 4, 33, 13));
        assert_eq!(terminal_focus_at(size, false, 1, 4), Some(Focus::List));
        assert_eq!(terminal_focus_at(size, false, 22, 4), Some(Focus::Detail));

        assert_eq!(terminal_preview_area(size, true), Rect::new(3, 4, 54, 13));
        assert_eq!(terminal_focus_at(size, true, 1, 4), Some(Focus::Detail));
    }

    #[test]
    fn entering_a_session_keeps_the_exact_operator_grid_width_and_metadata() {
        let size = Size::new(140, 40);
        let control_area = board_area(terminal_content_area(size));
        let app = test_app();
        let (control_list, _) = panes(&app, control_area, Density::Wide);
        let (terminal_list, _) = terminal_panes(terminal_content_area(size), Density::Wide, false);
        assert_eq!(terminal_list, control_list);

        let control = render(test_app(), size.width, size.height);
        let mut terminal_app = test_app();
        terminal_app.mode = Mode::Terminal;
        terminal_app.focus = Focus::Detail;
        let terminal = render(terminal_app, size.width, size.height);
        for expected in [
            "moon",
            "hermes · active",
            "acme / luna / launch",
            "claude-sonnet-4-6 · TKN 12.3K",
        ] {
            assert!(control.contains(expected), "control missing {expected:?}");
            assert!(terminal.contains(expected), "terminal missing {expected:?}");
        }
    }

    #[test]
    fn pure_and_custom_themes_can_paint_the_full_terminal_canvas() {
        for theme in [Theme::PureBlack, Theme::PureWhite, Theme::Custom] {
            let mut app = test_app();
            app.theme = theme;
            let expected = app.palette().background;
            let backend = TestBackend::new(80, 20);
            let mut terminal = Terminal::new(backend).unwrap();
            terminal
                .draw(|frame| draw(frame, &mut app, SessionPreview::Unavailable))
                .unwrap();
            assert_eq!(terminal.backend().buffer()[(0, 0)].bg, expected);
        }
    }

    #[test]
    fn composio_mcp_detail_lists_redacted_connected_toolkits() {
        let mut app = test_app();
        app.snapshot.mcp_servers = vec![CapabilityRecord {
            name: "Composio".into(),
            sources: vec!["Composio".into()],
            transport: "CLI · link/tools list".into(),
            status: "connected".into(),
            toolkits: vec![
                CapabilityToolkitRecord {
                    name: "discordbot".into(),
                    status: "active".into(),
                    connections: 2,
                },
                CapabilityToolkitRecord {
                    name: "youtube".into(),
                    status: "expired".into(),
                    connections: 1,
                },
            ],
        }];
        app.set_view(View::Mcp);
        let output = render(app, 140, 28);
        for expected in [
            "MCP REGISTRY",
            "Sources",
            "Composio",
            "COMPOSIO TOOLKITS",
            "DISCORDBOT",
            "active · 2 connection(s)",
            "YOUTUBE",
            "expired · 1 connection(s)",
            "agk composio list",
        ] {
            assert!(output.contains(expected), "missing {expected:?}");
        }
    }

    #[test]
    fn history_preview_clamps_and_renders_from_the_live_tail() {
        let mut app = test_app();
        app.focus = Focus::Detail;
        app.preview_scroll = 3;
        let history = (0..80)
            .map(|line| format!("history-{line:02}"))
            .collect::<Vec<_>>();
        let backend = TestBackend::new(140, 24);
        let mut terminal = Terminal::new(backend).unwrap();
        terminal
            .draw(|frame| draw(frame, &mut app, SessionPreview::History(&history)))
            .unwrap();
        let output = terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(|cell| cell.symbol())
            .collect::<String>();
        assert!(output.contains("↑ 3 FROM LIVE"));
        assert!(output.contains("history-76"));
        assert!(!output.contains("history-79"));
        assert!(app.preview_max_scroll > 0);
    }

    #[test]
    fn terminal_workspace_history_uses_the_same_tail_relative_scroll() {
        let mut app = test_app();
        app.mode = Mode::Terminal;
        app.focus = Focus::Detail;
        app.preview_scroll = 4;
        let history = (0..80)
            .map(|line| format!("terminal-history-{line:02}"))
            .collect::<Vec<_>>();
        let backend = TestBackend::new(100, 24);
        let mut terminal = Terminal::new(backend).unwrap();
        terminal
            .draw(|frame| draw(frame, &mut app, SessionPreview::History(&history)))
            .unwrap();
        let output = terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(|cell| cell.symbol())
            .collect::<String>();
        assert!(output.contains("PAUSED · -4"));
        assert!(output.contains("terminal-history-75"));
        assert!(!output.contains("terminal-history-79"));
        assert!(app.preview_max_scroll > 0);
    }

    #[test]
    fn footer_and_empty_surfaces_keep_the_native_terminal_background() {
        let backend = TestBackend::new(80, 24);
        let mut terminal = Terminal::new(backend).unwrap();
        let mut app = test_app();
        terminal
            .draw(|frame| draw(frame, &mut app, SessionPreview::Unavailable))
            .unwrap();
        let buffer = terminal.backend().buffer();
        assert_eq!(buffer[(0, 23)].symbol(), " ");
        assert_eq!(buffer[(0, 23)].bg, Color::Reset);
        assert_eq!(buffer[(1, 23)].symbol(), "A");
        assert_eq!(buffer[(1, 23)].bg, Color::Reset);
        assert_eq!(buffer[(79, 23)].bg, Color::Reset);
    }

    #[test]
    fn mobile_footer_keeps_all_metrics_and_a_gap_before_live() {
        let mut app = test_app();
        app.snapshot.runtimes[0].name = "operator-agk-tui-ultra".into();
        app.footer.git_branch = Some("agk/finalize-runtime-contract".into());
        let output = render(app, 60, 20);
        let live = output.find("● 1 LIVE").expect("live counter");
        assert_eq!(output[..live].chars().next_back(), Some(' '));
        for metric in ["TKN", "RAM", "CPU", "DISK"] {
            assert!(output.contains(metric), "missing compact {metric}");
        }
    }

    #[test]
    fn narrow_footer_never_renders_empty_context_separators() {
        let output = render(test_app(), 50, 20);
        assert!(output.contains("AGK "));
        assert!(!output.contains("AGK ·  ·"));
    }
}
