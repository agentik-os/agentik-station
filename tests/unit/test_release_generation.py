"""Release checking must be genuinely read-only, including when metadata drifts."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def generator(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("release_generator", ROOT / "scripts/generate_release_metadata.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "sbom_payload", lambda: {"bomFormat": "CycloneDX", "fixture": True})
    (tmp_path / "VERSION").write_text("11.13\n")
    (tmp_path / "MANIFEST.json").write_text('{"release":"11.12","files":[],"file_count":0}\n')
    (tmp_path / "source.txt").write_text("synthetic source\n")
    assert module.main([]) == 0
    return module


def forbid_writes(*args, **kwargs):
    raise AssertionError("--check attempted a filesystem mutation")


def test_check_is_read_only_even_for_file_identity_and_timestamps(generator, monkeypatch):
    before = {path: (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
              for path in generator.ROOT.iterdir()}
    monkeypatch.setattr(Path, "write_text", forbid_writes)
    monkeypatch.setattr(Path, "unlink", forbid_writes)
    assert generator.main(["--check"]) == 0
    after = {path: (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
             for path in generator.ROOT.iterdir()}
    assert before == after


@pytest.mark.parametrize("name", ["SBOM.cdx.json", "RELEASE_PROVENANCE.json", "FILE_INDEX.md"])
def test_check_reports_drift_without_repairing_it(generator, monkeypatch, name):
    target = generator.ROOT / name
    target.write_text("deliberately stale\n")
    monkeypatch.setattr(Path, "write_text", forbid_writes)
    assert generator.main(["--check"]) == 1
    assert target.read_text() == "deliberately stale\n"


def test_check_does_not_create_missing_generated_files(generator, monkeypatch):
    target = generator.ROOT / "SBOM.cdx.json"
    target.unlink()
    monkeypatch.setattr(Path, "write_text", forbid_writes)
    assert generator.main(["--check"]) == 1
    assert not target.exists()


def test_version_and_virtual_sbom_are_bound_into_generated_metadata(generator):
    import hashlib
    root = generator.ROOT
    manifest = json.loads((root / "MANIFEST.json").read_text())
    provenance = json.loads((root / "RELEASE_PROVENANCE.json").read_text())
    assert manifest["release"] == provenance["release"] == "11.13"
    sbom_subject = next(item for item in provenance["subjects"] if item["path"] == "SBOM.cdx.json")
    assert sbom_subject["sha256"] == hashlib.sha256((root / "SBOM.cdx.json").read_bytes()).hexdigest()


def test_inventory_uses_lexical_relative_paths_not_path_component_order(generator):
    root = generator.ROOT
    (root / "source-dir").mkdir()
    (root / "source-dir/nested.md").write_text("fixture\n")
    (root / "source-dir.md").write_text("fixture\n")
    assert generator.main([]) == 0
    manifest = json.loads((root / "MANIFEST.json").read_text())
    provenance = json.loads((root / "RELEASE_PROVENANCE.json").read_text())
    subjects = [item["path"] for item in provenance["subjects"]]
    assert manifest["files"] == sorted(manifest["files"])
    assert subjects == sorted(subjects)
    assert manifest["files"].index("source-dir.md") < manifest["files"].index("source-dir/nested.md")
