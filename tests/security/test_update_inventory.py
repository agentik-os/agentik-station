import json
from pathlib import Path
import subprocess

import pytest

from agentik_station import cli, updates, hermes_updates
from agentik_station.paths import LayoutPaths

ROOT = Path(__file__).resolve().parents[2]


def test_all_source_repositories_and_sbom_components_are_accounted_for():
    result = updates.inventory(ROOT)
    sources = {row['source'] for row in result['components']}
    for key, value in result['pins'].items():
        if key.endswith('_REPOSITORY'): assert value in sources
    bom = json.loads((ROOT/'SBOM.cdx.json').read_text())
    assert {row['bom-ref'] for row in bom['components']} <= {row['id'] for row in result['components']}
    assert result['component_count'] == len(result['components'])
    assert result['pin_count'] == len(result['pins'])
    assert result['applied'] is False and result['compatible'] is False


def test_discovery_failures_and_manual_oci_review_cannot_disappear():
    called = []
    def fetch(kind, source):
        called.append((kind, source))
        return {'status': 'UNAVAILABLE', 'latest': None} if kind == 'npm' else {'status': 'OBSERVED_NOT_ACCEPTED', 'latest': 'v99.0.0'}
    result = updates.check(ROOT, fetch=fetch)
    assert len(called) == len(set(called))
    assert result['discovery_complete'] is False
    assert result['collection_succeeded'] is False
    assert any(row['upstream']['status'] == 'UNAVAILABLE' for row in result['components'])
    assert all(row['upstream']['status'] == 'REVIEW_REQUIRED' for row in result['components'] if row['kind'] == 'container')
    assert all(row['compatibility'] == 'NOT_ACCEPTED' for row in result['components'])


def test_manual_review_is_not_a_failed_collection_or_an_accepted_update(monkeypatch, capsys):
    result = updates.check(ROOT, fetch=lambda *a: {'status': 'OBSERVED_NOT_ACCEPTED', 'latest': 'v99.0.0'})
    assert result['collection_succeeded'] is True
    assert result['discovery_complete'] is False
    assert result['applied'] is False and result['compatible'] is False
    monkeypatch.setattr(updates, 'check', lambda *a: result)
    args = cli.build_parser().parse_args(['update', 'check'])
    assert args.handler(args) == 0
    assert json.loads(capsys.readouterr().out)['discovery_complete'] is False


def test_missing_published_releases_remain_explicit_successful_metadata_requests():
    result = updates.check(ROOT, fetch=lambda *a: {'status': 'NO_RELEASE_METADATA', 'latest': None})
    assert result['collection_succeeded'] is True
    assert result['discovery_complete'] is False


@pytest.mark.parametrize('kind,source', [('github', '../private'), ('github-commit', '../private'), ('npm', 'https://evil.invalid'), ('pypi', '../../key')])
def test_arbitrary_discovery_targets_rejected_without_network(kind, source, monkeypatch):
    monkeypatch.setattr(updates, 'build_opener', lambda *a: pytest.fail('network must not run'))
    assert updates.fetch_metadata(kind, source)['status'] == 'REVIEW_REQUIRED'


def hermes_fixture(tmp_path):
    paths = LayoutPaths.under(tmp_path.resolve())
    source = paths.software / 'tools/hermes/current'
    source.mkdir(parents=True)
    (source/'pyproject.toml').write_text('[project]\nname="hermes-agent"\n')
    return paths, source


def test_tarball_check_never_invokes_git_native_cli_or_real_profile(tmp_path, monkeypatch):
    paths, source = hermes_fixture(tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('no native command'))
    before = sorted(str(p.relative_to(source)) for p in source.rglob('*'))
    result = hermes_updates.run_check(paths, fetch=lambda *a: {'status': 'OBSERVED_NOT_ACCEPTED', 'latest': 'v2026.9.4'})
    assert result['status'] == 'PLAN_READY'
    assert result['source']['distribution'] == 'immutable-or-tarball'
    assert result['source']['commit'] is None
    assert result['commands'] == [] and result['account_accessed'] is False
    assert sorted(str(p.relative_to(source)) for p in source.rglob('*')) == before


def test_git_identity_observation_is_not_source_content_verification(tmp_path):
    _, source = hermes_fixture(tmp_path)
    (source/'.git').mkdir(); (source/'.git/HEAD').write_text('a'*40+'\n')
    result = hermes_updates.source_observation(source)
    assert result['commit'] == 'a'*40
    assert result['state'] == 'SOURCE_ID_OBSERVED_NOT_CONTENT_VERIFIED'


def test_malicious_git_metadata_never_exports_arbitrary_content(tmp_path):
    _, source = hermes_fixture(tmp_path)
    (source/'.git').mkdir(); (source/'.git/HEAD').write_text('ref: refs/../../SECRET\n')
    (source/'SECRET').write_text('PRIVATE_TEST_ONLY')
    assert 'PRIVATE_TEST_ONLY' not in json.dumps(hermes_updates.source_observation(source))
    (source/'.git/HEAD').unlink(); (source/'.git/HEAD').symlink_to(source/'SECRET')
    assert hermes_updates.source_observation(source)['commit'] is None


def test_escaped_runtime_link_is_not_accepted(tmp_path):
    _, source = hermes_fixture(tmp_path)
    outside = tmp_path/'outside'; source.rename(outside); source.symlink_to(outside)
    assert hermes_updates.source_observation(source)['state'] == 'SOURCE_PROVENANCE_NOT_VERIFIED'


def test_cli_surfaces_clear_state_and_update_modes():
    parser = cli.build_parser()
    assert parser.parse_args(['status', '--software']).software
    assert parser.parse_args(['update', 'plan']).handler is cli.cmd_update_inventory
    assert parser.parse_args(['update', 'check']).handler is cli.cmd_update_inventory


def test_scheduled_updater_only_runs_coupled_discovery_before_native_state():
    source = (ROOT/'scripts/station_hermes_update.sh').read_text()
    block = source.split('if [[ "${1:-update}" == auto ]]; then', 1)[1].split('\nfi', 1)[0]
    assert 'exec /usr/bin/python3 -I -B /opt/station/current/station update check' in block
    assert source.index(block) < source.index('HERMES_HOME_VALUE=')
    assert '--backup' not in block and '--yes' not in block


def test_cli_client_versions_are_not_compared_to_server_releases():
    result = updates.inventory(ROOT)
    rows = {row['name']: row for row in result['components']}
    assert rows['ChatbotX CLI']['source'] == 'chatbotx'
    assert rows['ChatbotX CLI']['discovery'] == 'npm'
    assert rows['Honcho']['source'] == 'honcho-ai'
    assert rows['Hindsight']['source'] == 'hindsight-client'
    for name in ('langfuse', 'honcho', 'hindsight', 'chatbotx'):
        assert rows[name + ' server']['kind'] == 'server-source'


def test_commit_pins_track_default_branch_without_inventing_a_release():
    result = updates.inventory(ROOT)
    rows = {row['name']: row for row in result['components']}
    for name in ('AGK_TUI', 'CHATBOTX', 'HONCHO'):
        assert rows[name]['discovery'] == 'github-commit'
        assert len(rows[name]['pinned']) == 40


@pytest.mark.parametrize('payload,expected', [([{'sha': 'a'*40}], 'OBSERVED_NOT_ACCEPTED'),
                                            ([{'sha': 'secret'}], 'UNAVAILABLE'),
                                            ({'sha': 'a'*40}, 'UNAVAILABLE')])
def test_commit_metadata_is_bounded_public_observation(payload, expected, monkeypatch):
    from io import BytesIO
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == 'https://api.github.com/repos/agentik-os/AGK-TUI/commits?per_page=1'
            assert not request.has_header('Authorization')
            return BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(updates, 'build_opener', lambda *a: Opener())
    result = updates.fetch_metadata('github-commit', 'agentik-os/AGK-TUI')
    assert result['status'] == expected
    if expected == 'OBSERVED_NOT_ACCEPTED':
        assert result['track'] == 'default-branch-commit-not-a-release'


def test_watcher_records_unique_private_observations_without_changing_profiles(tmp_path):
    paths, source = hermes_fixture(tmp_path)
    fetch = lambda *a: {'status': 'OBSERVED_NOT_ACCEPTED', 'latest': 'v2026.8.31'}
    one = hermes_updates.run_check(paths, record=True, fetch=fetch)
    two = hermes_updates.run_check(paths, record=True, fetch=fetch)
    assert one['receipt'] != two['receipt']
    assert Path(one['receipt']).stat().st_mode & 0o777 == 0o600
    assert one['commands'] == []


def test_hermes_update_alias_cannot_independently_mutate_a_live_runtime(monkeypatch, capsys):
    monkeypatch.setattr(hermes_updates, 'run_check', lambda *a: {'status': 'PLAN_READY', 'applied': False})
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('no native updater'))
    args = cli.build_parser().parse_args(['hermes', 'update'])
    assert args.handler(args) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'COORDINATED_RELEASE_REQUIRED'
