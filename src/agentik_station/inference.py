"""Explicit Zone inference sharing; source accounts never enter target profiles.

The broker is a model transport, not another agent. Enrollment changes only a
native named provider and missing model preferences. Package, memory, tools and
gateway identities remain owned by the existing instance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re
import socket

from .errors import SecurityError, ValidationError
from .filesystem import SafeFS
from .identifiers import validate_identifier
from .installer import install_lock
from .models import new_operation_id
from .native_process import run_bounded_native
from . import os_lifecycle as lifecycle, os_instances, voice
from .hermes_platforms import build_gateway_argv

PORT = 8791
PROVIDER = 'custom:station-inference'
MODEL = 'hermes-default'
UNIT = 'station-inference.service'
SOURCE = {'operator': 'agk-station', 'hermes_home': '/home/agk-station/.hermes'}
REPAIR = ('Inspect this exact Zone inference binding and native model configuration; '
          'preserve unrelated accounts and profiles. Retry the scoped enrollment, then '
          'verify its whole OS team. Configuration alone is not live model acceptance.')


def _uid(paths):
    return os.getuid() if paths.test_mode else 0


def _root(paths):
    return paths.software / 'inference'


def _read(paths, path):
    return lifecycle.read_runtime_json(path, uid=_uid(paths), immutable=True,
                                       trusted_root=paths.software if paths.test_mode else None)


def _config(paths, *, missing=False):
    try:
        value = _read(paths, _root(paths) / 'config.json')
    except FileNotFoundError:
        if missing:
            return None
        raise ValidationError('Inference sharing is not enabled; run station model enable --plan') from None
    if (set(value) != {'schema_version', 'port', 'source', 'grants'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or type(value['port']) is not int or value['port'] != PORT or value['source'] != SOURCE
            or not isinstance(value['grants'], list) or len(value['grants']) > 256):
        raise ValidationError('Invalid inference service configuration')
    seen, users, hashes = set(), set(), set()
    for grant in value['grants']:
        if not isinstance(grant, dict) or set(grant) != {'zone_id', 'uid', 'token_sha256'}:
            raise ValidationError('Invalid inference grant')
        zone_id = validate_identifier(grant['zone_id'], 'inference Zone')
        uid = grant['uid']
        if (not isinstance(uid, int) or isinstance(uid, bool) or not 0 < uid < 2**31
                or zone_id in seen or uid in users or not isinstance(grant['token_sha256'], str)
                or not re.fullmatch('[a-f0-9]{64}', grant['token_sha256'])):
            raise ValidationError('Invalid or duplicate inference identity')
        seen.add(zone_id)
        users.add(uid)
        if grant['token_sha256'] in hashes:
            raise ValidationError('Duplicate inference capability')
        hashes.add(grant['token_sha256'])
    return value


def _save(paths, path, value):
    config = path.name == 'config.json'
    gid = os.getgid() if paths.test_mode else (pwd.getpwnam('agk-station').pw_gid if config else 0)
    SafeFS(paths.allowed_roots).write_text(path, json.dumps(value, indent=2, sort_keys=True) + '\n',
                                          mode=0o640 if config else 0o600, owner=(_uid(paths), gid))


def _native(argv, *, timeout=60):
    result = run_bounded_native([str(item) for item in argv], timeout=timeout, capture=True)
    if result.returncode:
        raise ValidationError('Inference operation failed in its selected native identity. ' + REPAIR)
    return result


def _immutable_repo(repo, paths):
    version = (repo / 'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version):
        raise ValidationError('Invalid Station release version')
    if not paths.test_mode and repo != paths.releases / version:
        raise SecurityError('Enable inference from the active immutable Station release, not a writable checkout')
    for name in ('broker.py', 'token.py', 'preflight.py', 'profile_check.py'):
        lifecycle._read_bytes(repo / 'runtime/inference' / name, uid=_uid(paths), immutable=True,
                              trusted_root=repo if paths.test_mode else None)


def _unit(repo):
    return '\n'.join([
        '[Unit]', 'Description=Station source-owned inference transport (no agent execution)',
        'After=network-online.target', 'Wants=network-online.target', '', '[Service]',
        'Type=simple', 'User=agk-station', 'Group=agk-station',
        'WorkingDirectory=/home/agk-station',
        'Environment=HOME=/home/agk-station', 'Environment=HERMES_HOME=/home/agk-station/.hermes',
        'Environment=PATH=/usr/local/bin:/usr/bin:/bin', 'Environment=PYTHONDONTWRITEBYTECODE=1',
        'ExecStart=/opt/station/tools/hermes/current/venv/bin/python -I -B '
        + str(repo / 'runtime/inference/broker.py') + ' --config /opt/station/inference/config.json',
        'Restart=on-failure', 'RestartSec=5', 'UMask=0077', 'NoNewPrivileges=true',
        'PrivateTmp=true', 'ProtectSystem=strict', 'ProtectHome=read-only',
        'ReadWritePaths=/home/agk-station/.hermes', 'PrivateDevices=true',
        'ProtectKernelTunables=true', 'ProtectKernelModules=true', 'ProtectControlGroups=true',
        'RestrictSUIDSGID=true', 'RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX',
        'CapabilityBoundingSet=', 'AmbientCapabilities=', 'TasksMax=64',
        'MemoryMax=1G', 'StandardOutput=null', 'StandardError=null', '',
        '[Install]', 'WantedBy=multi-user.target', '',
    ])


def enable(repo, paths, *, plan=False):
    """Explicit source-owned service activation; no Zone is automatically granted."""
    _immutable_repo(repo, paths)
    current = _config(paths, missing=True)
    account = pwd.getpwnam('agk-station')
    if account.pw_uid == 0 or account.pw_dir != '/home/agk-station':
        raise SecurityError('Inference source must be the existing dedicated operator')
    unit = _unit(repo).encode()
    token = lifecycle._read_bytes(repo / 'runtime/inference/token.py', uid=_uid(paths), immutable=True,
                                  trusted_root=repo if paths.test_mode else None)
    wanted = ((paths.systemd / UNIT, unit, 0o644), (paths.bin / 'station-inference-token', token, 0o755))
    previous = {}
    for destination, content, mode in wanted:
        try:
            old = lifecycle._read_bytes(destination, uid=_uid(paths), immutable=True,
                                         trusted_root=destination.parent if paths.test_mode else None)
        except FileNotFoundError:
            previous[destination] = None
            continue
        previous[destination] = old
    old_unit = previous[paths.systemd / UNIT]
    if old_unit is not None and old_unit != unit:
        match = re.search(rb'^ExecStart=/opt/station/tools/hermes/current/venv/bin/python -I -B (\S+)/runtime/inference/broker.py --config /opt/station/inference/config.json$', old_unit, re.M)
        if not match:
            raise SecurityError('Unknown existing inference service; no automatic adoption')
        old_repo = Path(match[1].decode('ascii'))
        _immutable_repo(old_repo, paths)
        if old_unit != _unit(old_repo).encode():
            raise SecurityError('Existing inference service contains unreviewed overrides')
    else:
        old_repo = repo
    old_token = previous[paths.bin / 'station-inference-token']
    if old_token is not None and old_token != token:
        expected = lifecycle._read_bytes(old_repo / 'runtime/inference/token.py', uid=_uid(paths), immutable=True,
                                         trusted_root=old_repo if paths.test_mode else None)
        if old_token != expected:
            raise SecurityError('Existing inference helper is not the previous immutable release')
    result = {'state': 'PREPARED', 'source': SOURCE, 'listen': f'127.0.0.1:{PORT}',
              'zone_grants': len(current['grants']) if current else 0,
              'operational': False, 'provider_authenticated': False,
              'account_sharing': 'Inference only; no source credentials are copied',
              'service': UNIT, 'next_repair_action': REPAIR}
    if plan:
        return result
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError('Inference enable requires the authorized Station operator')
    with install_lock(paths, new_operation_id()):
        if _config(paths, missing=True) != current:
            raise SecurityError('Inference configuration changed; rerun the enable plan')
        for destination, _, _ in wanted:
            try:
                old = lifecycle._read_bytes(destination, uid=_uid(paths), immutable=True,
                                             trusted_root=destination.parent if paths.test_mode else None)
            except FileNotFoundError:
                old = None
            if old != previous[destination]:
                raise SecurityError('Inference software changed while waiting for the lock')
        _native(['/usr/bin/python3', '-I', '-B', repo / 'runtime/inference/preflight.py',
                 '--repair-known-modes'], timeout=180)
        # Never bind on top of an unrelated listener or adopt an existing unit.
        if current is None:
            try:
                with socket.create_connection(('127.0.0.1', PORT), timeout=0.5):
                    raise SecurityError('Inference port is occupied; no service was changed')
            except (ConnectionRefusedError, TimeoutError):
                pass
        fs = SafeFS(paths.allowed_roots)
        # Validate existing anchors before mkdir may adjust their metadata.
        for directory in (_root(paths), _root(paths) / 'bindings'):
            try:
                with lifecycle._directory(directory, uid=_uid(paths), trusted_root=paths.software if paths.test_mode else None):
                    pass
            except FileNotFoundError:
                pass
        fs.mkdir(_root(paths), 0o750, owner=(_uid(paths), os.getgid() if paths.test_mode else account.pw_gid))
        fs.mkdir(_root(paths) / 'bindings', 0o700, owner=(_uid(paths), os.getgid() if paths.test_mode else 0))
        if current is None:
            _save(paths, _root(paths) / 'config.json', {'schema_version': 1, 'port': PORT, 'source': SOURCE, 'grants': []})
        for destination, content, mode in wanted:
            fs.write_bytes(destination, content, mode, owner=(_uid(paths), os.getgid() if paths.test_mode else 0))
        actions = [['daemon-reload'], ['enable', '--now', UNIT]]
        if old_unit is not None and old_unit != unit:
            actions.append(['restart', UNIT])
        for args in (*actions, ['is-active', UNIT]):
            _native(['/usr/bin/systemctl', *args])
    return {**result, 'state': 'SERVICE_ACTIVE_NO_MODEL_ACCEPTANCE'}


def _binding(paths, zone, *, missing=False):
    zone_id = validate_identifier(zone['id'], 'inference Zone')
    try:
        binding = _read(paths, _root(paths) / 'bindings' / (zone_id + '.json'))
    except FileNotFoundError:
        if missing:
            return None
        raise ValidationError('This Zone has no explicit Hermes inference grant') from None
    context = lifecycle._context(paths, zone)
    expected = {'schema_version', 'zone_id', 'uid', 'organization_id', 'environment',
                'instances', 'token_sha256', 'revoked'}
    if (set(binding) != expected or type(binding['schema_version']) is not int or binding['schema_version'] != 1
            or type(binding['uid']) is not int
            or binding['zone_id'] != zone_id or binding['uid'] != context['uid']
            or binding['organization_id'] != zone.get('organization')
            or binding['environment'] != zone['environment']
            or not isinstance(binding['instances'], list) or not binding['instances']
            or not all(isinstance(item, str) for item in binding['instances'])
            or len(binding['instances']) > 64 or len(set(binding['instances'])) != len(binding['instances'])
            or not isinstance(binding['revoked'], bool)
            or not isinstance(binding['token_sha256'], str)
            or not re.fullmatch('[a-f0-9]{64}', binding['token_sha256'])):
        raise SecurityError('Inference binding does not match this canonical Zone identity')
    for instance in binding['instances']:
        validate_identifier(instance, 'inference instance')
    return binding


def _token_digest(paths, zone, *, create=False):
    context = lifecycle._context(paths, zone)
    lifecycle._read_bytes(paths.bin / 'station-inference-token', uid=_uid(paths), immutable=True,
                          trusted_root=paths.bin if paths.test_mode else None)
    argv = ['/usr/sbin/runuser', '--user', zone['unix_user'], '--', '/usr/bin/env', '-i',
            'PATH=/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE=1',
            str(paths.bin / 'station-inference-token'), '--create' if create else '--digest']
    result = _native(argv)
    try:
        data = json.loads(result.stdout)
        digest = data['token_sha256']
    except (ValueError, KeyError, TypeError):
        raise ValidationError('Inference token helper returned invalid evidence') from None
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise ValidationError('Inference token digest is invalid')
    return context, digest


def grant(paths, zone, instances, *, plan=False, revoke=False):
    """Owner-authorized Zone capability, enrollment limited to named instances."""
    config = _config(paths)
    instances = sorted({validate_identifier(item, 'inference instance') for item in instances})
    if not instances and not revoke:
        raise ValidationError('Name at least one intended OS instance')
    if len(instances) > 64:
        raise ValidationError('Too many intended inference instances')
    context = lifecycle._context(paths, zone)
    for instance in instances:
        record = os_instances.load_os_instance_record(paths, zone=zone, instance_id=instance, require_configured=True)
        if record['organization_id'] != zone.get('organization'):
            raise SecurityError('OS inference ownership differs from the Zone')
    if revoke:
        result = {'state': 'PREPARED', 'zone_id': zone['id'], 'revoke': True, 'operational': False}
        if plan:
            return result
        if not paths.test_mode and os.geteuid() != 0:
            raise SecurityError('Inference grants require Station root authority')
        with install_lock(paths, new_operation_id()):
            latest = _config(paths)
            # A broken enrollment ledger must never prevent authorization removal.
            others = [row for row in latest['grants'] if row['zone_id'] != zone['id']]
            _save(paths, _root(paths) / 'config.json', {**latest, 'grants': others})
            metadata_repair = False
            try:
                binding = _binding(paths, zone, missing=True)
                if binding:
                    _save(paths, _root(paths) / 'bindings' / (zone['id'] + '.json'), {**binding, 'revoked': True})
            except (SecurityError, ValidationError, OSError):
                metadata_repair = True
        return {**result, 'state': 'REVOKED', 'token_retained': True, 'metadata_repair_required': metadata_repair,
                'in_flight_streams': 'Previously accepted requests may finish; subsequent requests are denied'}
    binding = _binding(paths, zone, missing=True)
    grant_row = next((row for row in config['grants'] if row['zone_id'] == zone['id']), None)
    if grant_row and (not binding or binding['revoked'] or grant_row['uid'] != context['uid']
                      or grant_row['token_sha256'] != binding['token_sha256']):
        raise SecurityError('Inference grant/binding conflict; no automatic adoption')
    result = {'state': 'PREPARED', 'zone_id': zone['id'], 'organization_id': zone.get('organization'),
              'instances': instances, 'scope': 'Zone UID inference capability; instances are enrollment scope, not Unix isolation',
              'source': SOURCE, 'model': MODEL, 'operational': False, 'revoke': revoke,
              'next_repair_action': REPAIR}
    if plan:
        return result
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError('Inference grants require Station root authority')
    with install_lock(paths, new_operation_id()):
        # Re-read authority inside the common Station mutation lock.
        latest = _config(paths)
        if latest != config or _binding(paths, zone, missing=True) != binding:
            raise SecurityError('Inference policy changed; rerun the scoped plan')
        others = [row for row in config['grants'] if row['zone_id'] != zone['id']]
        if len(others) >= 256 or any(row['uid'] == context['uid'] for row in others):
            raise SecurityError('Inference grant capacity or identity conflicts with existing clients')
        _, digest = _token_digest(paths, zone, create=binding is None)
        if binding and digest != binding['token_sha256']:
            raise SecurityError('Existing target token changed; no automatic replacement')
        if any(row['token_sha256'] == digest for row in others):
            raise SecurityError('Inference capability conflicts with another Zone')
        binding = {'schema_version': 1, 'zone_id': zone['id'], 'uid': context['uid'],
                   'organization_id': zone.get('organization'), 'environment': zone['environment'],
                   'instances': instances, 'token_sha256': digest, 'revoked': False}
        _save(paths, _root(paths) / 'bindings' / (zone['id'] + '.json'), binding)
        # Publish network authorization last; partial earlier work cannot grant inference.
        _save(paths, _root(paths) / 'config.json', {**config, 'grants': others + [
            {'zone_id': zone['id'], 'uid': context['uid'], 'token_sha256': digest}]})
    return {**result, 'state': 'GRANTED_NOT_MODEL_ACCEPTED'}


def inheritance_plan(paths, zone, record, role):
    binding = _binding(paths, zone, missing=True)
    if binding is None or binding['revoked'] or record['instance_id'] not in binding['instances']:
        return None
    role = role or next(key for key, value in record['role_profile_map'].items() if value == record['nano_director'])
    _, context, profile, profile_root, data = voice._scope(paths, zone, record['instance_id'], role)
    model = data.get('model', {})
    if isinstance(model, str) and model:
        return {'state': 'EXPLICIT_MODEL_PRESERVED', 'profile': profile, 'mutates': False}
    if not isinstance(model, dict):
        raise ValidationError('Target model configuration is invalid')
    if any(model.get(key) not in (None, '') for key in
           ('base_url', 'api_key', 'api_key_env', 'key_cmd', 'transport', 'api_mode')):
        return {'state': 'EXPLICIT_MODEL_PRESERVED', 'profile': profile, 'mutates': False}
    providers = data.get('providers', {})
    if not isinstance(providers, dict):
        raise ValidationError('Target named providers must be a mapping')
    settings = {'name': 'station-inference', 'base_url': f'http://127.0.0.1:{PORT}',
                'transport': 'codex_responses', 'key_cmd': str(paths.bin / 'station-inference-token'),
                'default_model': MODEL}
    selected = model.get('provider') == PROVIDER
    if (model.get('default') or model.get('provider')) and not selected:
        return {'state': 'EXPLICIT_MODEL_PRESERVED', 'profile': profile, 'mutates': False}
    if selected and model.get('default') not in (None, '', MODEL):
        return {'state': 'EXPLICIT_MODEL_PRESERVED', 'profile': profile, 'mutates': False}
    config = _config(paths)
    row = next((item for item in config['grants'] if item['zone_id'] == zone['id']), None)
    if row != {'zone_id': zone['id'], 'uid': binding['uid'], 'token_sha256': binding['token_sha256']}:
        raise SecurityError('Inference binding has no matching current grant')
    if providers.get('station-inference') not in (None, settings):
        raise ValidationError('Existing station-inference provider differs; preserve it for explicit review')
    inherited = selected and model.get('default') == MODEL and providers.get('station-inference') == settings
    return {'state': 'INHERITED' if inherited else 'INHERITANCE_PREPARED', 'mutates': not inherited,
            'profile': profile, 'role': role, 'instance_id': record['instance_id'], 'zone_id': zone['id'],
            'model': MODEL, 'source': SOURCE, 'provider': PROVIDER, 'settings': settings,
            'profile_root': str(profile_root), 'operational': False,
            'next_repair_action': REPAIR}


def enroll_profile(paths, zone, record, role=None, *, plan=False):
    intent = inheritance_plan(paths, zone, record, role)
    if plan or intent is None or not intent['mutates']:
        if not plan and intent is not None and intent['state'] == 'INHERITED':
            intent['runtime_check'] = _runtime_check(paths, zone, intent)
        return intent
    if not paths.test_mode and os.geteuid() != 0:
        raise SecurityError('Model enrollment requires the authorized Station operator')
    with install_lock(paths, new_operation_id()):
        if inheritance_plan(paths, zone, record, role) != intent:
            raise SecurityError('Target model preference changed; preserve it and inspect again')
        context = lifecycle._context(paths, zone)
        prefix = build_gateway_argv(zone, 'doctor', runtime_uid=context['uid'],
                                    hermes_binary=Path('/usr/local/bin/hermes'),
                                    director_profile=intent['profile'], instance_id=record['instance_id'])[:-1]
        voice._effective_profile(prefix, Path(intent['profile_root']))
        # Native effective reads reject dotted-key/managed-overlay ambiguity.
        current_model = voice._effective_value(prefix, 'model', {})
        if (not isinstance(current_model, dict) or current_model.get('provider') not in (None, '', PROVIDER)
                or current_model.get('default') not in (None, '', MODEL)
                or any(current_model.get(key) not in (None, '') for key in
                       ('base_url', 'api_key', 'api_key_env', 'key_cmd', 'transport', 'api_mode'))):
            raise SecurityError('Effective target model differs; existing preference was preserved')
        for key in ('model.provider', 'model.default', 'providers.station-inference'):
            voice._effective_value(prefix, key, None)
        for key, value in (('providers.station-inference', json.dumps(intent['settings'])),
                           ('model.provider', PROVIDER), ('model.default', MODEL)):
            _native(prefix + ['config', 'set', key, value])
        if (voice._effective_value(prefix, 'model.provider') != PROVIDER
                or voice._effective_value(prefix, 'model.default') != MODEL
                or voice._effective_value(prefix, 'providers.station-inference') != intent['settings']):
            raise ValidationError('Native inference model readback differs. ' + REPAIR)
    return {**intent, 'state': 'INHERITED', 'mutates': False, 'verification_required': True,
            'runtime_check': _runtime_check(paths, zone, intent)}


def _runtime_check(paths, zone, intent):
    helper = Path(__file__).resolve().parents[2] / 'runtime/inference/profile_check.py'
    lifecycle._read_bytes(helper, uid=_uid(paths), immutable=True,
                          trusted_root=helper.parent if paths.test_mode else None)
    argv = ['/usr/sbin/runuser', '--user', zone['unix_user'], '--', '/usr/bin/env', '-i',
            'HOME=' + str(lifecycle._context(paths, zone)['home']),
            'HERMES_HOME=' + intent['profile_root'], 'PATH=/usr/local/bin:/usr/bin:/bin',
            'PYTHONDONTWRITEBYTECODE=1', '/opt/station/tools/hermes/current/venv/bin/python',
            '-I', '-B', str(helper)]
    reply = _native(argv)
    try:
        data = json.loads(reply.stdout)
    except (ValueError, TypeError):
        raise ValidationError('Native inference route check returned invalid evidence') from None
    if data != {'state': 'NATIVE_ROUTE_VERIFIED', 'model': MODEL, 'provider': PROVIDER,
                'live_inference_tested': False}:
        raise ValidationError('Native inference route check did not verify the intended local transport')
    return data
