use crate::{
    data::{
        AgentRecord, CapabilityRecord, ControlObject, OsPackage, ProviderRecord, RegistrySnapshot,
        RuleRecord, RuntimeRecord, SkillRecord,
    },
    system_info::FooterSnapshot,
    theme::{CustomColors, Palette, Preferences, Theme},
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum View {
    Sessions,
    Projects,
    Agents,
    Os,
    Mcp,
    Skills,
    Rules,
    Settings,
}

impl View {
    pub const ALL: [Self; 8] = [
        Self::Sessions,
        Self::Projects,
        Self::Agents,
        Self::Os,
        Self::Mcp,
        Self::Skills,
        Self::Rules,
        Self::Settings,
    ];

    pub const fn label(self) -> &'static str {
        match self {
            Self::Sessions => "Sessions",
            Self::Projects => "Projects",
            Self::Agents => "Agents",
            Self::Os => "OS",
            Self::Mcp => "MCP",
            Self::Skills => "Skills",
            Self::Rules => "Rules",
            Self::Settings => "Settings",
        }
    }

    pub const fn hotkey(self) -> &'static str {
        match self {
            Self::Sessions => "1",
            Self::Projects => "2",
            Self::Agents => "3",
            Self::Os => "4",
            Self::Mcp => "5",
            Self::Skills => "6",
            Self::Rules => "7",
            Self::Settings => "8",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Focus {
    Nav,
    List,
    Detail,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Mode {
    Control,
    Terminal,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Density {
    Compact,
    Standard,
    Wide,
}

pub fn density(width: u16, height: u16) -> Density {
    if width < 72 || height < 18 {
        Density::Compact
    } else if width < 120 || height < 28 {
        Density::Standard
    } else {
        Density::Wide
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SettingsSection {
    Appearance,
    Providers,
    Sessions,
    Runtime,
    System,
    Help,
    About,
}

impl SettingsSection {
    pub const ALL: [Self; 7] = [
        Self::Appearance,
        Self::Providers,
        Self::Sessions,
        Self::Runtime,
        Self::System,
        Self::Help,
        Self::About,
    ];

    pub const fn label(self) -> &'static str {
        match self {
            Self::Appearance => "Appearance",
            Self::Providers => "Providers",
            Self::Sessions => "Sessions",
            Self::Runtime => "Runtime",
            Self::System => "System",
            Self::Help => "Help",
            Self::About => "About",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SessionKind {
    Hermes,
    Claude,
    Codex,
    OpenRouter,
    OpenCode,
    Shell,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SessionTarget {
    pub id: String,
    pub name: String,
    pub rmux_session: String,
    pub managed: bool,
    pub native_session: Option<String>,
    pub hermes_profile: Option<String>,
    pub cwd: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AgentConversationContext {
    pub agent_id: String,
    pub agent_name: String,
    pub runtime_prefix: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct OsConversationContext {
    pub reference: String,
    pub agent_id: String,
    pub runtime_prefix: String,
}

impl From<&RuntimeRecord> for SessionTarget {
    fn from(runtime: &RuntimeRecord) -> Self {
        Self {
            id: runtime.id.clone(),
            name: runtime.name.clone(),
            rmux_session: runtime.rmux_session.clone(),
            managed: runtime.managed,
            native_session: runtime.native_session.clone(),
            hermes_profile: runtime.hermes_profile.clone(),
            cwd: runtime.cwd.clone(),
        }
    }
}

impl SessionKind {
    pub const ALL: [Self; 6] = [
        Self::Hermes,
        Self::Codex,
        Self::Claude,
        Self::OpenCode,
        Self::OpenRouter,
        Self::Shell,
    ];

    pub const fn slug(self) -> &'static str {
        match self {
            Self::Hermes => "hermes",
            Self::Claude => "claude",
            Self::Codex => "codex",
            Self::OpenRouter => "openrouter",
            Self::OpenCode => "opencode",
            Self::Shell => "shell",
        }
    }

    pub const fn label(self) -> &'static str {
        match self {
            Self::Hermes => "Hermes",
            Self::Claude => "Claude",
            Self::Codex => "Codex",
            Self::OpenRouter => "OpenRouter",
            Self::OpenCode => "OpenCode",
            Self::Shell => "Terminal",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Overlay {
    None,
    Search {
        value: String,
        original: String,
    },
    Palette {
        query: String,
        selected: usize,
    },
    NewKind {
        selected: usize,
    },
    NewName {
        kind: SessionKind,
        value: String,
    },
    NewAgentConversation {
        agent_id: String,
        runtime_prefix: String,
        value: String,
    },
    RenameSession {
        target: SessionTarget,
        value: String,
    },
    CustomTheme {
        original: CustomColors,
        working: CustomColors,
        selected: usize,
        value: String,
        fresh: bool,
    },
}

impl Overlay {
    pub const fn is_open(&self) -> bool {
        !matches!(self, Self::None)
    }
}

#[derive(Debug)]
pub struct App {
    /// RMUX session hosting this TUI, when AGK itself was opened from rmux.
    /// It remains visible in the session list but cannot be mirrored back into
    /// itself, which avoids recursion without hiding unrelated `*-control`
    /// workspaces.
    pub current_rmux_session: Option<String>,
    pub mode: Mode,
    pub view: View,
    pub focus: Focus,
    pub snapshot: RegistrySnapshot,
    pub selected: usize,
    pub query: String,
    pub overlay: Overlay,
    pub expanded: bool,
    pub preferences: Preferences,
    pub theme: Theme,
    pub committed_theme: Theme,
    pub settings_section: usize,
    pub provider_selected: usize,
    pub detail_scroll: u16,
    pub status: Option<String>,
    pub footer: FooterSnapshot,
    pub preview_width: u16,
    pub preview_height: u16,
    /// Lines above the live tail in the selected RMUX pane.
    pub preview_scroll: u16,
    /// Renderer-published clamp bound for `preview_scroll`.
    pub preview_max_scroll: u16,
    /// Active specialized-agent conversation browser.
    pub agent_conversations: Option<AgentConversationContext>,
    /// Active OS conversation browser. `None` means the normal OS registry.
    pub os_conversations: Option<OsConversationContext>,
    last_session: Option<String>,
}

impl App {
    pub fn new(preferences: Preferences) -> Self {
        let theme = preferences.theme;
        Self {
            current_rmux_session: None,
            mode: Mode::Control,
            view: View::Sessions,
            focus: Focus::List,
            snapshot: RegistrySnapshot::default(),
            selected: 0,
            query: String::new(),
            overlay: Overlay::None,
            expanded: false,
            preferences,
            theme,
            committed_theme: theme,
            settings_section: 0,
            provider_selected: 0,
            detail_scroll: 0,
            status: None,
            footer: FooterSnapshot::default(),
            preview_width: 0,
            preview_height: 0,
            preview_scroll: 0,
            preview_max_scroll: 0,
            agent_conversations: None,
            os_conversations: None,
            last_session: None,
        }
    }

    pub fn set_view(&mut self, view: View) {
        if self.view == View::Sessions
            && let Some(name) = self.current_session().map(|item| item.name.clone())
        {
            self.last_session = Some(name);
        }
        if self.view == View::Settings && view != View::Settings {
            self.cancel_theme_preview();
        }
        self.view = view;
        if view != View::Agents {
            self.agent_conversations = None;
        }
        if view != View::Os {
            self.os_conversations = None;
        }
        self.query.clear();
        self.selected = if view == View::Sessions {
            self.last_session
                .as_deref()
                .and_then(|name| {
                    self.snapshot
                        .runtimes
                        .iter()
                        .position(|item| item.name == name)
                })
                .unwrap_or_default()
        } else {
            0
        };
        self.detail_scroll = 0;
        self.preview_scroll = 0;
        self.preview_max_scroll = 0;
        self.expanded = false;
        self.focus = Focus::List;
    }

    pub fn next_view(&mut self) {
        let index = View::ALL
            .iter()
            .position(|view| *view == self.view)
            .unwrap_or(0);
        self.set_view(View::ALL[(index + 1) % View::ALL.len()]);
    }

    pub fn previous_view(&mut self) {
        let index = View::ALL
            .iter()
            .position(|view| *view == self.view)
            .unwrap_or(0);
        self.set_view(View::ALL[(index + View::ALL.len() - 1) % View::ALL.len()]);
    }

    pub fn set_snapshot(&mut self, snapshot: RegistrySnapshot) {
        let identity = self.current_key();
        self.snapshot = snapshot;
        self.provider_selected = self
            .provider_selected
            .min(self.snapshot.providers.len().saturating_sub(1));
        self.selected = identity
            .as_ref()
            .and_then(|key| {
                self.visible_keys()
                    .iter()
                    .position(|candidate| candidate == key)
            })
            .unwrap_or_else(|| self.selected.min(self.visible_len().saturating_sub(1)));
        if identity != self.current_key() {
            self.preview_scroll = 0;
            self.preview_max_scroll = 0;
        }
        self.remember_current_session();
    }

    pub fn visible_len(&self) -> usize {
        match self.view {
            View::Sessions => self.filtered_sessions().count(),
            View::Projects => self.filtered_objects().count(),
            View::Agents if self.agent_conversations.is_some() => {
                self.filtered_agent_conversations().count()
            }
            View::Agents => self.filtered_agents().count(),
            View::Os if self.os_conversations.is_some() => self.filtered_os_conversations().count(),
            View::Os => self.filtered_os().count(),
            View::Mcp => self.filtered_mcp().count(),
            View::Skills => self.filtered_skills().count(),
            View::Rules => self.filtered_rules().count(),
            View::Settings => SettingsSection::ALL.len(),
        }
    }

    pub fn select_next(&mut self) {
        if self.view == View::Settings && self.focus == Focus::List {
            self.settings_section =
                (self.settings_section + 1).min(SettingsSection::ALL.len().saturating_sub(1));
            return;
        }
        let len = self.visible_len();
        if len > 0 {
            self.selected = (self.selected + 1).min(len - 1);
            self.detail_scroll = 0;
            self.preview_scroll = 0;
            self.preview_max_scroll = 0;
            self.remember_current_session();
        }
    }

    pub fn select_previous(&mut self) {
        if self.view == View::Settings && self.focus == Focus::List {
            self.settings_section = self.settings_section.saturating_sub(1);
            return;
        }
        self.selected = self.selected.saturating_sub(1);
        self.detail_scroll = 0;
        self.preview_scroll = 0;
        self.preview_max_scroll = 0;
        self.remember_current_session();
    }

    pub fn current_session(&self) -> Option<&RuntimeRecord> {
        self.filtered_sessions().nth(self.selected)
    }

    pub fn current_session_target(&self) -> Option<SessionTarget> {
        self.current_session().map(SessionTarget::from)
    }

    pub fn selected_session_name(&self) -> Option<&str> {
        if self.view == View::Sessions {
            self.current_session().map(|item| item.name.as_str())
        } else {
            self.last_session.as_deref()
        }
    }

    pub fn selected_is_current_rmux_session(&self) -> bool {
        self.current_session().is_some_and(|runtime| {
            self.current_rmux_session.as_deref() == Some(runtime.rmux_session.as_str())
        })
    }

    pub fn scroll_preview_up(&mut self, lines: u16) {
        self.preview_scroll = self.preview_scroll.saturating_add(lines.max(1));
        if self.preview_max_scroll > 0 {
            self.preview_scroll = self.preview_scroll.min(self.preview_max_scroll);
        }
    }

    pub fn scroll_preview_down(&mut self, lines: u16) {
        self.preview_scroll = self.preview_scroll.saturating_sub(lines.max(1));
    }

    pub fn scroll_preview_home(&mut self) {
        self.preview_scroll = if self.preview_max_scroll > 0 {
            self.preview_max_scroll
        } else {
            u16::MAX
        };
    }

    pub fn scroll_preview_live(&mut self) {
        self.preview_scroll = 0;
    }

    pub fn current_object(&self) -> Option<&ControlObject> {
        self.filtered_objects().nth(self.selected)
    }

    pub fn current_agent(&self) -> Option<&AgentRecord> {
        if let Some(context) = &self.agent_conversations {
            return self
                .snapshot
                .agents
                .iter()
                .find(|agent| agent.id == context.agent_id);
        }
        self.filtered_agents().nth(self.selected)
    }

    pub fn enter_agent_conversations(&mut self) -> bool {
        let Some(agent) = self.current_agent() else {
            return false;
        };
        self.agent_conversations = Some(AgentConversationContext {
            agent_id: agent.id.clone(),
            agent_name: agent.name.clone(),
            runtime_prefix: agent.runtime_name.clone(),
        });
        self.selected = 0;
        self.query.clear();
        self.focus = Focus::List;
        true
    }

    pub fn leave_agent_conversations(&mut self) -> bool {
        if self.agent_conversations.take().is_none() {
            return false;
        }
        self.selected = 0;
        self.query.clear();
        self.focus = Focus::List;
        true
    }

    pub fn filtered_agent_conversations(&self) -> impl Iterator<Item = &RuntimeRecord> {
        let prefix = self
            .agent_conversations
            .as_ref()
            .map(|context| context.runtime_prefix.as_str());
        self.snapshot.runtimes.iter().filter(move |runtime| {
            let Some(prefix) = prefix else { return false };
            (runtime.name == prefix || runtime.name.starts_with(&format!("{prefix}-")))
                && matches_query(
                    &self.query,
                    &[&runtime.name, &runtime.kind, &runtime.status],
                )
        })
    }

    pub fn current_agent_conversation(&self) -> Option<&RuntimeRecord> {
        self.filtered_agent_conversations().nth(self.selected)
    }

    pub fn current_agent_conversation_target(&self) -> Option<SessionTarget> {
        self.current_agent_conversation().map(SessionTarget::from)
    }

    pub fn current_os(&self) -> Option<&OsPackage> {
        self.filtered_os().nth(self.selected)
    }

    /// Resolve the catalog agent responsible for the selected OS. Explicit
    /// versioned `os` bindings win, then manifest agent IDs, with the bundled
    /// OS lifecycle agent as a compatibility owner for older packages.
    pub fn current_os_agent(&self) -> Option<&AgentRecord> {
        let package = self.current_os()?;
        let versioned = format!("{}@{}", package.id, package.version);
        self.snapshot
            .agents
            .iter()
            .find(|agent| {
                agent
                    .os
                    .iter()
                    .any(|reference| reference == &versioned || reference == &package.id)
            })
            .or_else(|| {
                self.snapshot.agents.iter().find(|agent| {
                    package
                        .agents
                        .iter()
                        .any(|owner| owner == &agent.id || owner.replace('_', "-") == agent.id)
                })
            })
            .or_else(|| {
                self.snapshot
                    .agents
                    .iter()
                    .find(|agent| agent.id == "master-os-builder")
            })
    }

    pub fn enter_os_conversations(&mut self) -> bool {
        let Some(package) = self.current_os() else {
            return false;
        };
        let reference = format!("{}@{}", package.id, package.version);
        let Some(agent) = self.current_os_agent() else {
            return false;
        };
        self.os_conversations = Some(OsConversationContext {
            reference,
            agent_id: agent.id.clone(),
            runtime_prefix: agent.runtime_name.clone(),
        });
        self.selected = 0;
        self.query.clear();
        self.focus = Focus::List;
        true
    }

    pub fn leave_os_conversations(&mut self) -> bool {
        if self.os_conversations.take().is_none() {
            return false;
        }
        self.selected = 0;
        self.query.clear();
        self.focus = Focus::List;
        true
    }

    pub fn filtered_os_conversations(&self) -> impl Iterator<Item = &RuntimeRecord> {
        let prefix = self
            .os_conversations
            .as_ref()
            .map(|context| context.runtime_prefix.as_str());
        self.snapshot.runtimes.iter().filter(move |runtime| {
            let Some(prefix) = prefix else { return false };
            (runtime.name == prefix || runtime.name.starts_with(&format!("{prefix}-")))
                && matches_query(
                    &self.query,
                    &[&runtime.name, &runtime.kind, &runtime.status],
                )
        })
    }

    pub fn current_os_conversation(&self) -> Option<&RuntimeRecord> {
        self.filtered_os_conversations().nth(self.selected)
    }

    pub fn current_os_conversation_target(&self) -> Option<SessionTarget> {
        self.current_os_conversation().map(SessionTarget::from)
    }

    pub fn os_context_package(&self) -> Option<&OsPackage> {
        let reference = &self.os_conversations.as_ref()?.reference;
        self.snapshot
            .os_packages
            .iter()
            .find(|package| format!("{}@{}", package.id, package.version) == *reference)
    }

    pub fn current_mcp(&self) -> Option<&CapabilityRecord> {
        self.filtered_mcp().nth(self.selected)
    }

    pub fn current_skill(&self) -> Option<&SkillRecord> {
        self.filtered_skills().nth(self.selected)
    }

    pub fn current_rule(&self) -> Option<&RuleRecord> {
        self.filtered_rules().nth(self.selected)
    }

    pub fn current_provider(&self) -> Option<&ProviderRecord> {
        self.snapshot.providers.get(self.provider_selected)
    }

    pub fn select_next_provider(&mut self) {
        self.provider_selected =
            (self.provider_selected + 1).min(self.snapshot.providers.len().saturating_sub(1));
    }

    pub fn select_previous_provider(&mut self) {
        self.provider_selected = self.provider_selected.saturating_sub(1);
    }

    pub fn filtered_sessions(&self) -> impl Iterator<Item = &RuntimeRecord> {
        self.snapshot.runtimes.iter().filter(|item| {
            matches_query(
                &self.query,
                &[
                    &item.name,
                    &item.kind,
                    &item.status,
                    item.project.as_deref().unwrap_or(""),
                    item.client.as_deref().unwrap_or(""),
                    item.mission.as_deref().unwrap_or(""),
                    &item.cwd,
                ],
            )
        })
    }

    pub fn filtered_objects(&self) -> impl Iterator<Item = &ControlObject> {
        self.snapshot.objects.iter().filter(|item| {
            matches_query(
                &self.query,
                &[
                    &item.id,
                    &item.kind,
                    &item.slug,
                    &item.name,
                    &item.status,
                    item.path.as_deref().unwrap_or(""),
                ],
            )
        })
    }

    pub fn filtered_agents(&self) -> impl Iterator<Item = &AgentRecord> {
        self.snapshot.agents.iter().filter(|item| {
            matches_query(
                &self.query,
                &[
                    &item.id,
                    &item.name,
                    &item.description,
                    &item.status,
                    &item.runtime,
                ],
            )
        })
    }

    pub fn filtered_os(&self) -> impl Iterator<Item = &OsPackage> {
        self.snapshot.os_packages.iter().filter(|item| {
            matches_query(
                &self.query,
                &[&item.id, &item.name, &item.version, &item.description],
            )
        })
    }

    pub fn filtered_mcp(&self) -> impl Iterator<Item = &CapabilityRecord> {
        self.snapshot.mcp_servers.iter().filter(|item| {
            let sources = item.sources.join(" ");
            matches_query(
                &self.query,
                &[&item.name, &sources, &item.transport, &item.status],
            )
        })
    }

    pub fn filtered_skills(&self) -> impl Iterator<Item = &SkillRecord> {
        self.snapshot
            .skills
            .iter()
            .filter(|item| matches_query(&self.query, &[&item.name, &item.source, &item.status]))
    }

    pub fn filtered_rules(&self) -> impl Iterator<Item = &RuleRecord> {
        self.snapshot.rules.iter().filter(|item| {
            matches_query(
                &self.query,
                &[
                    &item.id,
                    &item.title,
                    &item.content,
                    &item.providers.join(" "),
                ],
            )
        })
    }

    pub fn current_key(&self) -> Option<String> {
        match self.view {
            View::Sessions => self
                .current_session()
                .map(|item| format!("runtime:{}", item.name)),
            View::Projects => self
                .current_object()
                .map(|item| format!("object:{}", item.id)),
            View::Agents if self.agent_conversations.is_some() => self
                .current_agent_conversation()
                .map(|item| format!("runtime:{}", item.name)),
            View::Agents => self
                .current_agent()
                .map(|item| format!("agent:{}", item.id)),
            View::Os if self.os_conversations.is_some() => self
                .current_os_conversation()
                .map(|item| format!("runtime:{}", item.name)),
            View::Os => self
                .current_os()
                .map(|item| format!("os:{}@{}", item.id, item.version)),
            View::Mcp => self.current_mcp().map(|item| format!("mcp:{}", item.name)),
            View::Skills => self
                .current_skill()
                .map(|item| format!("skill:{}", item.name)),
            View::Rules => self.current_rule().map(|item| format!("rule:{}", item.id)),
            _ => None,
        }
    }

    fn visible_keys(&self) -> Vec<String> {
        match self.view {
            View::Sessions => self
                .filtered_sessions()
                .map(|item| format!("runtime:{}", item.name))
                .collect(),
            View::Projects => self
                .filtered_objects()
                .map(|item| format!("object:{}", item.id))
                .collect(),
            View::Agents if self.agent_conversations.is_some() => self
                .filtered_agent_conversations()
                .map(|item| format!("runtime:{}", item.name))
                .collect(),
            View::Agents => self
                .filtered_agents()
                .map(|item| format!("agent:{}", item.id))
                .collect(),
            View::Os if self.os_conversations.is_some() => self
                .filtered_os_conversations()
                .map(|item| format!("runtime:{}", item.name))
                .collect(),
            View::Os => self
                .filtered_os()
                .map(|item| format!("os:{}@{}", item.id, item.version))
                .collect(),
            View::Mcp => self
                .filtered_mcp()
                .map(|item| format!("mcp:{}", item.name))
                .collect(),
            View::Skills => self
                .filtered_skills()
                .map(|item| format!("skill:{}", item.name))
                .collect(),
            View::Rules => self
                .filtered_rules()
                .map(|item| format!("rule:{}", item.id))
                .collect(),
            _ => Vec::new(),
        }
    }

    pub fn tab(&mut self, detail_available: bool) {
        self.focus = match (self.view, self.focus, detail_available) {
            (_, Focus::List, true) => Focus::Detail,
            _ => Focus::List,
        };
    }

    pub fn back_tab(&mut self, detail_available: bool) {
        self.focus = match (self.view, self.focus, detail_available) {
            (_, Focus::Detail, _) => Focus::List,
            (_, _, true) => Focus::Detail,
            _ => Focus::List,
        };
    }

    pub fn settings_section(&self) -> SettingsSection {
        SettingsSection::ALL[self.settings_section.min(SettingsSection::ALL.len() - 1)]
    }

    pub fn preview_next_theme(&mut self) {
        self.theme = self.theme.next();
    }
    pub fn preview_previous_theme(&mut self) {
        self.theme = self.theme.previous();
    }

    pub fn palette(&self) -> Palette {
        self.theme
            .palette_with_custom(self.preferences.custom_colors)
    }

    pub fn commit_theme(&mut self) {
        self.committed_theme = self.theme;
        self.preferences.theme = self.theme;
        self.status = Some(format!("Theme saved: {}", self.theme.name()));
    }

    pub fn cancel_theme_preview(&mut self) {
        self.theme = self.committed_theme;
    }

    pub fn select_session_by_name(&mut self, name: &str) -> bool {
        self.query.clear();
        self.view = View::Sessions;
        self.focus = Focus::List;
        self.expanded = false;
        if let Some(index) = self
            .snapshot
            .runtimes
            .iter()
            .position(|item| item.name == name)
        {
            self.selected = index;
            self.remember_current_session();
            true
        } else {
            self.selected = 0;
            false
        }
    }

    fn remember_current_session(&mut self) {
        if self.view == View::Sessions
            && let Some(name) = self.current_session().map(|item| item.name.clone())
        {
            self.last_session = Some(name);
        }
    }
}

fn matches_query(query: &str, values: &[&str]) -> bool {
    let query = query.trim().to_ascii_lowercase();
    if query.is_empty() {
        return true;
    }
    let haystack = values.join(" ").to_ascii_lowercase();
    query.split_whitespace().all(|term| haystack.contains(term))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn app() -> App {
        App::new(Preferences::default())
    }

    fn runtime(name: &str) -> RuntimeRecord {
        RuntimeRecord {
            id: format!("runtime-{name}"),
            name: name.into(),
            kind: "hermes".into(),
            environment: "mission".into(),
            client: None,
            project: None,
            mission: None,
            native_session: None,
            hermes_profile: None,
            rmux_session: name.into(),
            cwd: "/work".into(),
            status: "active".into(),
            created_at: 1.0,
            last_activity: 2.0,
            tokens: 0,
            model_usage: Vec::new(),
            managed: true,
            live: true,
        }
    }

    fn agent(id: &str, os: &[&str]) -> AgentRecord {
        AgentRecord {
            id: id.into(),
            name: id.into(),
            version: "1.0.0".into(),
            description: String::new(),
            scope: vec!["mission".into()],
            runtime: "hermes".into(),
            profile: Some("mission-os".into()),
            os: os.iter().map(|value| (*value).into()).collect(),
            catalog_path: "/catalog".into(),
            runtime_name: format!("mission-{id}"),
            runtime_id: None,
            status: "available".into(),
            live: false,
            available: true,
        }
    }

    fn os_package(id: &str, version: &str) -> OsPackage {
        OsPackage {
            id: id.into(),
            name: id.into(),
            version: version.into(),
            description: String::new(),
            scope: vec!["mission".into()],
            dependencies: Vec::new(),
            capabilities: Vec::new(),
            skills: Vec::new(),
            workflows: Vec::new(),
            agents: Vec::new(),
            tools: Vec::new(),
            commands: Vec::new(),
            knowledge: Vec::new(),
            evals: Vec::new(),
            assignments: vec!["profile:mission".into()],
            available: true,
        }
    }

    #[test]
    fn responsive_breakpoints_are_deterministic() {
        assert_eq!(density(60, 30), Density::Compact);
        assert_eq!(density(90, 24), Density::Standard);
        assert_eq!(density(140, 40), Density::Wide);
    }

    #[test]
    fn tab_skips_navigation_and_toggles_list_with_detail() {
        let mut app = app();
        app.focus = Focus::Nav;
        app.tab(true);
        assert_eq!(app.focus, Focus::List);
        app.tab(true);
        assert_eq!(app.focus, Focus::Detail);
        app.tab(true);
        assert_eq!(app.focus, Focus::List);
        app.back_tab(true);
        assert_eq!(app.focus, Focus::Detail);
    }

    #[test]
    fn navigation_and_theme_preview_have_cancel_commit_contracts() {
        let mut app = app();
        app.focus = Focus::Nav;
        app.next_view();
        assert_eq!(app.view, View::Projects);
        assert_eq!(app.focus, Focus::List);
        app.set_view(View::Settings);
        let original = app.theme;
        app.preview_next_theme();
        assert_ne!(app.theme, original);
        app.cancel_theme_preview();
        assert_eq!(app.theme, original);
        app.preview_next_theme();
        app.commit_theme();
        assert_eq!(app.preferences.theme, app.theme);
    }

    #[test]
    fn search_is_case_insensitive_and_requires_all_terms() {
        assert!(matches_query("MOON codex", &["moon-base", "Codex"]));
        assert!(!matches_query("moon hermes", &["moon-base", "Codex"]));
    }

    #[test]
    fn selected_session_survives_other_views_and_filters_do_not_leak() {
        let mut app = app();
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("alpha"), runtime("bravo")],
            ..RegistrySnapshot::default()
        });
        app.select_next();
        app.query = "bravo".into();
        app.set_view(View::Projects);
        assert_eq!(app.selected_session_name(), Some("bravo"));
        assert!(app.query.is_empty());
        app.set_view(View::Sessions);
        assert_eq!(
            app.current_session().map(|item| item.name.as_str()),
            Some("bravo")
        );
    }

    #[test]
    fn preview_scrollback_is_tail_relative_and_resets_on_selection_change() {
        let mut app = app();
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("alpha"), runtime("bravo")],
            ..RegistrySnapshot::default()
        });
        app.preview_max_scroll = 100;
        app.scroll_preview_up(12);
        assert_eq!(app.preview_scroll, 12);
        app.scroll_preview_down(5);
        assert_eq!(app.preview_scroll, 7);
        app.scroll_preview_home();
        assert_eq!(app.preview_scroll, 100);
        app.select_next();
        assert_eq!(app.preview_scroll, 0);
        app.scroll_preview_up(4);
        app.scroll_preview_live();
        assert_eq!(app.preview_scroll, 0);
    }

    #[test]
    fn selected_os_resolves_its_explicit_profile_agent_before_fallbacks() {
        let mut app = app();
        app.set_snapshot(RegistrySnapshot {
            agents: vec![
                agent("master-os-builder", &[]),
                agent("mission-specialist", &["mission-os@2.1.0"]),
            ],
            os_packages: vec![os_package("mission-os", "2.1.0")],
            ..RegistrySnapshot::default()
        });
        app.set_view(View::Os);

        let owner = app.current_os_agent().expect("OS owner");
        assert_eq!(owner.id, "mission-specialist");
        assert_eq!(owner.profile.as_deref(), Some("mission-os"));
    }
}
