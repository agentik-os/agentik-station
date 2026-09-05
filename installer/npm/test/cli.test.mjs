import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createContext, initialize } from '../state.mjs';

const entry = fileURLToPath(new URL('../cli.mjs', import.meta.url));

async function fixture(t) {
  // These fixtures contain no real accounts, native services or model tools.
  // macOS's default per-account temporary path alone can exceed RMUX's socket
  // limit; use the canonical short sticky directory with our private child.
  const temporaryRoot = process.platform === 'darwin' ? '/private/tmp' : os.tmpdir();
  const parent = await fs.realpath(await fs.mkdtemp(path.join(temporaryRoot, 'station-cli-')));
  const bin = path.join(parent, 'fake-bin');
  const home = path.join(parent, 'untouched-home');
  const root = path.join(parent, 'station root');
  await fs.mkdir(bin, { mode: 0o700 });
  await fs.mkdir(home, { mode: 0o700 });
  await fs.writeFile(path.join(home, 'sentinel'), 'personal state stays unchanged\n', { mode: 0o600 });
  for (const name of ['uv', 'git', 'cargo', 'curl', 'npm']) {
    // Discovery can stat these; execution always fails without a real tool.
    await fs.writeFile(path.join(bin, name), '#!/bin/sh\nprintf "unexpected native execution\\n" >&2\nexit 97\n', { mode: 0o700 });
  }
  t.after(() => fs.rm(parent, { recursive: true, force: true }));
  return { parent, root, bin, home };
}

function execute(f, args, entrypoint = entry) {
  const result = spawnSync(process.execPath, [entrypoint, ...args], {
    cwd: f.parent, env: { PATH: f.bin, HOME: f.home, NO_COLOR: '1', CI: '1' },
    stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8', timeout: 10000, maxBuffer: 256 * 1024,
  });
  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.signal, null);
  assert.doesNotMatch(result.stdout + result.stderr, /unexpected native execution/);
  return result;
}

function json(result) {
  assert.equal(result.stderr, '', 'machine-readable output must not be mixed with human stderr');
  assert.doesNotMatch(result.stdout, /\u001b/);
  return JSON.parse(result.stdout);
}

async function untouched(f) {
  await assert.rejects(fs.lstat(f.root), { code: 'ENOENT' });
  assert.deepEqual(await fs.readdir(f.home), ['sentinel']);
  assert.equal(await fs.readFile(path.join(f.home, 'sentinel'), 'utf8'), 'personal state stays unchanged\n');
}

test('help is read-only and documents separate workstation and Host modes', async t => {
  const f = await fixture(t);
  const result = execute(f, ['--help']);
  assert.equal(result.status, 0);
  assert.equal(result.stderr, '');
  assert.match(result.stdout, /Chief AI Officer/);
  assert.match(result.stdout, /no sudo/);
  assert.match(result.stdout, /Host/);
  await untouched(f);
});

test('help --json is valid JSON with no banner or native output', async t => {
  const f = await fixture(t);
  const result = execute(f, ['--help', '--json']);
  assert.equal(result.status, 0);
  assert.match(json(result).help, /agentik-station plan/);
  await untouched(f);
});

test('plan JSON preserves spaced root and deterministic profile without creating it', async t => {
  const f = await fixture(t);
  const first = execute(f, ['plan', '--json', '--root', f.root]);
  const second = execute(f, ['plan', '--root', f.root, '--json']);
  assert.equal(first.status, 0);
  const plan = json(first);
  assert.equal(plan.mode, 'workstation');
  assert.equal(plan.root, f.root);
  assert.match(plan.profile, /^station-[a-f0-9]{12}$/);
  assert.equal(plan.profile, json(second).profile);
  assert.ok(plan.steps.length >= 3);
  assert.ok(plan.warnings.some(value => /not a Zone/.test(value)));
  await untouched(f);
});

test('Host mode returns a review plan and never invokes privileged installation', async t => {
  const f = await fixture(t);
  const plan = execute(f, ['plan', '--mode', 'host', '--root', f.root, '--json']);
  assert.equal(plan.status, 0);
  assert.equal(json(plan).status, 'review-required');
  const install = execute(f, ['install', '--mode', 'host', '--yes', '--root', f.root, '--json']);
  assert.equal(install.status, 2);
  assert.equal(json(install).mode, 'host');
  await untouched(f);
});

for (const args of [
  ['--json', '--invalid-option'],
  ['--invalid-option', '--json'],
  ['plan', '--json', '--root'],
  ['plan', '--json', '--root', 'relative/station'],
  ['plan', '--json', '--mode', 'unknown'],
  ['not-a-command', '--json'],
]) {
  test(`argument failure stays JSON and read-only: ${JSON.stringify(args)}`, async t => {
    const f = await fixture(t);
    const result = execute(f, args);
    assert.equal(result.status, 1);
    const report = json(result);
    assert.equal(report.status, 'failed');
    assert.equal(report.checks[0].status, 'failed');
    await untouched(f);
  });
}

test('nonTTY install without --yes refuses before creating a root or running tools', { skip: process.getuid() === 0 }, async t => {
  const f = await fixture(t);
  const result = execute(f, ['install', '--root', f.root, '--json']);
  assert.equal(result.status, 1);
  const report = json(result);
  assert.equal(report.status, 'failed');
  assert.match(report.checks[0].detail, /No changes made.*--yes/);
  await untouched(f);
});

test('explicit install refuses to adopt an occupied root and preserves its sentinel', { skip: process.getuid() === 0 }, async t => {
  const f = await fixture(t);
  await fs.mkdir(f.root, { mode: 0o700 });
  const sentinel = path.join(f.root, 'existing-project');
  await fs.writeFile(sentinel, 'keep this exact content\n', { mode: 0o600 });
  const result = execute(f, ['install', '--yes', '--root', f.root, '--json']);
  assert.equal(result.status, 1);
  assert.match(json(result).checks[0].detail, /not a recognized Station Workstation/);
  assert.deepEqual(await fs.readdir(f.root), ['existing-project']);
  assert.equal(await fs.readFile(sentinel, 'utf8'), 'keep this exact content\n');
});

test('missing-install verification returns failed JSON without creating state', async t => {
  const f = await fixture(t);
  const result = execute(f, ['verify', '--root', f.root, '--json']);
  assert.equal(result.status, 1);
  assert.match(json(result).checks[0].detail, /No recognized installation/);
  await untouched(f);
});

test('tui --json is refused before any interactive process or installation access', async t => {
  const f = await fixture(t);
  const result = execute(f, ['tui', '--root', f.root, '--json']);
  assert.equal(result.status, 1);
  assert.match(json(result).checks[0].detail, /TUI.*does not support --json/);
  await untouched(f);
});

test('unknown equals-form and positional arguments never echo synthetic secrets', async t => {
  const f = await fixture(t);
  const sentinel = 'SYNTHETIC_TOKEN_NOT_A_REAL_CREDENTIAL_0123456789';
  for (const candidate of [`--token=${sentinel}`, sentinel]) {
    for (const machine of [false, true]) {
      const result = execute(f, ['plan', candidate, ...(machine ? ['--json'] : [])]);
      assert.equal(result.status, 1);
      assert.equal((result.stdout + result.stderr).includes(sentinel), false);
      if (machine) assert.equal(json(result).status, 'failed');
      else assert.match(result.stderr, /Unknown option/);
    }
  }
  await untouched(f);
});

test('npm-style executable symlink runs the CLI instead of silently importing it', async t => {
  const f = await fixture(t);
  const link = path.join(f.bin, 'agentik-station');
  await fs.symlink(entry, link);
  const result = execute(f, ['plan', '--root', f.root, '--json'], link);
  assert.equal(result.status, 0);
  assert.equal(json(result).root, f.root);
  await untouched(f);
});

test('failed software checks still give safely quoted next commands for literal root paths', { skip: process.getuid() === 0 }, async t => {
  const f = await fixture(t);
  f.root = path.join(f.parent, "Station's workspace ; literal");
  const sourceRoot = fileURLToPath(new URL('../../../', import.meta.url));
  const ctx = await createContext({ root: f.root, sourceRoot });
  // Only the ownership envelope exists: no Hermes, accounts or native software.
  // Verification exercises inert prerequisite fixtures and missing-tool errors.
  await initialize(ctx);
  const result = execute(f, ['verify', '--root', f.root, '--json']);
  assert.equal(result.status, 1);
  const report = json(result);
  assert.equal(report.status, 'failed');
  const quotedRoot = `'${f.root.replaceAll("'", "'\\''")}'`;
  const quotedLauncher = `'${path.join(f.root, 'bin', 'agk').replaceAll("'", "'\\''")}'`;
  assert.deepEqual(report.next, [quotedLauncher, ...['model', 'discord', 'activate'].map(command => `agentik-station ${command} --root ${quotedRoot}`)]);
  assert.equal(JSON.parse(await fs.readFile(report.receipt, 'utf8')).status, 'failed');
  assert.deepEqual(await fs.readdir(f.home), ['sentinel']);
});
