//! Cached host information used by the AGK footer.
//!
//! Host probes are deliberately kept out of rendering. [`SystemInfoService`]
//! refreshes the comparatively expensive values on a short cadence, while
//! caller-owned counters (tokens and sessions) are updated on a cheap cadence.

use std::{
    fmt,
    path::{Path, PathBuf},
    process::Command,
    time::{Duration, Instant},
};

use chrono::Local;
use sysinfo::{CpuRefreshKind, Disks, MemoryRefreshKind, System as HostSystem};

pub const DEFAULT_REFRESH_INTERVAL: Duration = Duration::from_secs(2);
pub const UNKNOWN: &str = "—";

#[derive(Clone, Debug, PartialEq)]
pub struct FooterSnapshot {
    pub cwd: Option<PathBuf>,
    pub git_branch: Option<String>,
    pub cpu_percent: Option<f32>,
    pub ram_percent: Option<f32>,
    pub disk_percent: Option<f32>,
    pub session_count: usize,
    pub token_total: Option<u64>,
    pub token_model: Option<String>,
    pub local_time: String,
}

impl Default for FooterSnapshot {
    fn default() -> Self {
        Self {
            cwd: None,
            git_branch: None,
            cpu_percent: None,
            ram_percent: None,
            disk_percent: None,
            session_count: 0,
            token_total: None,
            token_model: None,
            local_time: local_hms(),
        }
    }
}

pub struct SystemInfoService {
    host: HostSystem,
    disks: Disks,
    refresh_interval: Duration,
    last_host_refresh: Option<Instant>,
    snapshot: FooterSnapshot,
}

/// Short name for callers that keep the service directly in application state.
impl fmt::Debug for SystemInfoService {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("SystemInfoService")
            .field("refresh_interval", &self.refresh_interval)
            .field("last_host_refresh", &self.last_host_refresh)
            .field("snapshot", &self.snapshot)
            .finish_non_exhaustive()
    }
}

impl Default for SystemInfoService {
    fn default() -> Self {
        Self::new()
    }
}

impl SystemInfoService {
    pub fn new() -> Self {
        Self::with_refresh_interval(DEFAULT_REFRESH_INTERVAL)
    }

    pub fn with_refresh_interval(refresh_interval: Duration) -> Self {
        let mut service = Self {
            host: HostSystem::new(),
            disks: Disks::new(),
            refresh_interval,
            last_host_refresh: None,
            snapshot: FooterSnapshot::default(),
        };
        service.force_refresh(None, None, 0);
        service
    }

    pub fn snapshot(&self) -> &FooterSnapshot {
        &self.snapshot
    }

    /// Refresh host data when its cadence expires and always accept fresh
    /// caller-owned counters. This is cheap enough to call for every frame.
    /// Refresh host data for the selected session or project directory.  A
    /// context switch refreshes immediately; a stable context keeps the normal
    /// cadence so Git and disk probes never run once per rendered frame.
    pub fn refresh_for_context(
        &mut self,
        token_total: Option<u64>,
        token_model: Option<&str>,
        session_count: usize,
        directory: Option<&Path>,
    ) -> &FooterSnapshot {
        self.snapshot.token_total = token_total;
        self.snapshot.token_model = token_model.map(str::to_owned);
        self.snapshot.session_count = session_count;
        self.snapshot.local_time = local_hms();

        let now = Instant::now();
        let context_changed = self.snapshot.cwd.as_deref() != directory;
        let due = context_changed
            || self
                .last_host_refresh
                .is_none_or(|last| now.saturating_duration_since(last) >= self.refresh_interval);
        if due {
            self.refresh_host(now, directory.map(Path::to_path_buf));
        }
        &self.snapshot
    }

    /// Refresh all values immediately, bypassing the normal cadence.
    pub fn force_refresh(
        &mut self,
        token_total: Option<u64>,
        token_model: Option<&str>,
        session_count: usize,
    ) -> &FooterSnapshot {
        self.snapshot.token_total = token_total;
        self.snapshot.token_model = token_model.map(str::to_owned);
        self.snapshot.session_count = session_count;
        self.snapshot.local_time = local_hms();
        self.refresh_host(Instant::now(), std::env::current_dir().ok());
        &self.snapshot
    }

    fn refresh_host(&mut self, now: Instant, cwd: Option<PathBuf>) {
        self.host
            .refresh_cpu_specifics(CpuRefreshKind::nothing().with_cpu_usage());
        self.host
            .refresh_memory_specifics(MemoryRefreshKind::nothing().with_ram());
        self.disks.refresh(true);

        self.snapshot.git_branch = cwd.as_deref().and_then(git_branch_at);
        self.snapshot.disk_percent = cwd
            .as_deref()
            .and_then(|path| disk_percent_for_path(&self.disks, path));
        self.snapshot.cwd = cwd;
        self.snapshot.cpu_percent = if self.host.cpus().is_empty() {
            None
        } else {
            finite_percent(self.host.global_cpu_usage())
        };
        self.snapshot.ram_percent =
            ratio_percent(self.host.used_memory(), self.host.total_memory());
        self.last_host_refresh = Some(now);
    }
}

/// Return the current branch for `directory`, or `None` for non-repositories,
/// detached HEADs, missing Git, and malformed command output.
pub fn git_branch_at(directory: &Path) -> Option<String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(directory)
        .args(["symbolic-ref", "--quiet", "--short", "HEAD"])
        .env("GIT_OPTIONAL_LOCKS", "0")
        .env("GIT_TERMINAL_PROMPT", "0")
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }

    let branch = String::from_utf8(output.stdout).ok()?;
    let branch = branch.trim();
    (!branch.is_empty()).then(|| branch.to_owned())
}

pub fn finite_percent(value: f32) -> Option<f32> {
    value.is_finite().then(|| value.clamp(0.0, 100.0))
}

pub fn ratio_percent(used: u64, total: u64) -> Option<f32> {
    if total == 0 {
        return None;
    }
    finite_percent((used as f64 * 100.0 / total as f64) as f32)
}

pub fn format_percent(value: Option<f32>) -> String {
    value
        .and_then(finite_percent)
        .map(|value| format!("{value:.0}%"))
        .unwrap_or_else(|| UNKNOWN.to_owned())
}

pub fn format_token_total(total: u64) -> String {
    const THOUSAND: f64 = 1_000.0;
    const MILLION: f64 = 1_000_000.0;
    const BILLION: f64 = 1_000_000_000.0;

    match total {
        0..=999 => total.to_string(),
        1_000..=999_999 => format!("{:.1}K", total as f64 / THOUSAND),
        1_000_000..=999_999_999 => format!("{:.1}M", total as f64 / MILLION),
        _ => format!("{:.1}B", total as f64 / BILLION),
    }
}

pub fn format_optional_token_total(total: Option<u64>) -> String {
    total
        .map(format_token_total)
        .unwrap_or_else(|| UNKNOWN.to_owned())
}

fn local_hms() -> String {
    Local::now().format("%H:%M:%S").to_string()
}

fn disk_percent_for_path(disks: &Disks, path: &Path) -> Option<f32> {
    let disk = disks
        .list()
        .iter()
        .filter(|disk| path.starts_with(disk.mount_point()))
        .max_by_key(|disk| disk.mount_point().components().count())?;
    ratio_percent(
        disk.total_space().saturating_sub(disk.available_space()),
        disk.total_space(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        process::{Command, Stdio},
        time::{SystemTime, UNIX_EPOCH},
    };

    #[test]
    fn percentage_helpers_clamp_and_handle_unknown_values() {
        assert_eq!(finite_percent(-12.5), Some(0.0));
        assert_eq!(finite_percent(120.0), Some(100.0));
        assert_eq!(finite_percent(f32::NAN), None);
        assert_eq!(finite_percent(f32::INFINITY), None);
        assert_eq!(ratio_percent(1, 4), Some(25.0));
        assert_eq!(ratio_percent(2, 1), Some(100.0));
        assert_eq!(ratio_percent(10, 0), None);
        assert_eq!(format_percent(Some(42.6)), "43%");
        assert_eq!(format_percent(None), UNKNOWN);
    }

    #[test]
    fn token_totals_use_compact_stable_units() {
        assert_eq!(format_token_total(999), "999");
        assert_eq!(format_token_total(1_000), "1.0K");
        assert_eq!(format_token_total(12_345), "12.3K");
        assert_eq!(format_token_total(1_500_000), "1.5M");
        assert_eq!(format_token_total(2_000_000_000), "2.0B");
        assert_eq!(format_optional_token_total(None), UNKNOWN);
        assert_eq!(format_optional_token_total(Some(12_345)), "12.3K");
    }

    #[test]
    fn caller_counters_update_even_when_host_refresh_is_not_due() {
        let mut info = SystemInfoService::with_refresh_interval(Duration::from_secs(60));
        let before = info.last_host_refresh;
        let context = info.snapshot.cwd.clone();
        let snapshot = info.refresh_for_context(
            Some(7_654),
            Some("claude-sonnet-4-6"),
            9,
            context.as_deref(),
        );
        assert_eq!(snapshot.token_total, Some(7_654));
        assert_eq!(snapshot.token_model.as_deref(), Some("claude-sonnet-4-6"));
        assert_eq!(snapshot.session_count, 9);
        assert_eq!(info.last_host_refresh, before);
    }

    #[test]
    fn git_branch_lookup_uses_the_repository_containing_the_cwd() {
        if !Command::new("git")
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
        {
            return;
        }

        let repo = TempRepo::new();
        run_git(&repo.path, &["init", "--quiet"]);
        run_git(
            &repo.path,
            &["symbolic-ref", "HEAD", "refs/heads/footer-test"],
        );
        let nested = repo.path.join("nested").join("deeper");
        fs::create_dir_all(&nested).expect("create nested test directory");

        assert_eq!(git_branch_at(&nested).as_deref(), Some("footer-test"));
    }

    struct TempRepo {
        path: PathBuf,
    }

    impl TempRepo {
        fn new() -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "agk-tui-system-info-{}-{nonce}",
                std::process::id()
            ));
            fs::create_dir(&path).expect("create temporary repository");
            Self { path }
        }
    }

    impl Drop for TempRepo {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn run_git(repo: &Path, args: &[&str]) {
        let status = Command::new("git")
            .arg("-C")
            .arg(repo)
            .args(args)
            .env("GIT_OPTIONAL_LOCKS", "0")
            .env("GIT_TERMINAL_PROMPT", "0")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .expect("run git for test repository");
        assert!(status.success(), "git command failed: {args:?}");
    }
}
