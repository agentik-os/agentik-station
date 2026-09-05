#!/usr/bin/python3
"""Secret-free native route check, run only as the selected Zone profile owner."""
from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import pwd
import re
import sys


def key_value(value):
    # Native key_cmd is a refreshable CommandTokenSource, not a stored string.
    if callable(value):
        value = value()
    if not isinstance(value, str) or not value:
        raise ValueError('Native credential unavailable')
    return value


def check():
    uid = os.geteuid()
    account = pwd.getpwuid(uid)
    if uid == 0 or uid != os.getuid() or not re.fullmatch(
            r'/var/lib/station/zones/[a-z0-9][a-z0-9-]{0,62}/home', account.pw_dir):
        raise ValueError('Wrong identity')
    selected = Path(os.environ['HERMES_HOME'])
    state = Path(account.pw_dir).parent
    if (not selected.is_relative_to(state / 'os-instances') or selected.name == 'profiles'
            or selected.parent.name != 'profiles' or selected.resolve() != selected
            or selected.stat().st_uid != uid):
        raise ValueError('Wrong profile')
    sys.path.insert(0, '/opt/station/tools/hermes/current')
    logging.disable(logging.CRITICAL)
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        from hermes_cli.env_loader import load_hermes_dotenv
        from hermes_cli.config import load_config_readonly
        from hermes_cli.runtime_provider import resolve_runtime_provider
        load_hermes_dotenv()
        if os.environ.get('HERMES_HOME') != str(selected):
            raise ValueError('Profile redirected')
        config = load_config_readonly()
        model = config.get('model', {})
        if model.get('provider') != 'custom:station-inference' or model.get('default') != 'hermes-default':
            raise ValueError('Explicit model differs')
        runtime = resolve_runtime_provider(requested=model['provider'], target_model=model['default'])
        spec = importlib.util.spec_from_file_location('station_capability', Path(__file__).with_name('token.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        token = module.capability()
        if (runtime.get('provider') != 'custom' or runtime.get('api_mode') != 'codex_responses'
                or runtime.get('base_url', '').rstrip('/') != 'http://127.0.0.1:8791'
                or key_value(runtime.get('api_key')) != token):
            raise ValueError('Native runtime differs')
    return {'state': 'NATIVE_ROUTE_VERIFIED', 'model': 'hermes-default',
            'provider': 'custom:station-inference', 'live_inference_tested': False}


def main():
    try:
        result = check()
    except Exception:
        print(json.dumps({'state': 'NATIVE_ROUTE_FAILED', 'live_inference_tested': False}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
