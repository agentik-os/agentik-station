from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agentik_station.errors import SecurityError, ValidationError
from agentik_station.os_runtime import (
    _profile_config, _require_clean_output, install_compiled_bundle,
    require_root_owned_directory_chain,
)


def test_profile_config_preserves_cwd_and_cannot_inject_yaml():
    project = Path('/srv/station/project: strange\nplugins:\n  enabled: [evil]')
    config = _profile_config('profile:\n  id: atlas\nterminal:\n  cwd: __PROJECT_ROOT__\n', 'forge', project)
    roundtrip = yaml.safe_load(yaml.safe_dump(config))
    assert roundtrip['terminal'] == {'cwd': str(project), 'home_mode': 'profile'}
    assert roundtrip['profile']['id'] == 'forge'
    assert roundtrip['plugins']['enabled'] == ['station-web']


@pytest.mark.parametrize('text', [
    'terminal: {}\nterminal: {}', 'terminal:\n  cwd: a\n  cwd: b',
    'terminal: []', 'profile: null', 'plugins: {}', '!!python/object:bad {}',
])
def test_invalid_template_fails_closed(text):
    with pytest.raises(ValidationError):
        _profile_config(text, 'forge', Path('/srv/station/project'))


def test_compiler_rejects_symlink_ancestor(tmp_path):
    target = tmp_path / 'target'
    target.mkdir()
    (tmp_path / 'link').symlink_to(target, target_is_directory=True)
    with pytest.raises(SecurityError):
        _require_clean_output(tmp_path / 'link' / 'missing' / 'output')


def test_privileged_publication_rejects_user_owned_parent(tmp_path):
    with pytest.raises(SecurityError):
        require_root_owned_directory_chain(tmp_path)


def test_profile_install_clears_caller_environment(tmp_path, monkeypatch):
    (tmp_path / 'COMPILED.json').write_text('{"profiles":["forge"],"os_id":"devops-os"}')
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr('subprocess.run', run)
    install_compiled_bundle(tmp_path, hermes_home=Path('/var/lib/station/zones/lab/hermes'),
                            unix_user='z-lab', hermes_binary='/usr/bin/hermes', runuser_binary='/usr/sbin/runuser')
    assert calls[0][4:6] == ['/usr/bin/env', '-i']
    assert 'HOME=/var/lib/station/zones/lab/home' in calls[0]
    assert 'PATH=/usr/local/bin:/usr/bin:/bin' in calls[0]
