#[path = "../src/data.rs"]
mod data;

use data::{RegistryClient, RegistryPaths};
use pretty_assertions::assert_eq;
use rusqlite::{Connection, params};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use tempfile::TempDir;

fn paths(temp: &TempDir) -> RegistryPaths {
    RegistryPaths::for_home(
        temp.path(),
        temp.path().join("catalog"),
        temp.path().join("os-registry"),
    )
}

fn parent(path: &Path) {
    fs::create_dir_all(path.parent().expect("test path has a parent")).unwrap();
}

fn write(path: impl AsRef<Path>, contents: &str) {
    let path = path.as_ref();
    parent(path);
    fs::write(path, contents).unwrap();
}

#[test]
fn global_rules_are_loaded_with_provider_scope_and_safe_defaults() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        &paths.rules_config,
        "rules:\n  - id: verify-runtime\n    title: Verify runtime\n    content: Test the real flow.\n    providers: ['*']\n  - id: codex-only\n    title: Codex only\n    content: Keep Codex focused.\n    providers: [codex]\n    enabled: false\n",
    );
    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    assert_eq!(snapshot.rules.len(), 2);
    assert_eq!(snapshot.rules[0].providers, vec!["*"]);
    assert!(snapshot.rules[0].enabled);
    assert!(!snapshot.rules[1].enabled);
    assert!(snapshot.rules[0].source.ends_with("rules.yaml"));
}

fn runtime_db(path: &Path, include_native_session: bool) -> Connection {
    parent(path);
    let connection = Connection::open(path).unwrap();
    let native = if include_native_session {
        ", native_session TEXT"
    } else {
        ""
    };
    connection
        .execute_batch(&format!(
            "CREATE TABLE runtime_sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                environment TEXT NOT NULL,
                client TEXT,
                project TEXT,
                mission TEXT,
                rmux_session TEXT NOT NULL,
                cwd TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_activity REAL NOT NULL,
                archived_at REAL
                {native}
            );"
        ))
        .unwrap();
    connection
}

#[allow(clippy::too_many_arguments)]
fn insert_runtime(
    connection: &Connection,
    id: &str,
    name: &str,
    kind: &str,
    environment: &str,
    client: Option<&str>,
    project: Option<&str>,
    mission: Option<&str>,
    status: &str,
    last_activity: f64,
    archived_at: Option<f64>,
    native_session: Option<&str>,
) {
    connection
        .execute(
            "INSERT INTO runtime_sessions(
                id,name,type,environment,client,project,mission,rmux_session,cwd,status,
                created_at,last_activity,archived_at,native_session
             ) VALUES (?1,?2,?3,?4,?5,?6,?7,?2,'/workspace',?8,1.0,?9,?10,?11)",
            params![
                id,
                name,
                kind,
                environment,
                client,
                project,
                mission,
                status,
                last_activity,
                archived_at,
                native_session
            ],
        )
        .unwrap();
}

fn hermes_db(path: &Path) -> Connection {
    parent(path);
    let connection = Connection::open(path).unwrap();
    connection
        .execute_batch(
            "CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0
            );",
        )
        .unwrap();
    connection
}

fn add_modern_hermes_usage_schema(connection: &Connection) {
    connection
        .execute_batch(
            "ALTER TABLE sessions ADD COLUMN model TEXT;
             ALTER TABLE sessions ADD COLUMN billing_provider TEXT;
             ALTER TABLE sessions ADD COLUMN cwd TEXT;
             ALTER TABLE sessions ADD COLUMN started_at REAL;
             ALTER TABLE sessions ADD COLUMN last_activity_at REAL;
             ALTER TABLE sessions ADD COLUMN cache_read_tokens INTEGER DEFAULT 0;
             ALTER TABLE sessions ADD COLUMN cache_write_tokens INTEGER DEFAULT 0;
             ALTER TABLE sessions ADD COLUMN reasoning_tokens INTEGER DEFAULT 0;
             ALTER TABLE sessions ADD COLUMN api_call_count INTEGER DEFAULT 0;
             CREATE TABLE session_model_usage (
                session_id TEXT NOT NULL,
                model TEXT NOT NULL,
                billing_provider TEXT,
                api_call_count INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                reasoning_tokens INTEGER DEFAULT 0,
                last_seen REAL DEFAULT 0
             );",
        )
        .unwrap();
}

fn gateway_session_db(path: &Path) -> Connection {
    parent(path);
    let connection = Connection::open(path).unwrap();
    connection
        .execute_batch(
            "CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                session_key TEXT,
                title TEXT,
                cwd TEXT,
                started_at REAL NOT NULL,
                last_activity_at REAL,
                ended_at REAL,
                archived INTEGER DEFAULT 0,
                hidden INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                model TEXT,
                billing_provider TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                reasoning_tokens INTEGER DEFAULT 0,
                api_call_count INTEGER DEFAULT 0
            );",
        )
        .unwrap();
    connection
}

#[test]
fn active_profile_chats_are_resumable_in_sessions_and_agent_views() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        paths.agent_catalog.join("research/agent.yaml"),
        "id: research-agent\nname: Research Agent\nversion: 1.0.0\ndescription: Researches\nscope: [operator]\nruntime: hermes\nprofile: research\nprompt: prompt.md\n",
    );
    write(
        paths.agent_catalog.join("research/prompt.md"),
        "instructions",
    );

    let main = gateway_session_db(&paths.hermes_state_db);
    main.execute(
        "INSERT INTO sessions(
            id,source,session_key,title,cwd,started_at,last_activity_at,message_count,
            model,billing_provider,input_tokens,output_tokens
         ) VALUES ('discord-main','discord','agent:main:discord:dm:1',
                   'Continue launch','',10,30,4,'gpt-5.6-sol','openai-codex',100,20)",
        [],
    )
    .unwrap();
    main.execute(
        "INSERT INTO sessions(id,source,session_key,title,started_at,last_activity_at,message_count)
         VALUES ('ended-chat','discord','agent:main:discord:dm:1','Old',1,2,1)",
        [],
    )
    .unwrap();
    main.execute("UPDATE sessions SET ended_at=3 WHERE id='ended-chat'", [])
        .unwrap();
    drop(main);

    let profile_db = paths
        .hermes_state_db
        .parent()
        .unwrap()
        .join("profiles/research/state.db");
    let research = gateway_session_db(&profile_db);
    research
        .execute(
            "INSERT INTO sessions(
            id,source,session_key,title,cwd,started_at,last_activity_at,message_count,
            model,billing_provider,input_tokens,output_tokens
         ) VALUES ('telegram-agent','telegram','agent:main:telegram:dm:2',
                   'Weekly synthesis','',20,40,5,'claude-sonnet-4-6','anthropic',50,10)",
            [],
        )
        .unwrap();
    drop(research);

    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    let main_chat = snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.native_session.as_deref() == Some("discord-main"))
        .unwrap();
    assert!(main_chat.name.starts_with("operator-chat-continue-launch-"));
    assert_eq!(main_chat.status, "discord · synced");
    assert!(!main_chat.managed && !main_chat.live);
    assert_eq!(main_chat.tokens, 120);

    let agent_chat = snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.native_session.as_deref() == Some("telegram-agent"))
        .unwrap();
    assert!(
        agent_chat
            .name
            .starts_with("operator-research-agent-chat-weekly-synthesis-")
    );
    assert_eq!(agent_chat.hermes_profile.as_deref(), Some("research"));
    assert_eq!(agent_chat.tokens, 60);
    assert!(
        snapshot
            .runtimes
            .iter()
            .all(|runtime| runtime.native_session.as_deref() != Some("ended-chat"))
    );

    let agent = snapshot
        .agents
        .iter()
        .find(|agent| agent.id == "research-agent")
        .unwrap();
    assert_eq!(agent.runtime_id.as_deref(), Some(agent_chat.id.as_str()));
    assert_eq!(agent.status, "telegram · synced");
    assert!(!agent.live);
    assert_eq!(snapshot.token_total, 180);
}

#[test]
fn missing_stores_are_empty_and_never_created() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    let snapshot = RegistryClient::new("operator", paths.clone()).load(&[
        "operator-control".into(),
        "loose-session".into(),
        "loose-session".into(),
    ]);

    assert_eq!(snapshot.runtimes.len(), 2);
    assert_eq!(snapshot.runtimes[0].name, "loose-session");
    assert_eq!(snapshot.runtimes[1].name, "operator-control");
    assert!(snapshot.runtimes.iter().all(|runtime| !runtime.managed));
    assert!(snapshot.runtimes.iter().all(|runtime| runtime.live));
    assert!(snapshot.objects.is_empty());
    assert!(snapshot.agents.is_empty());
    assert!(snapshot.os_packages.is_empty());
    assert!(snapshot.mcp_servers.is_empty());
    assert!(snapshot.skills.is_empty());
    assert_eq!(snapshot.token_total, 0);
    assert!(snapshot.warnings.is_empty());
    assert!(!paths.runtime_db.exists());
    assert!(!paths.control_db.exists());
    assert!(!paths.hermes_state_db.exists());
}

#[test]
fn runtimes_join_managed_and_live_sessions_including_control_workspaces() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    let runtime = runtime_db(&paths.runtime_db, true);
    insert_runtime(
        &runtime,
        "RT-LIVE",
        "operator-live",
        "hermes",
        "operator",
        Some("CLI-1"),
        Some("PRJ-1"),
        Some("MIS-1"),
        "interrupted",
        50.0,
        None,
        Some("hermes-1"),
    );
    insert_runtime(
        &runtime,
        "RT-STALE",
        "operator-stale",
        "codex",
        "operator",
        None,
        Some("PRJ-2"),
        None,
        "working",
        40.0,
        None,
        Some("codex-native"),
    );
    insert_runtime(
        &runtime,
        "RT-COMPLETE",
        "operator-complete",
        "hermes",
        "operator",
        None,
        None,
        None,
        "complete",
        30.0,
        None,
        Some("hermes-1"),
    );
    insert_runtime(
        &runtime,
        "RT-CONTROL",
        "operator-control",
        "shell",
        "operator",
        None,
        None,
        None,
        "running",
        20.0,
        None,
        None,
    );
    insert_runtime(
        &runtime,
        "RT-ARCHIVED",
        "operator-archived",
        "shell",
        "operator",
        None,
        None,
        None,
        "archived",
        10.0,
        Some(99.0),
        None,
    );
    insert_runtime(
        &runtime,
        "RT-OTHER",
        "private-other",
        "shell",
        "private",
        None,
        None,
        None,
        "running",
        60.0,
        None,
        None,
    );
    drop(runtime);

    let hermes = hermes_db(&paths.hermes_state_db);
    hermes
        .execute(
            "INSERT INTO sessions(id,input_tokens,output_tokens) VALUES ('hermes-1',12,8)",
            [],
        )
        .unwrap();
    hermes
        .execute(
            "INSERT INTO sessions(id,input_tokens,output_tokens) VALUES ('unrelated',900,100)",
            [],
        )
        .unwrap();
    drop(hermes);

    let snapshot = RegistryClient::new("operator", paths).load(&[
        "operator-live".into(),
        "operator-control".into(),
        "unmanaged-work".into(),
    ]);
    let names: Vec<_> = snapshot
        .runtimes
        .iter()
        .map(|runtime| runtime.name.as_str())
        .collect();
    assert_eq!(
        names,
        vec![
            "operator-live",
            "operator-stale",
            "operator-complete",
            "operator-control",
            "unmanaged-work"
        ]
    );

    let live = &snapshot.runtimes[0];
    assert_eq!(live.status, "running");
    assert!(live.managed && live.live);
    assert_eq!(live.client.as_deref(), Some("CLI-1"));
    assert_eq!(live.project.as_deref(), Some("PRJ-1"));
    assert_eq!(live.mission.as_deref(), Some("MIS-1"));
    assert_eq!(live.tokens, 20, "warnings: {:?}", snapshot.warnings);

    let stale = &snapshot.runtimes[1];
    assert_eq!(stale.status, "interrupted");
    assert!(stale.managed && !stale.live);
    assert_eq!(stale.tokens, 0);

    let complete = &snapshot.runtimes[2];
    assert_eq!(complete.status, "complete");
    assert_eq!(complete.tokens, 20);

    let control = &snapshot.runtimes[3];
    assert_eq!(control.id, "RT-CONTROL");
    assert!(control.managed && control.live);

    let unmanaged = &snapshot.runtimes[4];
    assert_eq!(unmanaged.id, "rmux:unmanaged-work");
    assert_eq!(unmanaged.kind, "unmanaged");
    assert!(!unmanaged.managed && unmanaged.live);

    // Both managed rows refer to one Hermes session, so the aggregate is not
    // double counted and unrelated Hermes sessions do not leak into it.
    assert_eq!(snapshot.token_total, 20);
    assert!(snapshot.warnings.is_empty());
}

#[test]
fn modern_hermes_usage_is_split_by_model_without_double_counting_cache() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    let runtime = runtime_db(&paths.runtime_db, true);
    insert_runtime(
        &runtime,
        "RT-MODELS",
        "model-work",
        "hermes",
        "operator",
        None,
        None,
        None,
        "running",
        20.0,
        None,
        Some("session-modern"),
    );
    drop(runtime);

    let hermes = hermes_db(&paths.hermes_state_db);
    add_modern_hermes_usage_schema(&hermes);
    hermes
        .execute(
            "INSERT INTO sessions(id,input_tokens,output_tokens,model,billing_provider,cwd,started_at)
             VALUES ('session-modern',9999,9999,'fallback','fallback','/workspace',1)",
            [],
        )
        .unwrap();
    hermes
        .execute(
            "INSERT INTO session_model_usage(
                session_id,model,billing_provider,api_call_count,input_tokens,output_tokens,
                cache_read_tokens,cache_write_tokens,reasoning_tokens,last_seen
             ) VALUES ('session-modern','claude-sonnet-4-6','anthropic',2,100,20,5000,30,7,10)",
            [],
        )
        .unwrap();
    hermes
        .execute(
            "INSERT INTO session_model_usage(
                session_id,model,billing_provider,api_call_count,input_tokens,output_tokens,
                cache_read_tokens,cache_write_tokens,reasoning_tokens,last_seen
             ) VALUES ('session-modern','gpt-5.6-sol','openai-codex',3,300,40,9000,0,11,20)",
            [],
        )
        .unwrap();
    hermes
        .execute(
            "INSERT INTO session_model_usage(
                session_id,model,billing_provider,input_tokens,output_tokens,last_seen
             ) VALUES ('unrelated','stealth/ox-alpha','openrouter',50000,50000,30)",
            [],
        )
        .unwrap();
    drop(hermes);

    let snapshot = RegistryClient::new("operator", paths).load(&["model-work".into()]);
    let runtime = &snapshot.runtimes[0];
    assert_eq!(runtime.tokens, 460);
    assert_eq!(snapshot.token_total, 460);
    assert_eq!(runtime.model_usage.len(), 2);
    assert_eq!(runtime.model_usage[0].model, "gpt-5.6-sol");
    assert_eq!(runtime.model_usage[0].provider, "openai-codex");
    assert_eq!(runtime.model_usage[0].io_tokens(), 340);
    assert_eq!(runtime.model_usage[0].cache_read_tokens, 9000);
    assert_eq!(runtime.model_usage[1].model, "claude-sonnet-4-6");
    assert_eq!(snapshot.model_usage, runtime.model_usage);
}

#[test]
fn new_openrouter_runtime_gets_a_unique_read_only_session_match() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    let runtime = runtime_db(&paths.runtime_db, true);
    insert_runtime(
        &runtime,
        "RT-ROUTER",
        "router-work",
        "openrouter",
        "operator",
        None,
        None,
        None,
        "running",
        101.0,
        None,
        None,
    );
    runtime
        .execute(
            "UPDATE runtime_sessions SET created_at=100 WHERE id='RT-ROUTER'",
            [],
        )
        .unwrap();
    drop(runtime);

    let hermes = hermes_db(&paths.hermes_state_db);
    add_modern_hermes_usage_schema(&hermes);
    hermes
        .execute(
            "INSERT INTO sessions(id,input_tokens,output_tokens,model,billing_provider,cwd,started_at)
             VALUES ('router-native',50,10,'stealth/ox-alpha','openrouter','/workspace',100.4)",
            [],
        )
        .unwrap();
    hermes
        .execute(
            "INSERT INTO session_model_usage(
                session_id,model,billing_provider,api_call_count,input_tokens,output_tokens,last_seen
             ) VALUES ('router-native','stealth/ox-alpha','openrouter',1,50,10,101)",
            [],
        )
        .unwrap();
    drop(hermes);

    let snapshot = RegistryClient::new("operator", paths).load(&["router-work".into()]);
    assert_eq!(snapshot.runtimes[0].native_session, None);
    assert_eq!(snapshot.runtimes[0].tokens, 60);
    assert_eq!(
        snapshot.runtimes[0].model_usage[0].model,
        "stealth/ox-alpha"
    );
    assert_eq!(snapshot.runtimes[0].model_usage[0].provider, "openrouter");
}

#[test]
fn legacy_runtime_schema_loads_without_mutation() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    let runtime = runtime_db(&paths.runtime_db, false);
    runtime
        .execute(
            "INSERT INTO runtime_sessions(
                id,name,type,environment,rmux_session,cwd,status,created_at,last_activity
             ) VALUES ('RT-OLD','operator-old','shell','operator','operator-old','/tmp','running',1,2)",
            [],
        )
        .unwrap();
    drop(runtime);

    let snapshot = RegistryClient::new("operator", paths.clone()).load(&["operator-old".into()]);
    assert_eq!(snapshot.runtimes.len(), 1);
    assert_eq!(snapshot.runtimes[0].native_session, None);
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| warning.contains("legacy schema without native_session"))
    );

    let connection = Connection::open(paths.runtime_db).unwrap();
    let native_column_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM pragma_table_info('runtime_sessions') WHERE name='native_session'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(native_column_count, 0);
}

#[test]
fn control_objects_are_scoped_and_collective_maps_to_mission() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    parent(&paths.control_db);
    let connection = Connection::open(&paths.control_db).unwrap();
    connection
        .execute_batch(
            "CREATE TABLE objects (
                id TEXT PRIMARY KEY, environment TEXT, kind TEXT, slug TEXT, name TEXT,
                parent_id TEXT, status TEXT, path TEXT, metadata_json TEXT,
                created_at REAL, updated_at REAL
            );",
        )
        .unwrap();
    let objects = [
        (
            "CLI-1",
            "mission",
            "client",
            "acme",
            "Acme",
            None,
            "active",
            None,
            "{\"tier\":\"gold\"}",
            1.0,
        ),
        (
            "PRJ-1",
            "mission",
            "project",
            "rocket",
            "Rocket",
            Some("CLI-1"),
            "active",
            Some("/clients/acme/rocket"),
            "{}",
            2.0,
        ),
        (
            "MIS-1",
            "mission",
            "mission",
            "launch",
            "Launch",
            Some("PRJ-1"),
            "paused",
            None,
            "not-json",
            3.0,
        ),
        (
            "TSK-1",
            "mission",
            "task",
            "task",
            "Task",
            Some("MIS-1"),
            "active",
            None,
            "{}",
            4.0,
        ),
        (
            "PRJ-X", "private", "project", "secret", "Secret", None, "active", None, "{}", 5.0,
        ),
    ];
    for (id, environment, kind, slug, name, parent_id, status, path, metadata, updated) in objects {
        connection
            .execute(
                "INSERT INTO objects VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,0,?10)",
                params![
                    id,
                    environment,
                    kind,
                    slug,
                    name,
                    parent_id,
                    status,
                    path,
                    metadata,
                    updated
                ],
            )
            .unwrap();
    }
    drop(connection);

    let snapshot = RegistryClient::new("collective", paths).load(&[]);
    let ids: Vec<_> = snapshot
        .objects
        .iter()
        .map(|object| object.id.as_str())
        .collect();
    assert_eq!(ids, vec!["MIS-1", "PRJ-1", "CLI-1"]);
    assert_eq!(snapshot.objects[0].parent_id.as_deref(), Some("PRJ-1"));
    assert_eq!(
        snapshot.objects[1].path.as_deref(),
        Some("/clients/acme/rocket")
    );
    assert_eq!(snapshot.objects[2].metadata["tier"], "gold");
    assert_eq!(snapshot.objects[0].metadata, serde_json::json!({}));
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| warning.contains("MIS-1 has invalid metadata JSON"))
    );
}

#[test]
fn agent_catalog_validates_prompts_scopes_and_runtime_status() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        paths.agent_catalog.join("builder/agent.yaml"),
        "id: master-builder\nname: Master Builder\nversion: 1.2.3\ndescription: Builds systems\nscope: [mission]\nruntime: hermes\nprofile: research\nos: [research-os@1.0.0]\nprompt: prompt.md\n",
    );
    write(
        paths.agent_catalog.join("builder/prompt.md"),
        "instructions",
    );
    write(
        paths.agent_catalog.join("private/agent.yaml"),
        "id: private-agent\nname: Private\nversion: 1.0.0\ndescription: Private only\nscope: [private]\nprompt: prompt.md\n",
    );
    write(
        paths.agent_catalog.join("private/prompt.md"),
        "instructions",
    );
    write(
        paths.agent_catalog.join("missing/agent.yaml"),
        "id: missing-prompt\nname: Missing\nversion: 1.0.0\nscope: [mission]\n",
    );
    write(
        paths.agent_catalog.join("invalid/agent.yaml"),
        "id: INVALID\nname: Invalid\nversion: 1.0.0\nscope: [mission]\nprompt: prompt.md\n",
    );
    write(
        paths.agent_catalog.join("invalid/prompt.md"),
        "instructions",
    );

    let runtime = runtime_db(&paths.runtime_db, true);
    insert_runtime(
        &runtime,
        "RT-AGENT",
        "collective-master-builder",
        "hermes",
        "collective",
        None,
        None,
        None,
        "running",
        1.0,
        None,
        None,
    );
    drop(runtime);

    let snapshot =
        RegistryClient::new("collective", paths).load(&["collective-master-builder".into()]);
    assert_eq!(snapshot.agents.len(), 2);
    let builder = snapshot
        .agents
        .iter()
        .find(|agent| agent.id == "master-builder")
        .unwrap();
    assert_eq!(builder.runtime, "hermes");
    assert_eq!(builder.status, "running");
    assert!(builder.live);
    assert!(builder.available);
    assert_eq!(builder.profile.as_deref(), Some("research"));
    assert_eq!(builder.os, ["research-os@1.0.0"]);
    assert_eq!(builder.runtime_id.as_deref(), Some("RT-AGENT"));
    let private = snapshot
        .agents
        .iter()
        .find(|agent| agent.id == "private-agent")
        .unwrap();
    assert_eq!(private.status, "not-started");
    assert!(!private.live);
    assert!(!private.available);
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| warning.contains("missing-prompt") && warning.contains("prompt"))
    );
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| warning.contains("invalid id"))
    );
}

#[test]
fn unmanaged_rmux_name_does_not_impersonate_a_catalog_agent() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        paths.agent_catalog.join("helper/agent.yaml"),
        "id: helper-agent\nname: Helper\nversion: 1.0.0\ndescription: Helps\nscope: [operator]\nprompt: prompt.md\n",
    );
    write(paths.agent_catalog.join("helper/prompt.md"), "prompt");

    let snapshot = RegistryClient::new("operator", paths).load(&["operator-helper-agent".into()]);
    assert_eq!(snapshot.runtimes.len(), 1);
    assert!(!snapshot.runtimes[0].managed);
    assert_eq!(snapshot.agents[0].status, "not-started");
    assert!(!snapshot.agents[0].live);
    assert_eq!(snapshot.agents[0].runtime_id, None);
}

#[test]
fn os_registry_preserves_manifest_fields_and_attaches_assignments() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        paths.os_registry.join("state/index.json"),
        r#"{
          "schema_version": 1,
          "packages": [
            {
              "id": "mission-control", "name": "Mission Control", "version": "2.0.0",
              "description": "Coordinates missions", "scope": ["mission", "project"],
              "dependencies": ["base@1.0.0"], "capabilities": ["planning"],
              "skills": ["triage"], "workflows": ["launch"], "agents": ["builder"],
              "tools": ["terminal"], "commands": ["mission"], "knowledge": ["runbook"],
              "evals": ["smoke"]
            },
            {
              "id": "private-kit", "name": "Private Kit", "version": "1.0.0",
              "description": "Private", "scope": ["private"]
            },
            {"id": "broken"}
          ]
        }"#,
    );
    write(
        &paths.os_assignments,
        "schema_version: 1\nassignments:\n  - os: mission-control@2.0.0\n    scope: environment\n    target: mission\n  - os: mission-control@2.0.0\n    scope: project\n    target: PRJ-1\n  - private-kit@1.0.0\n",
    );

    let snapshot = RegistryClient::new("collective", paths).load(&[]);
    assert_eq!(snapshot.os_packages.len(), 2);
    let mission = snapshot
        .os_packages
        .iter()
        .find(|package| package.id == "mission-control")
        .unwrap();
    assert_eq!(mission.version, "2.0.0");
    assert_eq!(mission.dependencies, vec!["base@1.0.0"]);
    assert_eq!(mission.capabilities, vec!["planning"]);
    assert_eq!(
        mission.assignments,
        vec!["environment:mission", "project:PRJ-1"]
    );
    assert!(mission.available);
    let private = snapshot
        .os_packages
        .iter()
        .find(|package| package.id == "private-kit")
        .unwrap();
    assert_eq!(private.assignments, vec!["legacy:unscoped"]);
    assert!(!private.available);
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| warning.contains("invalid package"))
    );
}

#[test]
fn malformed_os_assignments_do_not_hide_valid_installed_packages() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        paths.os_registry.join("state/index.json"),
        r#"{"packages":[{"id":"base-os","name":"Base","version":"1.0.0","description":"Base OS","scope":["global"]}]}"#,
    );
    write(&paths.os_assignments, "assignments: [unterminated");

    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    assert_eq!(snapshot.os_packages.len(), 1);
    assert_eq!(snapshot.os_packages[0].id, "base-os");
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| warning.starts_with("OS assignments:"))
    );
}

#[test]
fn mcp_inventory_is_redacted_and_reports_only_identity_transport_and_status() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        &paths.hermes_config,
        r#"mcp_servers:
  remote:
    url: https://secret.example.invalid/mcp?token=TOP_SECRET
    headers:
      Authorization: Bearer TOP_SECRET
  local:
    command: [secret-mcp, --password, TOP_SECRET]
    env:
      API_KEY: TOP_SECRET
    enabled: false
  placeholder: {}
"#,
    );

    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    assert_eq!(snapshot.mcp_servers.len(), 3);
    assert_eq!(snapshot.mcp_servers[0].name, "local");
    assert_eq!(snapshot.mcp_servers[0].sources, vec!["Hermes"]);
    assert_eq!(snapshot.mcp_servers[0].transport, "stdio");
    assert_eq!(snapshot.mcp_servers[0].status, "disabled");
    assert_eq!(snapshot.mcp_servers[1].name, "placeholder");
    assert_eq!(snapshot.mcp_servers[1].transport, "unknown");
    assert_eq!(snapshot.mcp_servers[2].name, "remote");
    assert_eq!(snapshot.mcp_servers[2].transport, "http");

    let public_json = serde_json::to_string(&snapshot.mcp_servers).unwrap();
    assert!(!public_json.contains("TOP_SECRET"));
    assert!(!public_json.contains("secret.example"));
    assert!(!public_json.contains("secret-mcp"));
    assert!(!public_json.contains("Authorization"));
    assert!(!public_json.contains("API_KEY"));
}

#[test]
fn mcp_inventory_merges_current_provider_registries_without_secret_values() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        &paths.hermes_config,
        "mcp_servers:\n  shared:\n    command: [secret-hermes, TOP_SECRET]\n",
    );
    write(
        &paths.claude_config,
        r#"{
          "projects": {
            "/workspace/project": {
              "mcpServers": {
                "shared": {"command":"secret-claude","env":{"TOKEN":"TOP_SECRET"}},
                "claude-only": {"url":"https://secret.invalid/mcp?token=TOP_SECRET"}
              }
            }
          }
        }"#,
    );
    write(
        &paths.codex_config,
        r#"[mcp_servers.shared]
command = "secret-codex"
args = ["TOP_SECRET"]

[mcp_servers."codex-only"]
url = "https://secret.invalid/mcp?token=TOP_SECRET"
"#,
    );
    write(
        &paths.opencode_config,
        r#"{
          // OpenCode accepts JSONC comments and trailing commas.
          "mcp": {
            "shared": {"type":"local","command":["secret-opencode","TOP_SECRET"]},
            "disabled-one": {"type":"remote","url":"https://secret.invalid","enabled":false},
          },
        }"#,
    );

    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    let shared = snapshot
        .mcp_servers
        .iter()
        .find(|record| record.name == "shared")
        .unwrap();
    assert_eq!(
        shared.sources,
        vec!["Claude", "Codex", "Hermes", "OpenCode"]
    );
    assert_eq!(shared.transport, "stdio");
    assert_eq!(shared.status, "configured");
    assert!(snapshot.mcp_servers.iter().any(|record| {
        record.name == "claude-only" && record.sources == ["Claude"] && record.transport == "http"
    }));
    assert!(snapshot.mcp_servers.iter().any(|record| {
        record.name == "codex-only" && record.sources == ["Codex"] && record.transport == "http"
    }));
    assert!(snapshot.mcp_servers.iter().any(|record| {
        record.name == "disabled-one"
            && record.sources == ["OpenCode"]
            && record.status == "disabled"
    }));

    let public_json = serde_json::to_string(&snapshot.mcp_servers).unwrap();
    for secret in [
        "TOP_SECRET",
        "secret.invalid",
        "secret-hermes",
        "secret-claude",
        "secret-codex",
        "secret-opencode",
    ] {
        assert!(!public_json.contains(secret), "leaked {secret}");
    }
}

#[test]
fn loading_again_reflects_replaced_mcp_configuration() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    let client = RegistryClient::new("operator", paths.clone());
    write(
        &paths.hermes_config,
        "mcp_servers:\n  before-refresh:\n    command: [server]\n",
    );
    let first = client.load(&[]);
    assert_eq!(first.mcp_servers[0].name, "before-refresh");

    write(
        &paths.hermes_config,
        "mcp_servers:\n  after-refresh:\n    url: https://example.invalid/mcp\n",
    );
    let refreshed = client.load(&[]);
    assert_eq!(refreshed.mcp_servers[0].name, "after-refresh");
    assert_eq!(refreshed.mcp_servers[0].transport, "http");
    assert!(
        refreshed
            .mcp_servers
            .iter()
            .all(|record| record.name != "before-refresh")
    );
}

#[test]
fn malformed_provider_mcp_source_does_not_hide_healthy_sources() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(&paths.claude_config, "{broken json");
    write(
        &paths.hermes_config,
        "mcp_servers:\n  healthy:\n    command: [server]\n",
    );

    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    assert_eq!(snapshot.mcp_servers[0].name, "healthy");
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| { warning.starts_with("MCP inventory (Claude):") })
    );
}

#[test]
fn installed_skills_are_deduplicated_by_name_and_source_with_codex_namespaces() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(
        paths.hermes_skills.join("shared/SKILL.md"),
        "secret contents",
    );
    write(
        paths.hermes_skills.join("shared/DESCRIPTION.md"),
        "duplicate manifest",
    );
    write(paths.claude_skills.join("shared/SKILL.md"), "claude");
    write(paths.codex_skills.join("direct/DESCRIPTION.md"), "codex");
    write(
        paths.codex_skills.join("plugins/nested/SKILL.md"),
        "nested codex",
    );
    write(
        paths.codex_skills.join("plugins/deeper/ignored/SKILL.md"),
        "too deep",
    );

    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    let identities: Vec<_> = snapshot
        .skills
        .iter()
        .map(|skill| {
            (
                skill.name.as_str(),
                skill.source.as_str(),
                skill.status.as_str(),
            )
        })
        .collect();
    assert_eq!(
        identities,
        vec![
            ("direct", "codex", "installed"),
            ("nested", "codex", "installed"),
            ("shared", "claude", "installed"),
            ("shared", "hermes", "installed"),
        ]
    );
}

#[test]
fn malformed_present_sources_are_isolated_as_warnings() {
    let temp = TempDir::new().unwrap();
    let paths = paths(&temp);
    write(&paths.runtime_db, "not a sqlite database");
    write(&paths.hermes_config, "mcp_servers: [unterminated");
    write(
        paths.hermes_skills.join("healthy/SKILL.md"),
        "still discovered",
    );

    let snapshot = RegistryClient::new("operator", paths).load(&["live-anyway".into()]);
    assert_eq!(snapshot.runtimes.len(), 1);
    assert_eq!(snapshot.runtimes[0].name, "live-anyway");
    assert_eq!(snapshot.skills.len(), 1);
    assert_eq!(snapshot.skills[0].name, "healthy");
    assert!(snapshot.mcp_servers.is_empty());
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| warning.starts_with("runtime registry:"))
    );
    assert!(
        snapshot
            .warnings
            .iter()
            .any(|warning| warning.starts_with("MCP inventory (Hermes):"))
    );
}

#[test]
fn injected_paths_are_used_instead_of_process_home() {
    let temp = TempDir::new().unwrap();
    let alternate = TempDir::new().unwrap();
    let mut injected = paths(&temp);
    injected.hermes_config = alternate.path().join("custom-hermes/config.yaml");
    injected.agent_catalog = alternate.path().join("custom-agents");
    write(
        &injected.hermes_config,
        "mcp_servers:\n  injected:\n    command: [server]\n",
    );
    write(
        injected.agent_catalog.join("custom/agent.yaml"),
        "id: custom-agent\nname: Custom\nversion: 1.0.0\ndescription: Injected\nscope: [operator]\nprompt: prompt.md\n",
    );
    write(injected.agent_catalog.join("custom/prompt.md"), "prompt");

    let snapshot = RegistryClient::new("operator", injected).load(&[]);
    assert_eq!(snapshot.mcp_servers[0].name, "injected");
    assert_eq!(snapshot.agents[0].id, "custom-agent");
}

#[test]
fn public_mcp_record_has_no_place_for_secret_configuration() {
    let fields = serde_json::to_value(data::CapabilityRecord {
        name: "example".into(),
        sources: vec!["Hermes".into()],
        transport: "stdio".into(),
        status: "configured".into(),
        toolkits: Vec::new(),
    })
    .unwrap();
    let keys: Vec<_> = fields
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(
        keys,
        vec!["name", "sources", "status", "toolkits", "transport"]
    );
}

#[test]
fn path_builder_is_pure_and_predictable() {
    let home = PathBuf::from("/tmp/example-home");
    let paths = RegistryPaths::for_home(&home, "/catalog", "/registry");
    assert_eq!(paths.runtime_db, home.join(".agentik/runtime.db"));
    assert_eq!(paths.control_db, home.join(".agentik/control.db"));
    assert_eq!(paths.hermes_state_db, home.join(".hermes/state.db"));
    assert_eq!(paths.claude_config, home.join(".claude.json"));
    assert_eq!(paths.codex_config, home.join(".codex/config.toml"));
    assert_eq!(
        paths.opencode_config,
        home.join(".config/opencode/opencode.jsonc")
    );
    assert_eq!(
        paths.opencode_config_fallback,
        home.join(".config/opencode/opencode.json")
    );
    assert_eq!(
        paths.os_assignments,
        home.join(".agentik/os-assignments.yaml")
    );
    assert_eq!(paths.agent_catalog, PathBuf::from("/catalog"));
    assert_eq!(paths.os_registry, PathBuf::from("/registry"));
}

#[test]
fn discovery_builds_a_client_without_touching_the_filesystem() {
    let client = RegistryClient::discover("operator");
    assert_eq!(client.environment, "operator");
    assert_eq!(
        client
            .paths
            .runtime_db
            .file_name()
            .and_then(|name| name.to_str()),
        Some("runtime.db")
    );
    assert_eq!(
        client
            .paths
            .control_db
            .file_name()
            .and_then(|name| name.to_str()),
        Some("control.db")
    );
}

#[test]
fn provider_and_composio_readiness_use_injected_paths() {
    let temp = TempDir::new().unwrap();
    let mut paths = paths(&temp);
    let binaries = temp.path().join("bin");
    fs::create_dir_all(&binaries).unwrap();
    for name in ["hermes", "claude", "codex", "opencode", "composio"] {
        let executable = binaries.join(name);
        fs::write(&executable, "#!/bin/sh\nexit 0\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
    }
    paths.executable_paths = vec![binaries];
    write(&paths.hermes_config, "mcp_servers: {}\n");
    write(&paths.hermes_env, "OPENROUTER_API_KEY=fake-test-value\n");
    write(
        &paths.claude_credentials,
        r#"{"claudeAiOauth":{"accessToken":"claude-test"}}"#,
    );
    write(
        &paths.codex_auth,
        r#"{"tokens":{"access_token":"codex-test"}}"#,
    );
    write(&paths.composio_auth, "{\"api_key\":\"test-key\"}\n");
    write(
        &paths.composio_inventory,
        "{\"schema_version\":1,\"authenticated\":true,\"toolkits\":[{\"name\":\"github\",\"status\":\"active\",\"connections\":1}]}\n",
    );

    let snapshot = RegistryClient::new("operator", paths.clone()).load(&[]);
    assert!(
        snapshot
            .providers
            .iter()
            .all(|provider| provider.installed && provider.configured)
    );
    assert!(snapshot.mcp_servers.iter().any(|record| {
        record.name == "Composio"
            && record.transport == "CLI · link/tools list"
            && record.status == "connected"
            && record.toolkits.len() == 1
            && record.toolkits[0].name == "github"
    }));

    write(&paths.composio_auth, "{\"api_key\":null,\"org_id\":null}\n");
    let snapshot = RegistryClient::new("mission", paths).load(&[]);
    assert!(
        snapshot
            .mcp_servers
            .iter()
            .any(|record| { record.name == "Composio" && record.status == "setup-required" })
    );
}

#[test]
fn topology_snapshot_exposes_only_redacted_profile_health() {
    let temp = TempDir::new().unwrap();
    let mut paths = paths(&temp);
    paths.topology_status = temp.path().join("topology-status.json");
    write(
        &paths.topology_status,
        r#"{
          "schema_version": 1,
          "profiles": [{
            "profile_id": "mission",
            "display_name": "Mission",
            "runtime_driver": "linux-user",
            "linux_user": "mission",
            "workspace_exists": true,
            "hermes_state_exists": true,
            "rmux_sessions": 7,
            "gateway_state": "running",
            "discord_state": "connected",
            "runtime_identity_matches": true
          }]
        }"#,
    );
    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    assert_eq!(snapshot.profiles.len(), 1);
    let profile = &snapshot.profiles[0];
    assert_eq!(profile.profile_id, "mission");
    assert_eq!(profile.rmux_sessions, Some(7));
    assert_eq!(profile.discord_state.as_deref(), Some("connected"));
}

#[test]
fn providers_distinguish_missing_installation_from_missing_setup() {
    let temp = TempDir::new().unwrap();
    let mut paths = paths(&temp);
    let binaries = temp.path().join("bin");
    fs::create_dir_all(&binaries).unwrap();
    let hermes = binaries.join("hermes");
    fs::write(&hermes, "#!/bin/sh\nexit 0\n").unwrap();
    fs::set_permissions(&hermes, fs::Permissions::from_mode(0o755)).unwrap();
    paths.executable_paths = vec![binaries];

    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    let hermes = snapshot
        .providers
        .iter()
        .find(|row| row.id == "hermes")
        .unwrap();
    let openrouter = snapshot
        .providers
        .iter()
        .find(|row| row.id == "openrouter")
        .unwrap();
    let codex = snapshot
        .providers
        .iter()
        .find(|row| row.id == "codex")
        .unwrap();
    assert!(hermes.installed && !hermes.configured);
    assert!(openrouter.installed && !openrouter.configured);
    assert!(!codex.installed && !codex.configured);
}

#[test]
fn provider_readiness_requires_real_claude_and_codex_credentials() {
    let temp = TempDir::new().unwrap();
    let mut paths = paths(&temp);
    let binaries = temp.path().join("bin");
    fs::create_dir_all(&binaries).unwrap();
    for name in ["claude", "codex"] {
        let binary = binaries.join(name);
        fs::write(&binary, "#!/bin/sh\nexit 0\n").unwrap();
        fs::set_permissions(&binary, fs::Permissions::from_mode(0o755)).unwrap();
    }
    paths.executable_paths = vec![binaries];

    let snapshot = RegistryClient::new("operator", paths.clone()).load(&[]);
    assert!(
        snapshot
            .providers
            .iter()
            .find(|row| row.id == "claude")
            .unwrap()
            .installed
    );
    assert!(
        !snapshot
            .providers
            .iter()
            .find(|row| row.id == "claude")
            .unwrap()
            .configured
    );
    assert!(
        snapshot
            .providers
            .iter()
            .find(|row| row.id == "codex")
            .unwrap()
            .installed
    );
    assert!(
        !snapshot
            .providers
            .iter()
            .find(|row| row.id == "codex")
            .unwrap()
            .configured
    );

    write(
        &paths.claude_credentials,
        r#"{"claudeAiOauth":{"accessToken":"claude-test"}}"#,
    );
    write(
        &paths.codex_auth,
        r#"{"tokens":{"access_token":"codex-test"}}"#,
    );
    let snapshot = RegistryClient::new("operator", paths).load(&[]);
    assert!(
        snapshot
            .providers
            .iter()
            .find(|row| row.id == "claude")
            .unwrap()
            .configured
    );
    assert!(
        snapshot
            .providers
            .iter()
            .find(|row| row.id == "codex")
            .unwrap()
            .configured
    );
}
