import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { protectedStatePreserved, assertIdle } from '../update.mjs';
import { installationDiagnostics, safeInstallPhase } from '../cli.mjs';
import { createContext, initialize, atomicJSON } from '../state.mjs';

const root = 'personal/home/os/stepper-os';
const checks = ['distribution', 'native-profiles'].map(kind => ({ id: `os:stepper-os:${kind}`, required: true, status: 'verified' }));
const prior = [['personal/home/.hermes/config.yaml', 'file', 0o600, 'old-hash']];
const added = [['personal/home/os', 'dir', 0o700], [root, 'dir', 0o700], [`${root}/OS_INSTALL.json`, 'file', 0o600, 'new-hash']];

test('11.30 to new OS release may add verified previously absent OS state', () => {
  assert.equal(protectedStatePreserved(prior, [...prior, ...added], [root], checks), true);
});

test('new OS allowance never permits changing or dropping existing account state', () => {
  assert.equal(protectedStatePreserved(prior, [['personal/home/.hermes/config.yaml', 'file', 0o600, 'changed'], ...added], [root], checks), false);
  assert.equal(protectedStatePreserved(prior, added, [root], checks), false);
});

test('new OS roots need both actual required native checks, not mere presence', () => {
  for (const failed of [[], checks.slice(0, 1), checks.map(row => ({ ...row, status: 'failed' })), checks.map(row => ({ ...row, required: false }))]) {
    assert.equal(protectedStatePreserved(prior, [...prior, ...added], [root], failed), false);
  }
});

test('previous OS state can never be relabeled newly created', () => {
  const before = [...prior, ...added];
  assert.equal(protectedStatePreserved(before, before, [root], checks), false);
  assert.equal(protectedStatePreserved(before, before, [], checks), true);
});

test('unrelated or broad paths cannot be added as migration exceptions', () => {
  assert.equal(protectedStatePreserved(prior, [...prior, ...added], ['personal/home/os'], checks), false);
  assert.equal(protectedStatePreserved(prior, [...prior, ...added, ['personal/home/os/another-client', 'dir', 0o700]], [root], checks), false);
  assert.equal(protectedStatePreserved(prior, [...prior, ['personal/home/.env', 'file', 0o600, 'new']], [root], checks), false);
});

test('OS diagnostic ids are useful without leaking native errors or account data', () => {
  assert.equal(safeInstallPhase('os:stepper-os'), 'os:stepper-os');
  assert.equal(safeInstallPhase('os:secret-account'), null);
  const report = installationDiagnostics({ phase: 'os:stepper-os', status: 'failed', checks: [{ ...checks[1], status: 'failed', detail: 'private native output' }] }, 1);
  assert.equal(report.failedRequiredChecks[0].id, 'os:stepper-os:native-profiles');
  assert.equal(JSON.stringify(report).includes('private native output'), false);
});

async function idleFixture(t, platform = 'linux', id = 'stepper-os') {
  const parent = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'station-os-idle-')));
  t.after(() => fs.rm(parent, { recursive: true, force: true }));
  const ctx = await createContext({ root: path.join(parent, 'station'), platform,
    accountHome: path.join(parent, 'account'), sourceRoot: fileURLToPath(new URL('../../../', import.meta.url)) });
  await initialize(ctx);
  const state = path.join(ctx.home, 'os', id), receipt = path.join(state, 'OS_INSTALL.json');
  await fs.mkdir(state, { recursive: true, mode: 0o700 });
  const mapping = Object.fromEntries(['map-steward', 'shaper', 'sequencer'].map(role => [role,
    `w-${createHash('sha256').update([ctx.root, ctx.profile, id, role].join('\0')).digest('hex').slice(0, 16)}-${role}`]));
  const profiles = Object.values(mapping).sort();
  const record = { schema_version: 1, root: ctx.root, workstation_profile: ctx.profile, uid: process.getuid(),
    compiled: { schema_version: 4, os_id: id, os_version: '0.1.0', profiles,
      nano_director: mapping['map-steward'], role_profile_map: mapping,
      workspace_root: path.join(ctx.root, 'personal/os', id, 'workspace'), hermes_home: path.join(state, 'hermes'),
      boundary: 'personal-same-uid', claim: 'COMPILED_NOT_INSTALLED', inputs_sha256: 'a'.repeat(64), artifacts_sha256: 'b'.repeat(64) },
    profiles: Object.fromEntries(profiles.map(name => [name, 'installed'])) };
  await atomicJSON(receipt, record);
  const calls = [], run = async (binary, argv) => {
    calls.push({ binary, argv });
    return binary === '/bin/ps' ? { code: 0, stdout: `${process.pid} ${process.ppid} updater\n`, stderr: '' }
      : platform === 'darwin' ? { code: 113, stdout: '', stderr: 'Could not find service' }
        : { code: 0, stdout: 'not-found\n', stderr: '' };
  };
  return { ctx, state, receipt, record, profiles, calls, run };
}

for (const location of ['account-systemd', 'private-systemd', 'account-launchd', 'private-launchd']) {
  test(`a stopped recorded specialist ${location} definition blocks update before native calls`, async t => {
    const f = await idleFixture(t), profile = f.profiles.at(-1);
    const home = location.startsWith('account') ? f.ctx.accountHome : f.ctx.home;
    const definition = location.endsWith('systemd') ? path.join(home, '.config/systemd/user', `hermes-gateway-${profile}.service`)
      : path.join(home, 'Library/LaunchAgents', `ai.hermes.gateway-${profile}.plist`);
    await fs.mkdir(path.dirname(definition), { recursive: true, mode: 0o700 });
    await fs.writeFile(definition, 'SYNTHETIC_STOPPED_DEFINITION', { mode: 0o600 });
    const before = await fs.readFile(f.receipt);
    await assert.rejects(assertIdle(f.ctx, f), /definition exists/);
    assert.equal(f.calls.length, 0);
    assert.deepEqual(await fs.readFile(f.receipt), before);
    assert.equal(await fs.readFile(definition, 'utf8'), 'SYNTHETIC_STOPPED_DEFINITION');
  });
}

for (const platform of ['linux', 'darwin']) test(`loaded stopped OS gateway blocks ${platform} migration`, async t => {
  const f = await idleFixture(t, platform), selected = f.profiles.at(-1);
  const run = async (binary, argv) => {
    const result = await f.run(binary, argv);
    return argv.some(arg => arg.includes(selected)) ? { code: 0, stdout: platform === 'darwin' ? 'state = waiting' : 'loaded\n', stderr: '' } : result;
  };
  await assert.rejects(assertIdle(f.ctx, { run }), /absence could not be proved/);
  assert(f.calls.some(call => call.argv.some(arg => arg.includes(selected))));
  assert(f.calls.every(call => call.binary === '/bin/ps' || ['show', 'print'].includes(call.argv[0]) || call.argv[0] === '--user'));
});

for (const selector of ['--profile ', '--profile=', '-p ', '--profile "']) test(`recorded OS process ${selector} blocks migration without a root path in argv`, async t => {
  const f = await idleFixture(t), selected = f.profiles.at(-1);
  const run = async (binary, argv) => binary === '/bin/ps'
    ? { code: 0, stdout: `${process.pid} ${process.ppid} updater\n987654 1 hermes ${selector}${selected}${selector.endsWith('"') ? '"' : ''} chat\n`, stderr: '' }
    : f.run(binary, argv);
  await assert.rejects(assertIdle(f.ctx, { run }), /recorded OS profile/);
  assert.equal(f.calls.length, 0);
});

for (const id of ['stepper-os', 'builder-os', 'librarian-os']) test(`idle checks cover every recorded ${id} specialist without reading native config or credentials`, async t => {
  const f = await idleFixture(t, 'darwin', id), opened = [];
  const open = fs.open.bind(fs);
  t.mock.method(fs, 'open', async (target, ...args) => { opened.push(String(target)); return open(target, ...args); });
  await assertIdle(f.ctx, f);
  assert.deepEqual(opened, [f.receipt]);
  for (const profile of [f.ctx.profile, ...f.profiles]) {
    for (const domain of ['gui', 'user']) assert(f.calls.some(call => call.argv.includes(`${domain}/${process.getuid()}/ai.hermes.gateway-${profile}`)));
  }
});

for (const defect of ['foreign-root', 'foreign-uid', 'wrong-os', 'foreign-home', 'malicious-role', 'malicious-profile',
  'other-valid-profile', 'missing-status', 'invalid-status', 'digest-array']) test(`invalid OS service identity ${defect} is refused before process/service probes`, async t => {
  const f = await idleFixture(t), c = f.record.compiled;
  if (defect === 'foreign-root') f.record.root += '-other';
  if (defect === 'foreign-uid') f.record.uid++;
  if (defect === 'wrong-os') c.os_id = 'builder-os';
  if (defect === 'foreign-home') c.hermes_home = f.ctx.accountHome;
  if (defect === 'malicious-role') c.role_profile_map['../../unrelated'] = f.profiles[0];
  if (defect === 'malicious-profile') c.profiles[0] = '../../unrelated;touch';
  if (defect === 'other-valid-profile') c.role_profile_map['map-steward'] = 'w-0000000000000000-map-steward';
  if (defect === 'missing-status') delete f.record.profiles[f.profiles[0]];
  if (defect === 'invalid-status') f.record.profiles[f.profiles[0]] = 'adopted';
  if (defect === 'digest-array') c.inputs_sha256 = ['a'.repeat(64)];
  await atomicJSON(f.receipt, f.record);
  const before = await fs.readFile(f.receipt);
  await assert.rejects(assertIdle(f.ctx, f), /Invalid or unrecorded/);
  assert.equal(f.calls.length, 0);
  assert.deepEqual(await fs.readFile(f.receipt), before);
});

test('an unrecorded OS directory is not adopted for idle checks', async t => {
  const f = await idleFixture(t);
  await fs.unlink(f.receipt);
  await assert.rejects(assertIdle(f.ctx, f));
  assert.equal(f.calls.length, 0);
  assert.deepEqual(await fs.readdir(f.state), []);
});

test('a linked OS receipt is refused without inspecting its target', async t => {
  const f = await idleFixture(t), target = path.join(f.ctx.projects, 'unrelated.json');
  await fs.writeFile(target, 'PRIVATE_SYNTHETIC_CONTENT', { mode: 0o600 });
  await fs.unlink(f.receipt);
  await fs.symlink(target, f.receipt);
  await assert.rejects(assertIdle(f.ctx, f), /Unsafe path/);
  assert.equal(f.calls.length, 0);
  assert.equal(await fs.readFile(target, 'utf8'), 'PRIVATE_SYNTHETIC_CONTENT');
});
