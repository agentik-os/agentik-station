//! Read-only adapters for Agentik, RMUX, and Hermes state.
//!
//! The native TUI owns presentation and RMUX owns process state.  This module
//! only joins those live RMUX session names with the durable Agentik/Hermes
//! registries; it never creates, migrates, or mutates their files.

use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OpenFlags, params_from_iter};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use serde_yaml::Value as YamlValue;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::env;
use std::fs;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

const TERMINAL_RUNTIME_STATES: &[&str] = &["complete", "failed", "archived"];
const MAX_SKILLS_PER_SOURCE: usize = 500;

/// A durable Agentik runtime enriched with current RMUX and Hermes state.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RuntimeRecord {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub environment: String,
    pub client: Option<String>,
    pub project: Option<String>,
    pub mission: Option<String>,
    pub native_session: Option<String>,
    /// Named Hermes profile that owns `native_session`; `None` is the main
    /// profile in this Linux user's trust boundary.
    #[serde(default)]
    pub hermes_profile: Option<String>,
    pub rmux_session: String,
    pub cwd: String,
    pub status: String,
    pub created_at: f64,
    pub last_activity: f64,
    /// Input + output tokens across every attributed model in this runtime.
    pub tokens: u64,
    /// Exact Hermes accounting rows, ordered by most recently used model.
    #[serde(default)]
    pub model_usage: Vec<ModelUsageRecord>,
    /// False for a live RMUX session that has no Agentik registry row.
    pub managed: bool,
    /// Current process truth supplied by RMUX, independent of stored status.
    pub live: bool,
}

/// Token accounting for one model/provider pair. Cache and reasoning tokens
/// stay separate because adding them to input/output would double count on
/// providers that already include cached context in their input accounting.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct ModelUsageRecord {
    pub model: String,
    pub provider: String,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_read_tokens: u64,
    pub cache_write_tokens: u64,
    pub reasoning_tokens: u64,
    pub api_calls: u64,
    pub last_used_at: f64,
}

impl ModelUsageRecord {
    pub fn io_tokens(&self) -> u64 {
        self.input_tokens.saturating_add(self.output_tokens)
    }
}

/// A project hierarchy object from the Agentik control registry.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ControlObject {
    pub id: String,
    pub environment: String,
    pub kind: String,
    pub slug: String,
    pub name: String,
    pub parent_id: Option<String>,
    pub status: String,
    pub path: Option<String>,
    pub metadata: JsonValue,
    pub created_at: f64,
    pub updated_at: f64,
}

/// A bundled or overridden specialized-agent definition and its runtime state.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentRecord {
    pub id: String,
    pub name: String,
    pub version: String,
    pub description: String,
    pub scope: Vec<String>,
    pub runtime: String,
    /// Optional isolated Hermes profile declared by the agent catalog.
    pub profile: Option<String>,
    /// Versioned OS references owned by this specialized agent.
    pub os: Vec<String>,
    pub catalog_path: String,
    pub runtime_name: String,
    pub runtime_id: Option<String>,
    pub status: String,
    pub live: bool,
    pub available: bool,
}

/// An installed Agentik operative-system package.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct OsPackage {
    pub id: String,
    pub name: String,
    pub version: String,
    pub description: String,
    pub scope: Vec<String>,
    pub dependencies: Vec<String>,
    pub capabilities: Vec<String>,
    pub skills: Vec<String>,
    pub workflows: Vec<String>,
    pub agents: Vec<String>,
    pub tools: Vec<String>,
    pub commands: Vec<String>,
    pub knowledge: Vec<String>,
    pub evals: Vec<String>,
    /// Stable `scope:target` strings from `os-assignments.yaml`.
    pub assignments: Vec<String>,
    pub available: bool,
}

/// A deliberately redacted capability identity.  MCP command lines, URLs,
/// headers, environment variables, and credentials are never represented.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CapabilityRecord {
    pub name: String,
    /// Provider registries that currently declare this MCP server. The list
    /// contains identities only; provider configuration stays redacted.
    #[serde(default)]
    pub sources: Vec<String>,
    pub transport: String,
    pub status: String,
    #[serde(default)]
    pub toolkits: Vec<CapabilityToolkitRecord>,
}

/// A redacted Composio toolkit connection summary nested under its MCP entry.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CapabilityToolkitRecord {
    pub name: String,
    pub status: String,
    pub connections: u64,
}

/// An installed skill identity.  Skill contents are intentionally not read.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct SkillRecord {
    pub name: String,
    pub source: String,
    pub status: String,
}

/// One operator rule projected into every supported provider runtime.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuleRecord {
    pub id: String,
    pub title: String,
    pub content: String,
    #[serde(default)]
    pub providers: Vec<String>,
    #[serde(default = "enabled_by_default")]
    pub enabled: bool,
    #[serde(default)]
    pub source: String,
}

const fn enabled_by_default() -> bool {
    true
}

/// Local provider readiness without exposing credentials or account data.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProviderRecord {
    pub id: String,
    pub name: String,
    pub installed: bool,
    pub configured: bool,
    pub command: String,
}

/// Redacted multi-user runtime health published by the root topology broker.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProfileRecord {
    pub profile_id: String,
    pub display_name: String,
    pub runtime_driver: String,
    pub linux_user: String,
    pub workspace_exists: bool,
    pub hermes_state_exists: bool,
    pub rmux_sessions: Option<u64>,
    pub gateway_state: Option<String>,
    pub discord_state: Option<String>,
    pub runtime_identity_matches: bool,
}

/// One coherent, read-only view of the registries used by the native TUI.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct RegistrySnapshot {
    pub runtimes: Vec<RuntimeRecord>,
    pub objects: Vec<ControlObject>,
    pub agents: Vec<AgentRecord>,
    pub os_packages: Vec<OsPackage>,
    pub mcp_servers: Vec<CapabilityRecord>,
    pub skills: Vec<SkillRecord>,
    pub rules: Vec<RuleRecord>,
    pub providers: Vec<ProviderRecord>,
    pub profiles: Vec<ProfileRecord>,
    /// Sum of input + output tokens from unique attributed Hermes sessions.
    pub token_total: u64,
    /// Exact per-model accounting, aggregated across unique attributed
    /// sessions and ordered by most recently used model.
    pub model_usage: Vec<ModelUsageRecord>,
    pub warnings: Vec<String>,
}

/// All filesystem inputs.  Keeping them explicit makes the adapters hermetic
/// in tests and usable for non-default homes without changing process state.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RegistryPaths {
    pub runtime_db: PathBuf,
    pub control_db: PathBuf,
    pub hermes_state_db: PathBuf,
    pub hermes_config: PathBuf,
    pub hermes_env: PathBuf,
    pub claude_config: PathBuf,
    pub claude_credentials: PathBuf,
    pub codex_config: PathBuf,
    pub codex_auth: PathBuf,
    pub opencode_config: PathBuf,
    pub opencode_config_fallback: PathBuf,
    pub agent_catalog: PathBuf,
    pub os_registry: PathBuf,
    pub os_assignments: PathBuf,
    pub hermes_skills: PathBuf,
    pub claude_skills: PathBuf,
    pub codex_skills: PathBuf,
    pub rules_config: PathBuf,
    pub composio_auth: PathBuf,
    pub composio_inventory: PathBuf,
    pub topology_status: PathBuf,
    pub executable_paths: Vec<PathBuf>,
}

impl RegistryPaths {
    /// Build default paths beneath a supplied home, while injecting the two
    /// roots that may be bundled outside that home.
    pub fn for_home(
        home: impl AsRef<Path>,
        agent_catalog: impl Into<PathBuf>,
        os_registry: impl Into<PathBuf>,
    ) -> Self {
        let home = home.as_ref();
        let agentik = home.join(".agentik");
        let hermes = home.join(".hermes");
        Self {
            runtime_db: agentik.join("runtime.db"),
            control_db: agentik.join("control.db"),
            hermes_state_db: hermes.join("state.db"),
            hermes_config: hermes.join("config.yaml"),
            hermes_env: hermes.join(".env"),
            claude_config: home.join(".claude.json"),
            claude_credentials: home.join(".claude/.credentials.json"),
            codex_config: home.join(".codex/config.toml"),
            codex_auth: home.join(".codex/auth.json"),
            opencode_config: home.join(".config/opencode/opencode.jsonc"),
            opencode_config_fallback: home.join(".config/opencode/opencode.json"),
            agent_catalog: agent_catalog.into(),
            os_registry: os_registry.into(),
            os_assignments: agentik.join("os-assignments.yaml"),
            hermes_skills: hermes.join("skills"),
            claude_skills: home.join(".claude/skills"),
            codex_skills: home.join(".codex/skills"),
            rules_config: agentik.join("rules.yaml"),
            composio_auth: home.join(".composio/user_data.json"),
            composio_inventory: agentik.join("composio-connections.json"),
            topology_status: home.join(".agentik/topology-status.json"),
            executable_paths: Vec::new(),
        }
    }

    pub fn discover() -> Self {
        let home = env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/"));
        let hermes_home = env::var_os("HERMES_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join(".hermes"));
        let catalog = env::var_os("AGK_AGENT_CATALOG")
            .map(PathBuf::from)
            .unwrap_or_else(discover_bundled_catalog);
        let os_registry = env::var_os("AGK_OS_REGISTRY")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                let system = PathBuf::from("/opt/agentik/os-registry");
                if system.is_dir() {
                    system
                } else {
                    home.join(".local/share/agk/os-registry")
                }
            });
        let mut paths = Self::for_home(&home, catalog, os_registry);
        paths.hermes_state_db = hermes_home.join("state.db");
        paths.hermes_config = hermes_home.join("config.yaml");
        paths.hermes_env = hermes_home.join(".env");
        paths.hermes_skills = hermes_home.join("skills");
        paths.rules_config = env::var_os("AGK_RULES_CONFIG")
            .map(PathBuf::from)
            .or_else(|| {
                let user = home.join(".agentik/rules.yaml");
                user.is_file().then_some(user)
            })
            .or_else(|| {
                let system = PathBuf::from("/etc/agk-terminal/rules.yaml");
                system.is_file().then_some(system)
            })
            .or_else(|| {
                env::var_os("AGK_TERMINAL_ROOT")
                    .map(PathBuf::from)
                    .map(|root| root.join("config/rules.yaml"))
            })
            .unwrap_or_else(|| home.join(".local/lib/agk-terminal/config/rules.yaml"));
        paths.executable_paths = env::var_os("PATH")
            .map(|value| env::split_paths(&value).collect())
            .unwrap_or_default();
        paths.topology_status = env::var_os("AGK_TOPOLOGY_STATUS")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/var/lib/agk-terminal/topology-status.json"));
        paths
    }
}

/// Read-only registry facade used by the native TUI.
#[derive(Clone, Debug)]
pub struct RegistryClient {
    pub environment: String,
    pub paths: RegistryPaths,
}

impl RegistryClient {
    /// Discover the current user's canonical registry locations.
    pub fn discover(environment: impl Into<String>) -> Self {
        Self::new(environment, RegistryPaths::discover())
    }

    /// Construct a client with fully injectable paths.
    pub fn new(environment: impl Into<String>, paths: RegistryPaths) -> Self {
        Self {
            environment: environment.into(),
            paths,
        }
    }

    /// Load a coherent snapshot.  Missing optional stores are empty; a store
    /// that exists but cannot be parsed is isolated and described in warnings.
    pub fn load(&self, live_rmux_names: &[String]) -> RegistrySnapshot {
        let mut snapshot = RegistrySnapshot::default();

        snapshot.runtimes = match self.load_runtimes(live_rmux_names, &mut snapshot.warnings) {
            Ok(records) => records,
            Err(error) => {
                warn(&mut snapshot.warnings, "runtime registry", error);
                unmanaged_runtimes(live_rmux_names, &self.environment)
            }
        };

        match self.load_synced_gateway_conversations(&snapshot.runtimes) {
            Ok(records) => snapshot.runtimes.extend(records),
            Err(error) => warn(
                &mut snapshot.warnings,
                "Hermes messaging conversations",
                error,
            ),
        }
        snapshot.runtimes.sort_by(|left, right| {
            right
                .last_activity
                .total_cmp(&left.last_activity)
                .then_with(|| left.name.cmp(&right.name))
        });

        match self.load_hermes_usage(&snapshot.runtimes) {
            Ok((runtime_usage, aggregate)) => {
                for (runtime, usage) in snapshot.runtimes.iter_mut().zip(runtime_usage) {
                    runtime.tokens = usage
                        .iter()
                        .map(ModelUsageRecord::io_tokens)
                        .fold(0_u64, u64::saturating_add);
                    runtime.model_usage = usage;
                }
                snapshot.token_total = aggregate
                    .iter()
                    .map(ModelUsageRecord::io_tokens)
                    .fold(0_u64, u64::saturating_add);
                snapshot.model_usage = aggregate;
            }
            Err(error) => warn(&mut snapshot.warnings, "Hermes token registry", error),
        }

        snapshot.objects = match self.load_control_objects(&mut snapshot.warnings) {
            Ok(records) => records,
            Err(error) => {
                warn(&mut snapshot.warnings, "control registry", error);
                Vec::new()
            }
        };
        snapshot.agents = match self.load_agents(&snapshot.runtimes, &mut snapshot.warnings) {
            Ok(records) => records,
            Err(error) => {
                warn(&mut snapshot.warnings, "agent catalog", error);
                Vec::new()
            }
        };
        snapshot.os_packages = match self.load_os_packages(&mut snapshot.warnings) {
            Ok(records) => records,
            Err(error) => {
                warn(&mut snapshot.warnings, "OS registry", error);
                Vec::new()
            }
        };
        snapshot.mcp_servers = self.load_mcp_servers(&mut snapshot.warnings);
        snapshot.skills = match self.load_skills(&mut snapshot.warnings) {
            Ok(records) => records,
            Err(error) => {
                warn(&mut snapshot.warnings, "skill inventory", error);
                Vec::new()
            }
        };
        snapshot.rules = match self.load_rules() {
            Ok(records) => records,
            Err(error) => {
                warn(&mut snapshot.warnings, "rules registry", error);
                Vec::new()
            }
        };
        snapshot.providers = self.load_providers();
        snapshot.profiles = match self.load_profiles() {
            Ok(records) => records,
            Err(error) => {
                warn(&mut snapshot.warnings, "topology snapshot", error);
                Vec::new()
            }
        };

        snapshot.warnings.sort();
        snapshot.warnings.dedup();
        snapshot
    }

    fn load_runtimes(
        &self,
        live_rmux_names: &[String],
        warnings: &mut Vec<String>,
    ) -> Result<Vec<RuntimeRecord>> {
        let live: BTreeSet<String> = live_rmux_names
            .iter()
            .filter(|name| visible_rmux_name(name))
            .cloned()
            .collect();
        let Some(connection) = open_read_only(&self.paths.runtime_db)? else {
            return Ok(unmanaged_runtimes(live_rmux_names, &self.environment));
        };
        let columns = table_columns(&connection, "runtime_sessions")?;
        require_columns(
            &columns,
            &[
                "id",
                "name",
                "type",
                "environment",
                "client",
                "project",
                "mission",
                "rmux_session",
                "cwd",
                "status",
                "created_at",
                "last_activity",
            ],
            "runtime_sessions",
        )?;
        let native_column = if columns.contains("native_session") {
            "native_session"
        } else {
            "NULL AS native_session"
        };
        let profile_column = if columns.contains("hermes_profile") {
            "hermes_profile"
        } else {
            "NULL AS hermes_profile"
        };
        let archive_clause = if columns.contains("archived_at") {
            " AND archived_at IS NULL"
        } else {
            ""
        };
        let sql = format!(
            "SELECT id,name,type,environment,client,project,mission,{native_column},\
             {profile_column},rmux_session,cwd,status,created_at,last_activity \
             FROM runtime_sessions WHERE environment=?1{archive_clause} \
             ORDER BY last_activity DESC,name"
        );
        let mut statement = connection.prepare(&sql)?;
        let rows = statement.query_map([&self.environment], |row| {
            Ok(RawRuntime {
                id: row.get(0)?,
                name: row.get(1)?,
                kind: row.get(2)?,
                environment: row.get(3)?,
                client: row.get(4)?,
                project: row.get(5)?,
                mission: row.get(6)?,
                native_session: row.get(7)?,
                hermes_profile: row.get(8)?,
                rmux_session: row.get(9)?,
                cwd: row.get(10)?,
                status: row.get(11)?,
                created_at: row.get(12)?,
                last_activity: row.get(13)?,
            })
        })?;

        let mut records = Vec::new();
        let mut managed_rmux = HashSet::new();
        for row in rows {
            let row = row?;
            if !visible_rmux_name(&row.name) || !visible_rmux_name(&row.rmux_session) {
                continue;
            }
            let is_live = live.contains(&row.rmux_session);
            managed_rmux.insert(row.rmux_session.clone());
            let status = projected_runtime_status(&row.status, is_live);
            records.push(RuntimeRecord {
                id: row.id,
                name: row.name,
                kind: row.kind,
                environment: row.environment,
                client: row.client,
                project: row.project,
                mission: row.mission,
                native_session: row.native_session,
                hermes_profile: row.hermes_profile,
                rmux_session: row.rmux_session,
                cwd: row.cwd,
                status,
                created_at: row.created_at,
                last_activity: row.last_activity,
                tokens: 0,
                model_usage: Vec::new(),
                managed: true,
                live: is_live,
            });
        }

        for name in live {
            if !managed_rmux.contains(&name) {
                records.push(unmanaged_runtime(name, &self.environment));
            }
        }
        if !columns.contains("native_session") {
            warnings.push("runtime registry uses a legacy schema without native_session".into());
        }
        Ok(records)
    }

    /// Surface active messaging conversations as resumable, read-only rows.
    /// Hermes keeps the transcript authoritative; pressing Enter in the TUI
    /// later creates a normal AGK/RMUX frontend around this exact session ID.
    fn load_synced_gateway_conversations(
        &self,
        runtimes: &[RuntimeRecord],
    ) -> Result<Vec<RuntimeRecord>> {
        let mut stores = vec![(None, self.paths.hermes_state_db.clone())];
        if let Some(hermes_root) = self.paths.hermes_state_db.parent()
            && hermes_root
                .file_name()
                .is_some_and(|name| name == ".hermes")
        {
            let profiles_root = hermes_root.join("profiles");
            if profiles_root.is_dir() {
                let mut entries =
                    fs::read_dir(&profiles_root)?.collect::<std::io::Result<Vec<_>>>()?;
                entries.sort_by_key(|entry| entry.file_name());
                for entry in entries {
                    if !entry.file_type()?.is_dir() {
                        continue;
                    }
                    let profile = entry.file_name().to_string_lossy().into_owned();
                    if valid_kebab_id(&profile) {
                        stores.push((Some(profile), entry.path().join("state.db")));
                    }
                }
            }
        }

        let profile_prefixes =
            agent_profile_runtime_prefixes(&self.paths.agent_catalog, &self.environment);
        let mut linked = runtimes
            .iter()
            .filter_map(|runtime| {
                runtime
                    .native_session
                    .as_ref()
                    .map(|session| (runtime.hermes_profile.clone(), session.clone()))
            })
            .collect::<HashSet<_>>();
        let mut names = runtimes
            .iter()
            .map(|runtime| runtime.name.clone())
            .collect::<HashSet<_>>();
        let mut records = Vec::new();

        for (profile, database) in stores {
            let Some(connection) = open_read_only(&database)? else {
                continue;
            };
            let columns = table_columns(&connection, "sessions")?;
            if !["id", "source", "session_key", "started_at"]
                .iter()
                .all(|column| columns.contains(*column))
            {
                continue;
            }
            let expression = |column: &str, fallback: &str| {
                if columns.contains(column) {
                    format!("COALESCE({column},{fallback})")
                } else {
                    fallback.to_owned()
                }
            };
            let mut clauses = vec![
                "session_key IS NOT NULL".to_owned(),
                "TRIM(session_key) <> ''".to_owned(),
                "LOWER(source) IN ('discord','telegram','slack','whatsapp','matrix','signal','google_chat','mattermost','feishu')".to_owned(),
            ];
            if columns.contains("ended_at") {
                clauses.push("ended_at IS NULL".into());
            }
            if columns.contains("archived") {
                clauses.push("COALESCE(archived,0)=0".into());
            }
            if columns.contains("hidden") {
                clauses.push("COALESCE(hidden,0)=0".into());
            }
            if columns.contains("message_count") {
                clauses.push("COALESCE(message_count,0)>0".into());
            }
            let last_activity = expression("last_activity_at", "started_at");
            let sql = format!(
                "SELECT id,COALESCE(source,'hermes'),{}, {},started_at,{} \
                 FROM sessions WHERE {} ORDER BY {} DESC LIMIT 100",
                expression("title", "''"),
                expression("cwd", "''"),
                last_activity,
                clauses.join(" AND "),
                last_activity,
            );
            let mut statement = connection.prepare(&sql)?;
            let rows = statement.query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, f64>(4)?,
                    row.get::<_, f64>(5)?,
                ))
            })?;
            let workspace = hermes_workspace_for_state_db(&database);
            for row in rows {
                let (session_id, source, title, cwd, created_at, last_activity) = row?;
                let link = (profile.clone(), session_id.clone());
                if linked.contains(&link) {
                    continue;
                }
                let prefix = profile
                    .as_ref()
                    .and_then(|profile| profile_prefixes.get(profile))
                    .cloned()
                    .unwrap_or_else(|| match &profile {
                        Some(profile) => format!("{}-{profile}", self.environment),
                        None => self.environment.clone(),
                    });
                let title_slug = session_title_slug(&title, &source);
                let suffix = session_id
                    .chars()
                    .filter(|character| character.is_ascii_alphanumeric())
                    .rev()
                    .take(8)
                    .collect::<String>()
                    .chars()
                    .rev()
                    .collect::<String>()
                    .to_ascii_lowercase();
                let base = format!("{prefix}-chat-{title_slug}-{suffix}");
                let mut name = base.chars().take(80).collect::<String>();
                let mut discriminator = 2;
                while names.contains(&name) {
                    let tail = format!("-{discriminator}");
                    let keep = 80usize.saturating_sub(tail.len());
                    name = format!("{}{}", base.chars().take(keep).collect::<String>(), tail);
                    discriminator += 1;
                }
                names.insert(name.clone());
                linked.insert(link);
                records.push(RuntimeRecord {
                    id: format!(
                        "hermes:{}:{session_id}",
                        profile.as_deref().unwrap_or("main")
                    ),
                    name: name.clone(),
                    kind: "hermes".into(),
                    environment: self.environment.clone(),
                    client: None,
                    project: None,
                    mission: None,
                    native_session: Some(session_id),
                    hermes_profile: profile.clone(),
                    rmux_session: name,
                    cwd: if cwd.trim().is_empty() {
                        workspace.to_string_lossy().into_owned()
                    } else {
                        cwd
                    },
                    status: format!("{} · synced", source.to_ascii_lowercase()),
                    created_at,
                    last_activity,
                    tokens: 0,
                    model_usage: Vec::new(),
                    managed: false,
                    live: false,
                });
            }
        }
        Ok(records)
    }

    fn load_hermes_usage(
        &self,
        runtimes: &[RuntimeRecord],
    ) -> Result<(Vec<Vec<ModelUsageRecord>>, Vec<ModelUsageRecord>)> {
        let mut runtime_usage = vec![Vec::new(); runtimes.len()];
        let mut groups: BTreeMap<Option<String>, Vec<usize>> = BTreeMap::new();
        for (index, runtime) in runtimes.iter().enumerate() {
            groups
                .entry(runtime.hermes_profile.clone())
                .or_default()
                .push(index);
        }
        let mut aggregate_rows = Vec::new();
        for (profile, indices) in groups {
            let database = match profile.as_deref() {
                None => self.paths.hermes_state_db.clone(),
                Some(profile) => self
                    .paths
                    .hermes_state_db
                    .parent()
                    .unwrap_or_else(|| Path::new("/"))
                    .join("profiles")
                    .join(profile)
                    .join("state.db"),
            };
            let Some(connection) = open_read_only(&database)? else {
                continue;
            };
            let subset = indices
                .iter()
                .map(|index| runtimes[*index].clone())
                .collect::<Vec<_>>();
            let links = resolve_hermes_session_links(&connection, &subset)?;
            let session_ids = links.iter().flatten().cloned().collect::<BTreeSet<_>>();
            if session_ids.is_empty() {
                continue;
            }
            let by_session = load_session_model_usage(&connection, &session_ids)?;
            for (position, session_id) in links.iter().enumerate() {
                runtime_usage[indices[position]] = session_id
                    .as_ref()
                    .and_then(|id| by_session.get(id))
                    .cloned()
                    .unwrap_or_default();
            }
            for session_id in session_ids {
                if let Some(rows) = by_session.get(&session_id) {
                    aggregate_rows.extend(rows.iter().cloned());
                }
            }
        }
        let aggregate = aggregate_model_usage(aggregate_rows.iter());
        Ok((runtime_usage, aggregate))
    }

    fn load_control_objects(&self, warnings: &mut Vec<String>) -> Result<Vec<ControlObject>> {
        let Some(connection) = open_read_only(&self.paths.control_db)? else {
            return Ok(Vec::new());
        };
        let columns = table_columns(&connection, "objects")?;
        require_columns(
            &columns,
            &[
                "id",
                "environment",
                "kind",
                "slug",
                "name",
                "parent_id",
                "status",
                "path",
                "metadata_json",
                "created_at",
                "updated_at",
            ],
            "objects",
        )?;
        let mut statement = connection.prepare(
            "SELECT id,environment,kind,slug,name,parent_id,status,path,metadata_json,created_at,updated_at \
             FROM objects WHERE environment=?1 AND kind IN ('client','project','mission') \
             ORDER BY updated_at DESC,name",
        )?;
        let data_environment = self.data_environment();
        let rows = statement.query_map([&data_environment], |row| {
            Ok(RawControlObject {
                id: row.get(0)?,
                environment: row.get(1)?,
                kind: row.get(2)?,
                slug: row.get(3)?,
                name: row.get(4)?,
                parent_id: row.get(5)?,
                status: row.get(6)?,
                path: row.get(7)?,
                metadata_json: row.get(8)?,
                created_at: row.get(9)?,
                updated_at: row.get(10)?,
            })
        })?;
        let mut objects = Vec::new();
        for row in rows {
            let row = row?;
            let metadata = match serde_json::from_str(&row.metadata_json) {
                Ok(metadata) => metadata,
                Err(error) => {
                    warnings.push(format!(
                        "control object {} has invalid metadata JSON: {error}",
                        row.id
                    ));
                    JsonValue::Object(Default::default())
                }
            };
            objects.push(ControlObject {
                id: row.id,
                environment: row.environment,
                kind: row.kind,
                slug: row.slug,
                name: row.name,
                parent_id: row.parent_id,
                status: row.status,
                path: row.path,
                metadata,
                created_at: row.created_at,
                updated_at: row.updated_at,
            });
        }
        Ok(objects)
    }

    fn load_agents(
        &self,
        runtimes: &[RuntimeRecord],
        warnings: &mut Vec<String>,
    ) -> Result<Vec<AgentRecord>> {
        let root = &self.paths.agent_catalog;
        if !path_is_file_or_directory(root, false)? {
            return Ok(Vec::new());
        }
        let mut manifests = Vec::new();
        for entry in
            fs::read_dir(root).with_context(|| format!("cannot read {}", root.display()))?
        {
            let entry = entry?;
            if entry.file_type()?.is_dir() {
                let manifest = entry.path().join("agent.yaml");
                if manifest.is_file() {
                    manifests.push(manifest);
                }
            }
        }
        manifests.sort();
        let data_environment = self.data_environment();
        let mut agents = Vec::new();
        for manifest_path in manifests {
            let text = match fs::read_to_string(&manifest_path) {
                Ok(text) => text,
                Err(error) => {
                    warnings.push(format!(
                        "agent manifest {} cannot be read: {error}",
                        manifest_path.display()
                    ));
                    continue;
                }
            };
            let manifest: AgentManifest = match serde_yaml::from_str(&text) {
                Ok(manifest) => manifest,
                Err(error) => {
                    warnings.push(format!(
                        "agent manifest {} is invalid: {error}",
                        manifest_path.display()
                    ));
                    continue;
                }
            };
            if !valid_agent_id(&manifest.id) {
                warnings.push(format!(
                    "agent manifest {} has an invalid id",
                    manifest_path.display()
                ));
                continue;
            }
            let prompt = manifest_path
                .parent()
                .expect("agent manifest always has a parent")
                .join(&manifest.prompt);
            if !prompt.is_file() {
                warnings.push(format!(
                    "agent {} is missing its prompt file {}",
                    manifest.id,
                    prompt.display()
                ));
                continue;
            }
            let runtime_name = format!("{}-{}", self.environment, manifest.id);
            let mut conversations = runtimes
                .iter()
                .filter(|record| {
                    record.name == runtime_name
                        || record.name.starts_with(&format!("{runtime_name}-"))
                })
                .collect::<Vec<_>>();
            conversations.sort_by(|left, right| {
                right
                    .live
                    .cmp(&left.live)
                    .then_with(|| right.last_activity.total_cmp(&left.last_activity))
            });
            let running = conversations
                .iter()
                .copied()
                // An unmanaged RMUX name must not impersonate an installed
                // agent. Synced Hermes conversations are allowed only when
                // they carry a canonical native_session.
                .find(|record| record.managed || record.native_session.is_some());
            let synced = conversations
                .iter()
                .filter(|record| record.native_session.is_some())
                .count();
            agents.push(AgentRecord {
                id: manifest.id,
                name: manifest.name,
                version: manifest.version,
                description: manifest.description,
                profile: manifest.profile,
                os: manifest.os,
                available: manifest
                    .scope
                    .iter()
                    .any(|scope| scope == &data_environment),
                scope: manifest.scope,
                runtime: manifest.runtime,
                catalog_path: manifest_path
                    .parent()
                    .expect("agent manifest always has a parent")
                    .to_string_lossy()
                    .into_owned(),
                runtime_name,
                runtime_id: running.map(|record| record.id.clone()),
                status: running
                    .map(|record| record.status.clone())
                    .unwrap_or_else(|| {
                        if synced > 0 {
                            format!("{synced} synced")
                        } else {
                            "not-started".into()
                        }
                    }),
                live: running.is_some_and(|record| record.live),
            });
        }
        agents.sort_by(|left, right| left.id.cmp(&right.id));
        Ok(agents)
    }

    fn load_os_packages(&self, warnings: &mut Vec<String>) -> Result<Vec<OsPackage>> {
        let index_path = self.paths.os_registry.join("state/index.json");
        let assignments = match self.load_os_assignments(warnings) {
            Ok(assignments) => assignments,
            Err(error) => {
                warnings.push(format!("OS assignments: {error:#}"));
                Vec::new()
            }
        };
        if !path_is_file_or_directory(&index_path, true)? {
            return Ok(Vec::new());
        }
        let text = fs::read_to_string(&index_path)
            .with_context(|| format!("cannot read {}", index_path.display()))?;
        let index: JsonValue = serde_json::from_str(&text)
            .with_context(|| format!("cannot parse {}", index_path.display()))?;
        let package_values = index
            .as_object()
            .and_then(|object| object.get("packages"))
            .and_then(JsonValue::as_array)
            .ok_or_else(|| anyhow!("{} does not contain a packages array", index_path.display()))?;
        let data_environment = self.data_environment();
        let mut packages = Vec::new();
        for value in package_values {
            let raw: OsManifest = match serde_json::from_value(value.clone()) {
                Ok(raw) => raw,
                Err(error) => {
                    warnings.push(format!("OS registry contains an invalid package: {error}"));
                    continue;
                }
            };
            if !valid_kebab_id(&raw.id)
                || raw.name.trim().is_empty()
                || raw.version.trim().is_empty()
                || raw.scope.is_empty()
            {
                warnings.push(format!(
                    "OS registry contains an incomplete package {}@{}",
                    raw.id, raw.version
                ));
                continue;
            }
            let reference = format!("{}@{}", raw.id, raw.version);
            let mut package_assignments: Vec<String> = assignments
                .iter()
                .filter(|assignment| assignment.reference == reference)
                .map(|assignment| format!("{}:{}", assignment.scope, assignment.target))
                .collect();
            package_assignments.sort();
            package_assignments.dedup();
            packages.push(OsPackage {
                id: raw.id,
                name: raw.name,
                version: raw.version,
                description: raw.description,
                available: raw.scope.iter().any(|scope| {
                    scope == "global" || scope == &data_environment || scope == "environment"
                }),
                scope: raw.scope,
                dependencies: raw.dependencies,
                capabilities: raw.capabilities,
                skills: raw.skills,
                workflows: raw.workflows,
                agents: raw.agents,
                tools: raw.tools,
                commands: raw.commands,
                knowledge: raw.knowledge,
                evals: raw.evals,
                assignments: package_assignments,
            });
        }
        let installed: HashSet<String> = packages
            .iter()
            .map(|package| format!("{}@{}", package.id, package.version))
            .collect();
        for assignment in &assignments {
            if !installed.contains(&assignment.reference) {
                warnings.push(format!(
                    "OS assignment references an uninstalled package: {}",
                    assignment.reference
                ));
            }
        }
        packages.sort_by(|left, right| (&left.id, &left.version).cmp(&(&right.id, &right.version)));
        Ok(packages)
    }

    fn load_os_assignments(&self, warnings: &mut Vec<String>) -> Result<Vec<OsAssignment>> {
        if !path_is_file_or_directory(&self.paths.os_assignments, true)? {
            return Ok(Vec::new());
        }
        let text = fs::read_to_string(&self.paths.os_assignments)
            .with_context(|| format!("cannot read {}", self.paths.os_assignments.display()))?;
        let document: YamlValue = serde_yaml::from_str(&text)
            .with_context(|| format!("cannot parse {}", self.paths.os_assignments.display()))?;
        let Some(records) =
            yaml_mapping_get(&document, "assignments").and_then(YamlValue::as_sequence)
        else {
            bail!(
                "{} does not contain an assignments list",
                self.paths.os_assignments.display()
            );
        };
        let mut assignments = Vec::new();
        for record in records {
            if let Some(reference) = record.as_str() {
                assignments.push(OsAssignment {
                    reference: reference.to_owned(),
                    scope: "legacy".into(),
                    target: "unscoped".into(),
                });
                continue;
            }
            let Some(mapping) = record.as_mapping() else {
                warnings.push("OS assignment is neither a reference nor a mapping".into());
                continue;
            };
            let string = |key: &str| {
                mapping
                    .get(YamlValue::String(key.into()))
                    .and_then(YamlValue::as_str)
                    .map(str::to_owned)
            };
            let (Some(reference), Some(scope), Some(target)) =
                (string("os"), string("scope"), string("target"))
            else {
                warnings.push("OS assignment is missing os, scope, or target".into());
                continue;
            };
            assignments.push(OsAssignment {
                reference,
                scope,
                target,
            });
        }
        Ok(assignments)
    }

    fn load_mcp_servers(&self, warnings: &mut Vec<String>) -> Vec<CapabilityRecord> {
        let mut records = BTreeMap::new();
        for (source, result) in [
            ("Hermes", load_hermes_mcp_servers(&self.paths.hermes_config)),
            ("Claude", load_claude_mcp_servers(&self.paths.claude_config)),
            ("Codex", load_codex_mcp_servers(&self.paths.codex_config)),
            (
                "OpenCode",
                load_json_mcp_servers(&self.paths.opencode_config, "OpenCode", "mcp"),
            ),
            (
                "OpenCode",
                load_json_mcp_servers(&self.paths.opencode_config_fallback, "OpenCode", "mcp"),
            ),
        ] {
            match result {
                Ok(source_records) => {
                    for record in source_records {
                        merge_mcp_record(&mut records, record);
                    }
                }
                Err(error) => warn(warnings, &format!("MCP inventory ({source})"), error),
            }
        }

        if executable_in_paths(&self.paths.executable_paths, "composio") {
            match composio_authenticated(&self.paths.composio_auth) {
                Ok(connected) => {
                    let toolkits = if connected {
                        match composio_toolkits(&self.paths.composio_inventory) {
                            Ok(toolkits) => toolkits,
                            Err(error) => {
                                warn(warnings, "MCP inventory (Composio)", error);
                                Vec::new()
                            }
                        }
                    } else {
                        Vec::new()
                    };
                    merge_mcp_record(
                        &mut records,
                        CapabilityRecord {
                            name: "Composio".into(),
                            sources: vec!["Composio".into()],
                            transport: "CLI · link/tools list".into(),
                            status: if connected {
                                "connected"
                            } else {
                                "setup-required"
                            }
                            .into(),
                            toolkits,
                        },
                    );
                }
                Err(error) => warn(warnings, "MCP inventory (Composio)", error),
            }
        }
        records.into_values().collect()
    }

    fn load_providers(&self) -> Vec<ProviderRecord> {
        let hermes = executable_in_paths(&self.paths.executable_paths, "hermes");
        let claude = executable_in_paths(&self.paths.executable_paths, "claude");
        let codex = executable_in_paths(&self.paths.executable_paths, "codex");
        let openrouter = configured_env_key(&self.paths.hermes_env, "OPENROUTER_API_KEY")
            || env::var_os("OPENROUTER_API_KEY").is_some_and(|value| !value.is_empty());
        let claude_ready = configured_json_path(
            &self.paths.claude_credentials,
            &["claudeAiOauth", "accessToken"],
        );
        let codex_ready = configured_json_path(&self.paths.codex_auth, &["OPENAI_API_KEY"])
            || configured_json_path(&self.paths.codex_auth, &["tokens", "access_token"]);
        [
            (
                "hermes",
                "Hermes",
                hermes,
                self.paths.hermes_config.is_file(),
                "hermes",
            ),
            ("claude", "Claude Code", claude, claude_ready, "claude"),
            ("codex", "Codex", codex, codex_ready, "codex"),
            (
                "openrouter",
                "Hermes · OpenRouter",
                hermes,
                openrouter,
                "hermes --provider openrouter",
            ),
            (
                "opencode",
                "OpenCode",
                executable_in_paths(&self.paths.executable_paths, "opencode"),
                true,
                "opencode",
            ),
        ]
        .into_iter()
        .map(
            |(id, name, installed, configured, command)| ProviderRecord {
                id: id.into(),
                name: name.into(),
                installed,
                configured: installed && configured,
                command: command.into(),
            },
        )
        .collect()
    }

    fn load_profiles(&self) -> Result<Vec<ProfileRecord>> {
        if !path_is_file_or_directory(&self.paths.topology_status, true)? {
            return Ok(Vec::new());
        }
        let text = fs::read_to_string(&self.paths.topology_status)
            .with_context(|| format!("cannot read {}", self.paths.topology_status.display()))?;
        let value: JsonValue = serde_json::from_str(&text)
            .with_context(|| format!("cannot parse {}", self.paths.topology_status.display()))?;
        let profiles = value
            .get("profiles")
            .and_then(JsonValue::as_array)
            .ok_or_else(|| anyhow!("topology snapshot has no profiles array"))?;
        let mut records = Vec::new();
        for profile in profiles {
            match serde_json::from_value::<ProfileRecord>(profile.clone()) {
                Ok(record) => records.push(record),
                Err(error) => bail!("topology snapshot contains an invalid profile: {error}"),
            }
        }
        records.sort_by_key(|record| {
            ["operator", "agentik", "mission", "private"]
                .iter()
                .position(|profile| profile == &record.profile_id)
                .unwrap_or(usize::MAX)
        });
        Ok(records)
    }

    fn load_skills(&self, warnings: &mut Vec<String>) -> Result<Vec<SkillRecord>> {
        let roots = [
            (&self.paths.hermes_skills, "hermes", false),
            (&self.paths.claude_skills, "claude", false),
            (&self.paths.codex_skills, "codex", true),
        ];
        let mut found = BTreeMap::new();
        for (root, source, nested) in roots {
            match scan_skill_root(root, source, nested) {
                Ok(records) => {
                    for record in records {
                        found.insert((record.name.clone(), record.source.clone()), record);
                    }
                }
                Err(error) => warnings.push(format!(
                    "skill source {} at {} cannot be read: {error:#}",
                    source,
                    root.display()
                )),
            }
        }
        Ok(found.into_values().collect())
    }

    fn load_rules(&self) -> Result<Vec<RuleRecord>> {
        if !self.paths.rules_config.is_file() {
            return Ok(Vec::new());
        }
        let contents = fs::read_to_string(&self.paths.rules_config)
            .with_context(|| format!("cannot read {}", self.paths.rules_config.display()))?;
        let document: RuleDocument = serde_yaml::from_str(&contents)
            .with_context(|| format!("cannot parse {}", self.paths.rules_config.display()))?;
        let source = self.paths.rules_config.to_string_lossy().into_owned();
        let mut records = Vec::new();
        let mut ids = HashSet::new();
        for mut rule in document.rules {
            rule.id = rule.id.trim().to_ascii_lowercase();
            rule.title = rule.title.trim().to_owned();
            rule.content = rule.content.trim().to_owned();
            if !valid_kebab_id(&rule.id) || rule.title.is_empty() || rule.content.is_empty() {
                bail!("rules registry contains an incomplete rule {}", rule.id);
            }
            if !ids.insert(rule.id.clone()) {
                bail!("rules registry contains duplicate rule {}", rule.id);
            }
            if rule.providers.is_empty() {
                rule.providers.push("*".into());
            }
            rule.providers.sort();
            rule.providers.dedup();
            rule.source.clone_from(&source);
            records.push(rule);
        }
        Ok(records)
    }

    fn data_environment(&self) -> String {
        if self.environment == "collective" {
            "mission".into()
        } else {
            self.environment.clone()
        }
    }
}

#[derive(Debug, Deserialize)]
struct RuleDocument {
    #[serde(default)]
    rules: Vec<RuleRecord>,
}

fn executable_in_paths(paths: &[PathBuf], name: &str) -> bool {
    paths.iter().any(|directory| {
        let Ok(metadata) = fs::metadata(directory.join(name)) else {
            return false;
        };
        #[cfg(unix)]
        return metadata.is_file() && metadata.permissions().mode() & 0o111 != 0;
        #[cfg(not(unix))]
        return metadata.is_file();
    })
}

fn configured_env_key(path: &Path, key: &str) -> bool {
    fs::read_to_string(path).is_ok_and(|contents| {
        contents.lines().any(|line| {
            line.trim_start()
                .strip_prefix(key)
                .and_then(|rest| rest.strip_prefix('='))
                .is_some_and(|value| !value.trim().trim_matches(['\'', '"']).is_empty())
        })
    })
}

fn configured_json_path(path: &Path, keys: &[&str]) -> bool {
    let Ok(contents) = fs::read_to_string(path) else {
        return false;
    };
    let Ok(mut value) = serde_json::from_str::<JsonValue>(&contents) else {
        return false;
    };
    for key in keys {
        let Some(next) = value.get(*key).cloned() else {
            return false;
        };
        value = next;
    }
    match value {
        JsonValue::String(value) => !value.trim().is_empty(),
        JsonValue::Null => false,
        value => !matches!(value, JsonValue::Bool(false)),
    }
}

#[derive(Debug)]
struct RawRuntime {
    id: String,
    name: String,
    kind: String,
    environment: String,
    client: Option<String>,
    project: Option<String>,
    mission: Option<String>,
    native_session: Option<String>,
    hermes_profile: Option<String>,
    rmux_session: String,
    cwd: String,
    status: String,
    created_at: f64,
    last_activity: f64,
}

#[derive(Debug)]
struct RawControlObject {
    id: String,
    environment: String,
    kind: String,
    slug: String,
    name: String,
    parent_id: Option<String>,
    status: String,
    path: Option<String>,
    metadata_json: String,
    created_at: f64,
    updated_at: f64,
}

#[derive(Debug, Deserialize)]
struct AgentManifest {
    id: String,
    #[serde(default)]
    name: String,
    #[serde(default)]
    version: String,
    #[serde(default)]
    description: String,
    #[serde(default)]
    scope: Vec<String>,
    #[serde(default = "default_agent_runtime")]
    runtime: String,
    #[serde(default)]
    profile: Option<String>,
    #[serde(default)]
    os: Vec<String>,
    #[serde(default = "default_agent_prompt")]
    prompt: String,
}

#[derive(Debug, Deserialize)]
struct OsManifest {
    id: String,
    name: String,
    version: String,
    description: String,
    scope: Vec<String>,
    #[serde(default)]
    dependencies: Vec<String>,
    #[serde(default)]
    capabilities: Vec<String>,
    #[serde(default)]
    skills: Vec<String>,
    #[serde(default)]
    workflows: Vec<String>,
    #[serde(default)]
    agents: Vec<String>,
    #[serde(default)]
    tools: Vec<String>,
    #[serde(default)]
    commands: Vec<String>,
    #[serde(default)]
    knowledge: Vec<String>,
    #[serde(default)]
    evals: Vec<String>,
}

#[derive(Clone, Debug)]
struct OsAssignment {
    reference: String,
    scope: String,
    target: String,
}

fn discover_bundled_catalog() -> PathBuf {
    let mut candidates = Vec::new();
    if let Some(home) = std::env::var_os("HERMES_HOME") {
        candidates.push(PathBuf::from(home).join("agents"));
    }
    if let Some(home) = std::env::var_os("HOME") {
        let home = PathBuf::from(home);
        candidates.push(home.join(".hermes/agents"));
        candidates.push(home.join(".local/share/agk/agents"));
    }
    if let Some(root) = std::env::var_os("AGK_TERMINAL_ROOT") {
        candidates.push(PathBuf::from(root).join("agents"));
    }
    if let Some(root) = std::env::var_os("AGK_INSTALL_ROOT") {
        candidates.push(PathBuf::from(root).join("agents"));
    }
    // Last-resort compatibility for machines that have not migrated yet.
    candidates.push(PathBuf::from("/opt/agentik/hermes/current/agents"));
    candidates
        .into_iter()
        .find(|path| path.is_dir())
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../hermes/agents"))
}

fn default_agent_runtime() -> String {
    "hermes".into()
}

fn default_agent_prompt() -> String {
    "prompt.md".into()
}

fn open_read_only(path: &Path) -> Result<Option<Connection>> {
    match fs::metadata(path) {
        Ok(metadata) if !metadata.is_file() => bail!("{} is not a regular file", path.display()),
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => {
            return Err(error).with_context(|| format!("cannot inspect {}", path.display()));
        }
    }
    Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map(Some)
    .with_context(|| format!("cannot open {} read-only", path.display()))
}

fn table_columns(connection: &Connection, table: &str) -> Result<HashSet<String>> {
    let mut statement = connection.prepare(&format!("PRAGMA table_info({table})"))?;
    let rows = statement.query_map([], |row| row.get::<_, String>(1))?;
    let columns = rows.collect::<rusqlite::Result<HashSet<_>>>()?;
    if columns.is_empty() {
        bail!("required SQLite table {table} is missing");
    }
    Ok(columns)
}

fn optional_table_columns(connection: &Connection, table: &str) -> Result<Option<HashSet<String>>> {
    let exists = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?1)",
        [table],
        |row| row.get::<_, bool>(0),
    )?;
    if !exists {
        return Ok(None);
    }
    table_columns(connection, table).map(Some)
}

fn require_columns(columns: &HashSet<String>, required: &[&str], table: &str) -> Result<()> {
    let missing: Vec<_> = required
        .iter()
        .filter(|column| !columns.contains(**column))
        .copied()
        .collect();
    if !missing.is_empty() {
        bail!(
            "SQLite table {table} is missing columns: {}",
            missing.join(", ")
        );
    }
    Ok(())
}

fn path_is_file_or_directory(path: &Path, file: bool) -> Result<bool> {
    match fs::metadata(path) {
        Ok(metadata) if file && metadata.is_file() => Ok(true),
        Ok(metadata) if !file && metadata.is_dir() => Ok(true),
        Ok(_) => bail!(
            "{} is not a {}",
            path.display(),
            if file { "regular file" } else { "directory" }
        ),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error).with_context(|| format!("cannot inspect {}", path.display())),
    }
}

fn composio_authenticated(path: &Path) -> Result<bool> {
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(error) => {
            return Err(error).with_context(|| format!("cannot read {}", path.display()));
        }
    };
    let value: JsonValue = match serde_json::from_str(&text) {
        Ok(value) => value,
        Err(_) => return Ok(false),
    };
    Ok(value
        .get("api_key")
        .and_then(JsonValue::as_str)
        .is_some_and(|key| !key.trim().is_empty()))
}

fn composio_toolkits(path: &Path) -> Result<Vec<CapabilityToolkitRecord>> {
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => {
            return Err(error).with_context(|| format!("cannot read {}", path.display()));
        }
    };
    let document: JsonValue = match serde_json::from_str(&text) {
        Ok(document) => document,
        Err(_) => return Ok(Vec::new()),
    };
    if document.get("schema_version").and_then(JsonValue::as_u64) != Some(1) {
        return Ok(Vec::new());
    }
    let Some(toolkits) = document.get("toolkits").and_then(JsonValue::as_array) else {
        return Ok(Vec::new());
    };
    let mut records = toolkits
        .iter()
        .filter_map(|item| serde_json::from_value::<CapabilityToolkitRecord>(item.clone()).ok())
        .filter(|item| !item.name.trim().is_empty())
        .collect::<Vec<_>>();
    records.sort_by(|left, right| left.name.cmp(&right.name));
    Ok(records)
}

fn projected_runtime_status(stored: &str, live: bool) -> String {
    if !live && !TERMINAL_RUNTIME_STATES.contains(&stored) {
        "interrupted".into()
    } else if live && stored == "interrupted" {
        "running".into()
    } else {
        stored.into()
    }
}

fn visible_rmux_name(name: &str) -> bool {
    // Session names describe work, not UI ownership.  A blanket `-control`
    // filter hid legitimate long-lived workspaces such as `operator-control`.
    // Recursion prevention belongs to the TUI instance that knows which pane
    // it is running inside; see `App::current_rmux_session`.
    !name.is_empty()
}

fn agent_profile_runtime_prefixes(root: &Path, environment: &str) -> HashMap<String, String> {
    let Ok(entries) = fs::read_dir(root) else {
        return HashMap::new();
    };
    entries
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let manifest = entry.path().join("agent.yaml");
            let text = fs::read_to_string(manifest).ok()?;
            let definition = serde_yaml::from_str::<AgentManifest>(&text).ok()?;
            let profile = definition.profile?;
            (valid_kebab_id(&profile) && valid_agent_id(&definition.id))
                .then(|| (profile, format!("{environment}-{}", definition.id)))
        })
        .collect()
}

fn hermes_workspace_for_state_db(database: &Path) -> PathBuf {
    let home = database.parent().unwrap_or_else(|| Path::new("/"));
    let workspace = home.join("workspace");
    if workspace.is_dir() {
        return workspace;
    }
    if home.file_name().is_some_and(|name| name == ".hermes") {
        return home
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| home.to_path_buf());
    }
    // Named profiles always have their own existing Hermes directory, while
    // `workspace/` is optional.  RMUX requires an existing cwd, so fall back
    // to the profile root instead of inventing a path here.
    home.to_path_buf()
}

fn session_title_slug(title: &str, source: &str) -> String {
    let mut slug = String::new();
    let mut separator = false;
    for character in title.chars().flat_map(char::to_lowercase) {
        if character.is_ascii_alphanumeric() {
            if separator && !slug.is_empty() && slug.len() < 34 {
                slug.push('-');
            }
            separator = false;
            if slug.len() < 34 {
                slug.push(character);
            }
        } else {
            separator = true;
        }
    }
    while slug.ends_with('-') {
        slug.pop();
    }
    if slug.len() < 3 {
        slug = source
            .chars()
            .filter(|character| character.is_ascii_alphanumeric())
            .take(20)
            .collect::<String>()
            .to_ascii_lowercase();
    }
    if slug.len() < 3 {
        "conversation".into()
    } else {
        slug
    }
}

fn unmanaged_runtimes(names: &[String], environment: &str) -> Vec<RuntimeRecord> {
    names
        .iter()
        .filter(|name| visible_rmux_name(name))
        .cloned()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .map(|name| unmanaged_runtime(name, environment))
        .collect()
}

fn unmanaged_runtime(name: String, environment: &str) -> RuntimeRecord {
    RuntimeRecord {
        id: format!("rmux:{name}"),
        name: name.clone(),
        kind: "unmanaged".into(),
        environment: environment.into(),
        client: None,
        project: None,
        mission: None,
        native_session: None,
        hermes_profile: None,
        rmux_session: name,
        cwd: String::new(),
        status: "running".into(),
        created_at: 0.0,
        last_activity: 0.0,
        tokens: 0,
        model_usage: Vec::new(),
        managed: false,
        live: true,
    }
}

#[derive(Debug)]
struct HermesSessionCandidate {
    id: String,
    cwd: String,
    started_at: f64,
    provider: String,
}

/// Join new Hermes terminals read-only when their durable runtime row predates
/// Hermes' own generated session id. A tight time/cwd match avoids presenting
/// another terminal's usage; ambiguous matches deliberately remain unknown.
fn resolve_hermes_session_links(
    connection: &Connection,
    runtimes: &[RuntimeRecord],
) -> Result<Vec<Option<String>>> {
    const MATCH_WINDOW_SECONDS: f64 = 30.0;
    const AMBIGUITY_MARGIN_SECONDS: f64 = 1.0;

    let mut links = runtimes
        .iter()
        .map(|runtime| runtime.native_session.clone())
        .collect::<Vec<_>>();
    let candidates_for_runtime = runtimes
        .iter()
        .enumerate()
        .filter(|(_, runtime)| {
            runtime.native_session.is_none()
                && runtime.managed
                && runtime.live
                && runtime.created_at > 0.0
                && !runtime.cwd.is_empty()
                && matches!(
                    runtime.kind.to_ascii_lowercase().as_str(),
                    "hermes" | "openrouter"
                )
        })
        .collect::<Vec<_>>();
    if candidates_for_runtime.is_empty() {
        return Ok(links);
    }

    let columns = table_columns(connection, "sessions")?;
    if !["id", "cwd", "started_at"]
        .iter()
        .all(|column| columns.contains(*column))
    {
        return Ok(links);
    }
    let lower = candidates_for_runtime
        .iter()
        .map(|(_, runtime)| runtime.created_at)
        .fold(f64::INFINITY, f64::min)
        - MATCH_WINDOW_SECONDS;
    let upper = candidates_for_runtime
        .iter()
        .map(|(_, runtime)| runtime.created_at)
        .fold(f64::NEG_INFINITY, f64::max)
        + MATCH_WINDOW_SECONDS;
    let provider_column = if columns.contains("billing_provider") {
        "COALESCE(billing_provider,'')"
    } else {
        "''"
    };
    let sql = format!(
        "SELECT id,COALESCE(cwd,''),started_at,{provider_column} \
         FROM sessions WHERE started_at BETWEEN ?1 AND ?2"
    );
    let mut statement = connection.prepare(&sql)?;
    let rows = statement.query_map([lower, upper], |row| {
        Ok(HermesSessionCandidate {
            id: row.get(0)?,
            cwd: row.get(1)?,
            started_at: row.get(2)?,
            provider: row.get(3)?,
        })
    })?;
    let candidates = rows.collect::<rusqlite::Result<Vec<_>>>()?;
    let mut reserved = links.iter().flatten().cloned().collect::<HashSet<_>>();

    for (index, runtime) in candidates_for_runtime {
        let mut matches = candidates
            .iter()
            .filter(|candidate| {
                !reserved.contains(&candidate.id)
                    && candidate.cwd == runtime.cwd
                    && (candidate.started_at - runtime.created_at).abs() <= MATCH_WINDOW_SECONDS
                    && (!runtime.kind.eq_ignore_ascii_case("openrouter")
                        || candidate.provider.eq_ignore_ascii_case("openrouter"))
            })
            .map(|candidate| ((candidate.started_at - runtime.created_at).abs(), candidate))
            .collect::<Vec<_>>();
        matches.sort_by(|left, right| {
            left.0
                .total_cmp(&right.0)
                .then_with(|| left.1.id.cmp(&right.1.id))
        });
        let Some((best_distance, best)) = matches.first() else {
            continue;
        };
        if matches.get(1).is_some_and(|(next_distance, _)| {
            next_distance - best_distance < AMBIGUITY_MARGIN_SECONDS
        }) {
            continue;
        }
        links[index] = Some(best.id.clone());
        reserved.insert(best.id.clone());
    }
    Ok(links)
}

fn load_session_model_usage(
    connection: &Connection,
    session_ids: &BTreeSet<String>,
) -> Result<HashMap<String, Vec<ModelUsageRecord>>> {
    let placeholders = std::iter::repeat_n("?", session_ids.len())
        .collect::<Vec<_>>()
        .join(",");
    let usage_columns =
        optional_table_columns(connection, "session_model_usage")?.unwrap_or_default();
    let mut by_session: HashMap<String, Vec<ModelUsageRecord>> = HashMap::new();

    if ["session_id", "model", "input_tokens", "output_tokens"]
        .iter()
        .all(|column| usage_columns.contains(*column))
    {
        let expression = |column: &str, fallback: &str| {
            if usage_columns.contains(column) {
                format!("COALESCE({column},{fallback})")
            } else {
                fallback.to_owned()
            }
        };
        let sql = format!(
            "SELECT session_id,COALESCE(model,''),{},COALESCE(input_tokens,0),\
             COALESCE(output_tokens,0),{},{},{},{},{} \
             FROM session_model_usage WHERE session_id IN ({placeholders})",
            expression("billing_provider", "''"),
            expression("cache_read_tokens", "0"),
            expression("cache_write_tokens", "0"),
            expression("reasoning_tokens", "0"),
            expression("api_call_count", "0"),
            expression("last_seen", "0.0")
        );
        let mut statement = connection.prepare(&sql)?;
        let rows = statement.query_map(params_from_iter(session_ids.iter()), |row| {
            Ok((row.get::<_, String>(0)?, usage_from_row(row, 1)?))
        })?;
        for row in rows {
            let (session_id, usage) = row?;
            by_session.entry(session_id).or_default().push(usage);
        }
        for usage in by_session.values_mut() {
            *usage = aggregate_model_usage(usage.iter());
        }
    }

    let missing = session_ids
        .iter()
        .filter(|session_id| !by_session.contains_key(*session_id))
        .cloned()
        .collect::<BTreeSet<_>>();
    if missing.is_empty() {
        return Ok(by_session);
    }

    let columns = table_columns(connection, "sessions")?;
    require_columns(
        &columns,
        &["id", "input_tokens", "output_tokens"],
        "sessions",
    )?;
    let expression = |column: &str, fallback: &str| {
        if columns.contains(column) {
            format!("COALESCE({column},{fallback})")
        } else {
            fallback.to_owned()
        }
    };
    let fallback_placeholders = std::iter::repeat_n("?", missing.len())
        .collect::<Vec<_>>()
        .join(",");
    let last_used_expression = if columns.contains("last_activity_at") {
        "COALESCE(last_activity_at,0.0)".to_owned()
    } else {
        expression("started_at", "0.0")
    };
    let sql = format!(
        "SELECT id,{}, {},COALESCE(input_tokens,0),COALESCE(output_tokens,0),\
         {},{},{},{},{} FROM sessions WHERE id IN ({fallback_placeholders})",
        expression("model", "''"),
        expression("billing_provider", "''"),
        expression("cache_read_tokens", "0"),
        expression("cache_write_tokens", "0"),
        expression("reasoning_tokens", "0"),
        expression("api_call_count", "0"),
        last_used_expression,
    );
    let mut statement = connection.prepare(&sql)?;
    let rows = statement.query_map(params_from_iter(missing.iter()), |row| {
        Ok((row.get::<_, String>(0)?, usage_from_row(row, 1)?))
    })?;
    for row in rows {
        let (session_id, usage) = row?;
        by_session.insert(session_id, vec![usage]);
    }
    Ok(by_session)
}

fn usage_from_row(row: &rusqlite::Row<'_>, offset: usize) -> rusqlite::Result<ModelUsageRecord> {
    let text = |index: usize, fallback: &str| -> rusqlite::Result<String> {
        let value = row.get::<_, String>(index)?;
        Ok(if value.trim().is_empty() {
            fallback.to_owned()
        } else {
            value
        })
    };
    Ok(ModelUsageRecord {
        model: text(offset, "Unattributed")?,
        provider: text(offset + 1, "Hermes")?,
        input_tokens: nonnegative(row.get(offset + 2)?),
        output_tokens: nonnegative(row.get(offset + 3)?),
        cache_read_tokens: nonnegative(row.get(offset + 4)?),
        cache_write_tokens: nonnegative(row.get(offset + 5)?),
        reasoning_tokens: nonnegative(row.get(offset + 6)?),
        api_calls: nonnegative(row.get(offset + 7)?),
        last_used_at: row.get(offset + 8)?,
    })
}

fn aggregate_model_usage<'a>(
    rows: impl IntoIterator<Item = &'a ModelUsageRecord>,
) -> Vec<ModelUsageRecord> {
    let mut aggregate: BTreeMap<(String, String), ModelUsageRecord> = BTreeMap::new();
    for row in rows {
        let entry = aggregate
            .entry((row.model.clone(), row.provider.clone()))
            .or_insert_with(|| ModelUsageRecord {
                model: row.model.clone(),
                provider: row.provider.clone(),
                ..ModelUsageRecord::default()
            });
        entry.input_tokens = entry.input_tokens.saturating_add(row.input_tokens);
        entry.output_tokens = entry.output_tokens.saturating_add(row.output_tokens);
        entry.cache_read_tokens = entry
            .cache_read_tokens
            .saturating_add(row.cache_read_tokens);
        entry.cache_write_tokens = entry
            .cache_write_tokens
            .saturating_add(row.cache_write_tokens);
        entry.reasoning_tokens = entry.reasoning_tokens.saturating_add(row.reasoning_tokens);
        entry.api_calls = entry.api_calls.saturating_add(row.api_calls);
        entry.last_used_at = entry.last_used_at.max(row.last_used_at);
    }
    let mut aggregate = aggregate.into_values().collect::<Vec<_>>();
    aggregate.sort_by(|left, right| {
        right
            .last_used_at
            .total_cmp(&left.last_used_at)
            .then_with(|| left.model.cmp(&right.model))
            .then_with(|| left.provider.cmp(&right.provider))
    });
    aggregate
}

fn nonnegative(value: i64) -> u64 {
    u64::try_from(value).unwrap_or(0)
}

fn valid_agent_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    (3..=80).contains(&value.len())
        && matches!(bytes.next(), Some(b'a'..=b'z' | b'0'..=b'9'))
        && bytes.all(|byte| matches!(byte, b'a'..=b'z' | b'0'..=b'9' | b'-'))
}

fn valid_kebab_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    matches!(bytes.next(), Some(b'a'..=b'z' | b'0'..=b'9'))
        && bytes.all(|byte| matches!(byte, b'a'..=b'z' | b'0'..=b'9' | b'-'))
        && !value.ends_with('-')
        && !value.contains("--")
}

fn load_hermes_mcp_servers(path: &Path) -> Result<Vec<CapabilityRecord>> {
    let Some(text) = read_optional_text(path)? else {
        return Ok(Vec::new());
    };
    let config: YamlValue =
        serde_yaml::from_str(&text).with_context(|| format!("cannot parse {}", path.display()))?;
    let Some(servers) = yaml_mapping_get(&config, "mcp_servers").and_then(YamlValue::as_mapping)
    else {
        return Ok(Vec::new());
    };
    Ok(servers
        .iter()
        .filter_map(|(name, raw)| {
            let name = name.as_str()?.trim();
            if name.is_empty() {
                return None;
            }
            let mapping = raw.as_mapping();
            let configured = |key: &str| {
                mapping
                    .and_then(|mapping| mapping.get(YamlValue::String(key.into())))
                    .is_some_and(yaml_value_is_configured)
            };
            let transport = if configured("url") {
                "http"
            } else if configured("command") {
                "stdio"
            } else {
                "unknown"
            };
            let disabled = mapping
                .and_then(|mapping| mapping.get(YamlValue::String("enabled".into())))
                .is_some_and(|value| value == &YamlValue::Bool(false));
            Some(mcp_declaration(name, "Hermes", transport, disabled))
        })
        .collect())
}

fn load_json_mcp_servers(
    path: &Path,
    source: &str,
    registry_key: &str,
) -> Result<Vec<CapabilityRecord>> {
    let Some(text) = read_optional_text(path)? else {
        return Ok(Vec::new());
    };
    let document: JsonValue = serde_json::from_str(&strip_jsonc(&text))
        .with_context(|| format!("cannot parse {}", path.display()))?;
    let Some(servers) = document.get(registry_key).and_then(JsonValue::as_object) else {
        return Ok(Vec::new());
    };
    Ok(json_mcp_declarations(servers, source))
}

fn load_claude_mcp_servers(path: &Path) -> Result<Vec<CapabilityRecord>> {
    let Some(text) = read_optional_text(path)? else {
        return Ok(Vec::new());
    };
    let document: JsonValue = serde_json::from_str(&strip_jsonc(&text))
        .with_context(|| format!("cannot parse {}", path.display()))?;
    let mut records = BTreeMap::new();
    if let Some(servers) = document.get("mcpServers").and_then(JsonValue::as_object) {
        for record in json_mcp_declarations(servers, "Claude") {
            merge_mcp_record(&mut records, record);
        }
    }
    if let Some(projects) = document.get("projects").and_then(JsonValue::as_object) {
        for project in projects.values() {
            let Some(servers) = project.get("mcpServers").and_then(JsonValue::as_object) else {
                continue;
            };
            for record in json_mcp_declarations(servers, "Claude") {
                merge_mcp_record(&mut records, record);
            }
        }
    }
    Ok(records.into_values().collect())
}

fn json_mcp_declarations(
    servers: &serde_json::Map<String, JsonValue>,
    source: &str,
) -> Vec<CapabilityRecord> {
    servers
        .iter()
        .filter_map(|(name, raw)| {
            let name = name.trim();
            if name.is_empty() {
                return None;
            }
            let raw = raw.as_object();
            let configured = |key: &str| {
                raw.and_then(|mapping| mapping.get(key))
                    .is_some_and(json_value_is_configured)
            };
            let declared_type = raw
                .and_then(|mapping| mapping.get("type"))
                .and_then(JsonValue::as_str)
                .unwrap_or_default();
            let transport =
                if configured("url") || matches!(declared_type, "remote" | "http" | "sse") {
                    "http"
                } else if configured("command") || matches!(declared_type, "local" | "stdio") {
                    "stdio"
                } else {
                    "unknown"
                };
            let disabled = raw.is_some_and(|mapping| {
                mapping.get("enabled") == Some(&JsonValue::Bool(false))
                    || mapping.get("disabled") == Some(&JsonValue::Bool(true))
            });
            Some(mcp_declaration(name, source, transport, disabled))
        })
        .collect()
}

fn load_codex_mcp_servers(path: &Path) -> Result<Vec<CapabilityRecord>> {
    let Some(text) = read_optional_text(path)? else {
        return Ok(Vec::new());
    };
    #[derive(Default)]
    struct Declaration {
        command: bool,
        url: bool,
        disabled: bool,
    }

    let mut declarations: BTreeMap<String, Declaration> = BTreeMap::new();
    let mut current = None;
    for line in text.lines() {
        let line = line.trim();
        if let Some(section) = line
            .strip_prefix('[')
            .and_then(|remainder| remainder.split_once(']').map(|(section, _)| section))
        {
            current = codex_mcp_section_name(section);
            if let Some(name) = &current {
                declarations.entry(name.clone()).or_default();
            }
            continue;
        }
        let Some(name) = current.as_ref() else {
            continue;
        };
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let declaration = declarations
            .get_mut(name)
            .expect("current MCP section always has a declaration");
        match key.trim() {
            "command" => declaration.command = !value.trim().is_empty(),
            "url" => declaration.url = !value.trim().is_empty(),
            "enabled" => declaration.disabled = toml_boolean(value) == Some(false),
            "disabled" => declaration.disabled = toml_boolean(value) == Some(true),
            _ => {}
        }
    }
    Ok(declarations
        .into_iter()
        .map(|(name, declaration)| {
            let transport = if declaration.url {
                "http"
            } else if declaration.command {
                "stdio"
            } else {
                "unknown"
            };
            mcp_declaration(&name, "Codex", transport, declaration.disabled)
        })
        .collect())
}

fn codex_mcp_section_name(section: &str) -> Option<String> {
    let remainder = section.strip_prefix("mcp_servers.")?;
    let name = if let Some(quoted) = remainder.strip_prefix('"') {
        quoted.split('"').next()?
    } else {
        remainder.split('.').next()?
    };
    let name = name.trim();
    (!name.is_empty()).then(|| name.to_owned())
}

fn mcp_declaration(name: &str, source: &str, transport: &str, disabled: bool) -> CapabilityRecord {
    CapabilityRecord {
        name: name.to_owned(),
        sources: vec![source.to_owned()],
        transport: transport.to_owned(),
        status: if disabled { "disabled" } else { "configured" }.into(),
        toolkits: Vec::new(),
    }
}

fn merge_mcp_record(
    records: &mut BTreeMap<String, CapabilityRecord>,
    mut incoming: CapabilityRecord,
) {
    incoming.sources.sort();
    incoming.sources.dedup();
    let key = incoming.name.to_ascii_lowercase();
    let Some(existing) = records.get_mut(&key) else {
        records.insert(key, incoming);
        return;
    };
    existing.sources.extend(incoming.sources);
    existing.sources.sort();
    existing.sources.dedup();
    existing.transport = merge_mcp_label(&existing.transport, &incoming.transport, "mixed");
    existing.status = merge_mcp_label(&existing.status, &incoming.status, "mixed");
    existing.toolkits.extend(incoming.toolkits);
    existing
        .toolkits
        .sort_by(|left, right| left.name.cmp(&right.name));
    existing
        .toolkits
        .dedup_by(|left, right| left.name == right.name);
}

fn merge_mcp_label(existing: &str, incoming: &str, mixed: &str) -> String {
    if existing == incoming {
        existing.to_owned()
    } else if existing == "unknown" {
        incoming.to_owned()
    } else if incoming == "unknown" {
        existing.to_owned()
    } else {
        mixed.to_owned()
    }
}

fn read_optional_text(path: &Path) -> Result<Option<String>> {
    if !path_is_file_or_directory(path, true)? {
        return Ok(None);
    }
    fs::read_to_string(path)
        .map(Some)
        .with_context(|| format!("cannot read {}", path.display()))
}

fn json_value_is_configured(value: &JsonValue) -> bool {
    match value {
        JsonValue::Null => false,
        JsonValue::Bool(value) => *value,
        JsonValue::String(value) => !value.is_empty(),
        JsonValue::Array(value) => !value.is_empty(),
        JsonValue::Object(value) => !value.is_empty(),
        JsonValue::Number(_) => true,
    }
}

fn toml_boolean(value: &str) -> Option<bool> {
    match value.split('#').next()?.trim() {
        "true" => Some(true),
        "false" => Some(false),
        _ => None,
    }
}

/// Remove JSONC comments and trailing commas before handing the document to
/// serde_json. String contents, including URL `//`, remain unchanged.
fn strip_jsonc(input: &str) -> String {
    let characters = input.chars().collect::<Vec<_>>();
    let mut output = String::with_capacity(input.len());
    let mut index = 0;
    let mut in_string = false;
    let mut escaped = false;
    while index < characters.len() {
        let character = characters[index];
        if in_string {
            output.push(character);
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_string = false;
            }
            index += 1;
            continue;
        }
        if character == '"' {
            in_string = true;
            output.push(character);
            index += 1;
            continue;
        }
        if character == '/' && characters.get(index + 1) == Some(&'/') {
            index += 2;
            while index < characters.len() && characters[index] != '\n' {
                index += 1;
            }
            continue;
        }
        if character == '/' && characters.get(index + 1) == Some(&'*') {
            index += 2;
            while index + 1 < characters.len()
                && !(characters[index] == '*' && characters[index + 1] == '/')
            {
                if characters[index] == '\n' {
                    output.push('\n');
                }
                index += 1;
            }
            index = (index + 2).min(characters.len());
            continue;
        }
        if character == ',' {
            let next = characters[index + 1..]
                .iter()
                .copied()
                .find(|candidate| !candidate.is_whitespace());
            if matches!(next, Some('}' | ']')) {
                index += 1;
                continue;
            }
        }
        output.push(character);
        index += 1;
    }
    output
}

fn yaml_mapping_get<'a>(value: &'a YamlValue, key: &str) -> Option<&'a YamlValue> {
    value.as_mapping()?.get(YamlValue::String(key.to_owned()))
}

fn yaml_value_is_configured(value: &YamlValue) -> bool {
    match value {
        YamlValue::Null => false,
        YamlValue::Bool(value) => *value,
        YamlValue::String(value) => !value.is_empty(),
        YamlValue::Sequence(value) => !value.is_empty(),
        YamlValue::Mapping(value) => !value.is_empty(),
        _ => true,
    }
}

fn scan_skill_root(root: &Path, source: &str, nested: bool) -> Result<Vec<SkillRecord>> {
    if !path_is_file_or_directory(root, false)? {
        return Ok(Vec::new());
    }
    let mut manifests = BTreeSet::new();
    let mut children = fs::read_dir(root)
        .with_context(|| format!("cannot read {}", root.display()))?
        .collect::<std::io::Result<Vec<_>>>()?;
    children.sort_by_key(|entry| entry.file_name());
    for child in children {
        if !child.file_type()?.is_dir() {
            continue;
        }
        let child_path = child.path();
        for filename in ["DESCRIPTION.md", "SKILL.md"] {
            let manifest = child_path.join(filename);
            if manifest.is_file() {
                manifests.insert(manifest);
            }
        }
        if nested {
            let mut grandchildren =
                fs::read_dir(&child_path)?.collect::<std::io::Result<Vec<_>>>()?;
            grandchildren.sort_by_key(|entry| entry.file_name());
            for grandchild in grandchildren {
                if grandchild.file_type()?.is_dir() {
                    let manifest = grandchild.path().join("SKILL.md");
                    if manifest.is_file() {
                        manifests.insert(manifest);
                    }
                }
            }
        }
    }
    let mut records = BTreeMap::new();
    for manifest in manifests.into_iter().take(MAX_SKILLS_PER_SOURCE) {
        let Some(name) = manifest.parent().and_then(Path::file_name) else {
            continue;
        };
        let name = name.to_string_lossy().into_owned();
        records.entry(name.clone()).or_insert_with(|| SkillRecord {
            name,
            source: source.into(),
            status: "installed".into(),
        });
    }
    Ok(records.into_values().collect())
}

fn warn(warnings: &mut Vec<String>, source: &str, error: anyhow::Error) {
    warnings.push(format!("{source}: {error:#}"));
}
