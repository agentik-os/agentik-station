"""Real-Git, offline source-suite publication and adversarial readback."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("builder_suite", ROOT / "scripts/builder_suite.py")
suite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suite)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(root):
    git(root, "add", "--all")
    git(root, "-c", "user.name=Suite Test", "-c", "user.email=suite@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-m", "synthetic suite")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def source(tmp_path, monkeypatch):
    # File ownership is real; simulated UID only permits the fixture writer when
    # this unit suite is deliberately run as root in an isolated test environment.
    monkeypatch.setattr(suite.os, "geteuid", lambda: 1000)
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q")
    (root / "scripts").mkdir()
    (root / suite.GENERATOR).write_bytes((ROOT / suite.GENERATOR).read_bytes())
    (root / "VERSION").write_text("11.35\n")
    rows = []
    for name, version in zip(suite.PACKAGES, ("11.14", "3.0.1", "0.2.0")):
        path = root / "os" / name
        path.mkdir(parents=True)
        (path / "CONTRACT.json").write_text(json.dumps({
            "os_id": f"{name}-os", "version": version,
            "nano_director": f"{name}-director", "nanoteam": [f"{name}-worker"],
        }))
        (path / "MANIFEST.json").write_text(json.dumps({"id": f"{name}-os", "version": version}))
        (path / "README.md").write_text(f"Synthetic {name} source\n")
        rows.append({"id": f"{name}-os", "path": f"os/{name}", "version": version})
    (root / "os/CATALOG.json").write_text(json.dumps({"packages": rows}))
    return root, commit(root), tmp_path / "station-suite"


def test_export_exact_deterministic_committed_snapshot_and_standalone_verify(source):
    root, ref, output = source
    # A dirty source checkout must not leak into the pinned publication.
    (root / "os/builder/README.md").write_text("Uncommitted replacement\n")
    first = suite.export(root, ref, output)
    assert first["ok"] and first["source_compared"] and not first["operational"]
    assert first["source_commit"] == ref
    assert [p["id"] for p in first["packages"]] == [f"{p}-os" for p in suite.PACKAGES]
    assert (output / "os/builder/README.md").read_text() == "Synthetic builder source\n"
    before = suite.inventory(output)
    assert suite.export(root, ref, output) == first
    other = output.parent / "second-suite"
    suite.export(root, ref, other)
    assert suite.inventory(other) == before
    proc = subprocess.run([os.sys.executable, "-B", str(output / "verify.py"),
                           "verify", "--suite", str(output), "--station", str(root), "--check-current"],
                          check=True, capture_output=True, text=True)
    report = json.loads(proc.stdout)
    assert report["current_packages_compared"] and report["claim"] == "SOURCE_SNAPSHOT_NOT_RUNTIME"


@pytest.mark.parametrize("ref", ["main", "HEAD", "--help", "a" * 39, "A" * 40, "../source"])
def test_export_requires_exact_immutable_ref(source, ref):
    root, _, output = source
    with pytest.raises(suite.SuiteError, match="immutable Git commit"):
        suite.export(root, ref, output)
    assert not output.exists()


@pytest.mark.parametrize("entry", ["symlink", "secret", "cache", "export-ignore", "export-subst"])
def test_rejects_unsupported_committed_source_before_creating_output(source, entry):
    root, _, output = source
    path = root / "os/builder"
    if entry == "symlink":
        (path / "link").symlink_to("README.md")
    elif entry == "secret":
        (path / ".env").write_text("SYNTHETIC=not-a-secret")
        git(root, "add", "-f", "os/builder/.env")
    elif entry == "cache":
        (path / "cache.pyc").write_bytes(b"synthetic")
    elif entry == "export-ignore":
        (root / ".gitattributes").write_text("os/builder/README.md export-ignore\n")
    else:
        (path / "README.md").write_text("$Format:%H$\n")
        (root / ".gitattributes").write_text("os/builder/README.md export-subst\n")
    ref = commit(root)
    with pytest.raises(suite.SuiteError):
        suite.export(root, ref, output)
    assert not output.exists()


@pytest.mark.parametrize("fault", ["catalog-version", "contract-id", "manifest-version", "duplicate-role", "missing-package"])
def test_source_identity_must_match_all_three_complete_packages(source, fault):
    root, _, output = source
    if fault == "catalog-version":
        file = root / "os/CATALOG.json"
        value = json.loads(file.read_text())
        value["packages"][0]["version"] = "0.5.0"
    elif fault == "manifest-version":
        file = root / "os/builder/MANIFEST.json"
        value = json.loads(file.read_text())
        value["version"] = "0.5.0"
    elif fault == "missing-package":
        (root / "os/stepper/CONTRACT.json").unlink()
        with pytest.raises((suite.SuiteError, KeyError)):
            suite.export(root, commit(root), output)
        assert not output.exists()
        return
    else:
        file = root / "os/builder/CONTRACT.json"
        value = json.loads(file.read_text())
        value["os_id" if fault == "contract-id" else "nanoteam"] = (
            "different-os" if fault == "contract-id" else [value["nano_director"]])
    file.write_text(json.dumps(value))
    with pytest.raises(suite.SuiteError):
        suite.export(root, commit(root), output)
    assert not output.exists()


@pytest.mark.parametrize("fault", ["edit", "extra", "missing", "symlink", "hardlink", "fifo", "mode", "empty-dir"])
def test_modified_or_unsafe_suite_is_not_verified_or_overwritten(source, fault):
    root, ref, output = source
    suite.export(root, ref, output)
    victim = output / "os/builder/README.md"
    if fault == "edit":
        victim.write_text("edited")
    elif fault == "extra":
        (output / "extra.txt").write_text("extra")
    elif fault == "mode":
        victim.chmod(0o666)
    elif fault == "empty-dir":
        (output / "extra").mkdir()
    else:
        victim.unlink()
        if fault == "symlink":
            victim.symlink_to(output / "os/librarian/README.md")
        elif fault == "hardlink":
            os.link(output / "os/librarian/README.md", victim)
        elif fault == "fifo":
            os.mkfifo(victim)
    with pytest.raises((suite.SuiteError, OSError, KeyError)):
        suite.verify(output)
    with pytest.raises((suite.SuiteError, OSError, KeyError)):
        suite.export(root, ref, output)


def test_regenerate_requires_new_destination_and_current_source_drift_is_visible(source):
    root, ref, output = source
    suite.export(root, ref, output)
    (root / "os/stepper/README.md").write_text("New canonical Stepper source\n")
    updated = commit(root)
    assert suite.verify(output, root)["ok"]
    with pytest.raises(suite.SuiteError, match="Canonical OS packages changed"):
        suite.verify(output, root, check_current=True)
    before = suite.inventory(output)
    with pytest.raises(suite.SuiteError, match="Destination differs"):
        suite.export(root, updated, output)
    assert suite.inventory(output) == before
    suite.export(root, updated, output.parent / "new-suite")


def test_exact_source_verification_detects_rewritten_local_manifest(source):
    root, ref, output = source
    suite.export(root, ref, output)
    path = "os/builder/README.md"
    (output / path).write_bytes(b"changed")
    manifest = json.loads((output / "MANIFEST.json").read_text())
    manifest["files"][path].update(sha256=suite.digest(b"changed"), size=7)
    (output / "MANIFEST.json").write_bytes(suite.encoded(manifest))
    assert suite.verify(output)["source_compared"] is False
    with pytest.raises(suite.SuiteError, match="pinned Station commit"):
        suite.verify(output, root)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "os//builder/x", "os/./builder/x", "os\\builder\\x"])
def test_manifest_paths_are_not_path_authorities(name):
    with pytest.raises(suite.SuiteError):
        suite.relative(name)


def test_missing_source_binding_and_root_publication_are_explicit(source, monkeypatch):
    root, ref, output = source
    suite.export(root, ref, output)
    with pytest.raises(suite.SuiteError, match="explicit Station checkout"):
        suite.verify(output, check_current=True)
    monkeypatch.setattr(suite.os, "geteuid", lambda: 0)
    with pytest.raises(suite.SuiteError, match="non-root"):
        suite.export(root, ref, output.parent / "root-output")


def test_unknown_generator_is_not_used_to_publish_an_old_source(source):
    root, _, output = source
    (root / suite.GENERATOR).write_text("# different exporter\n")
    with pytest.raises(suite.SuiteError, match="generator from the selected"):
        suite.export(root, commit(root), output)


def test_swapped_intermediate_directory_never_redirects_publication(source, monkeypatch):
    root, ref, output = source
    outside = output.parent / "outside"
    outside.mkdir()
    original = suite.os.open
    attacked = []

    def swapped(path, flags, *args, **kwargs):
        if path == "builder" and kwargs.get("dir_fd") is not None and not attacked:
            attacked.append(True)
            parent = kwargs["dir_fd"]
            os.rmdir("builder", dir_fd=parent)
            os.symlink(str(outside), "builder", dir_fd=parent)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(suite.os, "open", swapped)
    with pytest.raises(OSError):
        suite.export(root, ref, output)
    assert attacked and not list(outside.iterdir())
    assert output.stat().st_mode & 0o777 == 0o700


def test_publication_permissions_do_not_follow_permissive_umask(source):
    root, ref, output = source
    previous = os.umask(0)
    try:
        suite.export(root, ref, output)
    finally:
        os.umask(previous)
    assert output.stat().st_mode & 0o777 == 0o755
    for path in output.rglob("*"):
        assert path.stat().st_mode & 0o022 == 0


@pytest.mark.parametrize("file,contents", [
    ("SUITE.json", []), ("SUITE.json", None), ("MANIFEST.json", []),
    ("os/builder/CONTRACT.json", []), ("os/builder/MANIFEST.json", False),
])
def test_malformed_metadata_shapes_have_redacted_cli_errors(source, capsys, file, contents):
    root, ref, output = source
    suite.export(root, ref, output)
    data = suite.encoded(contents)
    (output / file).write_bytes(data)
    if file != "MANIFEST.json":
        manifest = json.loads((output / "MANIFEST.json").read_text())
        manifest["files"][file].update(sha256=suite.digest(data), size=len(data))
        (output / "MANIFEST.json").write_bytes(suite.encoded(manifest))
    assert suite.main(["verify", "--suite", str(output)]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is False
    assert not captured.err and "Traceback" not in captured.out


@pytest.mark.parametrize("entries", [None, {}, [42], [None]])
def test_malformed_source_catalog_is_refused_before_export(source, entries):
    root, _, output = source
    (root / "os/CATALOG.json").write_text(json.dumps({"packages": entries}))
    with pytest.raises(suite.SuiteError):
        suite.export(root, commit(root), output)
    assert not output.exists()


def test_actual_canonical_suite_roundtrip_includes_all_source_files_and_29_roles(source):
    root, _, output = source
    for package in suite.PACKAGES:
        shutil.copytree(ROOT / "os" / package, root / "os" / package, dirs_exist_ok=True)
    shutil.copyfile(ROOT / "os/CATALOG.json", root / "os/CATALOG.json")
    ref = commit(root)
    report = suite.export(root, ref, output)
    assert sum(row["profile_count"] for row in report["packages"]) == 29
    expected = {path.relative_to(root).as_posix() for package in suite.PACKAGES
                for path in (root / "os" / package).rglob("*") if path.is_file()}
    observed = {name for name in suite.inventory(output) if name.startswith("os/")}
    assert observed == expected
    assert suite.verify(output, root, check_current=True)["ok"]
