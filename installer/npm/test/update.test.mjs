import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createContext, initialize, atomicJSON } from '../state.mjs';
import { updateRoots, recordSoftware, softwareSnapshot, updatePlan, applyUpdate, recoverUpdate, requireNoPendingUpdate, assertIdle, acquireRecoveryLock } from '../update.mjs';
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const sourceRoot = fileURLToPath(new URL('../../../', import.meta.url));
async function fixture(t) {
  const parent = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'station-update-')));
  t.after(() => fs.rm(parent, { recursive: true, force: true }));
  const ctx = { ...await createContext({ root: path.join(parent, 'station'), sourceRoot }), release: '11.29', platform: 'linux', accountHome: path.join(parent, 'account') };
  await initialize(ctx);
  for (const relative of updateRoots(ctx)) {
    await fs.mkdir(path.join(ctx.root, relative), { recursive: true, mode: 0o700 });
    await fs.writeFile(path.join(ctx.root, relative, 'software'), 'OLD', { mode: 0o600 });
  }
  await fs.writeFile(path.join(ctx.projects, 'keep'), 'PROJECT');
  const privateProfile = path.join(ctx.hermesHome, 'profiles', ctx.profile);
  await fs.writeFile(path.join(privateProfile, '.env'), 'SYNTHETIC_PRIVATE_TEST', { mode: 0o600 });
  await fs.writeFile(path.join(privateProfile, 'config.yaml'), 'kept: true\n', { mode: 0o600 });
  await recordSoftware(ctx, { initial: true });
  const next = { ...ctx, release: '11.30', pins: { ...ctx.pins, HERMES_COMMIT: 'a'.repeat(40) } };
  const run = async binary => ({ code: 0, stdout: binary === '/bin/ps' ? `${process.pid} ${process.ppid} synthetic-node\n` : 'not-found\n', stderr: '' });
  const provision = async updated => {
    assert.equal(updated.preserveEnrollment, true);
    for (const relative of updateRoots(updated)) await fs.writeFile(path.join(updated.root, relative, 'software'), 'NEW', { mode: 0o600 });
  };
  const verify = async () => [{ id: 'synthetic', required: true, status: 'verified' }];
  return { ctx, next, privateProfile, run, provision, verify };
}

test('plan covers all changed pins without writes, credential reads or executing native software', async t => {
  const f = await fixture(t), before = await fs.readdir(f.ctx.evidence);
  const plan = await updatePlan(f.next);
  assert.equal(plan.from, '11.29'); assert.equal(plan.to, '11.30');
  assert.deepEqual(plan.changedPins, ['HERMES_COMMIT']);
  assert.equal(plan.operational, false); assert.deepEqual(await fs.readdir(f.ctx.evidence), before);
});
test('legacy installations without predecessor baseline are refused, not adopted', async t => {
  const f = await fixture(t); await fs.unlink(path.join(f.ctx.root, '.station-software.json'));
  await assert.rejects(updatePlan(f.next), /Legacy installations/);
});
test('a FIFO substituted for private evidence cannot hang the update planner', async t => {
  const f = await fixture(t), target = path.join(f.ctx.root, '.station-software.json');
  await fs.unlink(target);
  assert.equal(spawnSync('/usr/bin/mkfifo', ['-m', '600', target]).status, 0);
  const script = `import {createContext} from ${JSON.stringify(new URL('../state.mjs', import.meta.url).href)};
    import {updatePlan} from ${JSON.stringify(new URL('../update.mjs', import.meta.url).href)};
    const ctx=await createContext({root:process.argv[1],sourceRoot:process.argv[2]});
    try { await updatePlan(ctx); process.exitCode=1; } catch { process.exitCode=0; }`;
  const checked = spawnSync(process.execPath, ['--input-type=module', '-e', script, f.ctx.root, sourceRoot],
    { timeout: 3000, encoding: 'utf8' });
  assert.equal(checked.error, undefined); assert.equal(checked.status, 0);
});
test('modified and added software is preserved and blocks updates', async t => {
  const f = await fixture(t);
  await fs.writeFile(path.join(f.ctx.tools, 'custom'), 'USER_CHANGE');
  await assert.rejects(applyUpdate(f.next, f), /Customizations are preserved/);
  assert.equal(await fs.readFile(path.join(f.ctx.tools, 'custom'), 'utf8'), 'USER_CHANGE');
  assert.deepEqual(await fs.readdir(f.ctx.evidence), []);
});
test('refuse downgrade, immutable pin drift and overwritten initial baseline', async t => {
  const f = await fixture(t);
  await assert.rejects(updatePlan({ ...f.ctx, release: '11.28' }), /Downgrades/);
  await assert.rejects(updatePlan({ ...f.next, release: '11.29' }), /Same release/);
  await assert.rejects(recordSoftware(f.ctx, { initial: true }), /baseline/);
});
test('same release is a no-op and does not stop services or reinstall tools', async t => {
  const f = await fixture(t);
  const result = await applyUpdate(f.ctx, { run: () => assert.fail('no native command') });
  assert.equal(result.softwareChanged, false);
});
test('verified update rebuilds at final paths and retains recoverable previous software only', async t => {
  const f = await fixture(t), result = await applyUpdate(f.next, f);
  assert.equal(result.to, '11.30'); assert.equal(result.servicesRestarted, false);
  for (const relative of updateRoots(f.ctx)) assert.equal(await fs.readFile(path.join(f.ctx.root, relative, 'software'), 'utf8'), 'NEW');
  assert.equal(await fs.readFile(path.join(result.evidence, 'old-1/software'), 'utf8'), 'OLD');
  assert.equal(await fs.readFile(path.join(f.privateProfile, '.env'), 'utf8'), 'SYNTHETIC_PRIVATE_TEST');
  assert.equal(await fs.readFile(path.join(f.ctx.projects, 'keep'), 'utf8'), 'PROJECT');
  assert.equal((await updatePlan(f.next)).from, '11.30');
  await requireNoPendingUpdate(f.next);
});
for (const failure of ['provision', 'verify', 'empty-verification']) test(`failed ${failure} restores prior software and preserves failure evidence`, async t => {
  const f = await fixture(t);
  if (failure === 'provision') f.provision = async () => { throw new Error('SYNTHETIC_NATIVE_SECRET'); };
  if (failure === 'verify') f.verify = async () => [{ required: true, status: 'failed' }];
  if (failure === 'empty-verification') f.verify = async () => [];
  await assert.rejects(applyUpdate(f.next, f), error => /previous software restored/.test(error.message) && !error.message.includes('SYNTHETIC_NATIVE_SECRET'));
  for (const relative of updateRoots(f.ctx)) assert.equal(await fs.readFile(path.join(f.ctx.root, relative, 'software'), 'utf8'), 'OLD');
  assert.equal((await updatePlan(f.next)).from, '11.29');
  assert.equal(await fs.readFile(path.join(f.privateProfile, '.env'), 'utf8'), 'SYNTHETIC_PRIVATE_TEST');
});
test('unrelated concurrent credential changes are detected but never overwritten during recovery', async t => {
  const f = await fixture(t), original = f.verify;
  f.verify = async () => { await fs.writeFile(path.join(f.privateProfile, '.env'), 'USER_CHANGED', { mode: 0o600 }); return original(); };
  await assert.rejects(applyUpdate(f.next, f), /previous software restored/);
  assert.equal(await fs.readFile(path.join(f.privateProfile, '.env'), 'utf8'), 'USER_CHANGED');
});
test('pending update prevents subsequent operations and recovery handles interrupted rename before journal flush', async t => {
  const f = await fixture(t), id = 'update-00000000-0000-4000-a000-000000000001';
  const transaction = path.join(f.ctx.evidence, id); await fs.mkdir(transaction, { mode: 0o700 });
  await atomicJSON(path.join(transaction, 'baseline.json'), await softwareSnapshot(f.ctx));
  await atomicJSON(path.join(f.ctx.root, '.station-update.json'), { schema: 1, root: f.ctx.root, profile: f.ctx.profile, id, targets: updateRoots(f.ctx), moved: [] });
  await fs.rename(f.ctx.bin, path.join(transaction, 'old-0'));
  await assert.rejects(requireNoPendingUpdate(f.ctx), /Interrupted/);
  const recovered = await recoverUpdate(f.ctx);
  assert.equal(recovered.restored, '11.29');
  assert.equal(await fs.readFile(path.join(f.ctx.bin, 'software'), 'utf8'), 'OLD');
});
test('tampered journal paths cannot target projects or account directories', async t => {
  const f = await fixture(t);
  await atomicJSON(path.join(f.ctx.root, '.station-update.json'), { schema: 1, root: f.ctx.root, profile: f.ctx.profile, id: '../outside', targets: ['projects'], moved: [] });
  await assert.rejects(recoverUpdate(f.ctx), /Invalid update/);
  assert.equal(await fs.readFile(path.join(f.ctx.projects, 'keep'), 'utf8'), 'PROJECT');
});
for (const defect of ['schema', 'root', 'profile', 'uid', 'release', 'pins', 'pin-value', 'digest',
  'entry-path', 'entry-shape', 'duplicate-entry', 'missing-root', 'predecessor']) test(`corrupt recovery ${defect} is refused before any rename or baseline publication`, async t => {
  const f = await fixture(t), id = 'update-00000000-0000-4000-a000-000000000001';
  const transaction = path.join(f.ctx.evidence, id); await fs.mkdir(transaction, { mode: 0o700 });
  const baseline = await softwareSnapshot(f.ctx);
  if (defect === 'schema') baseline.schema = 2;
  if (defect === 'root') baseline.root = '/unrelated/station';
  if (defect === 'profile') baseline.profile = 'wrong-profile';
  if (defect === 'uid') baseline.uid++;
  if (defect === 'release') baseline.release = 'not-a-release';
  if (defect === 'pins') baseline.pins = [];
  if (defect === 'pin-value') baseline.pins = { HERMES_COMMIT: { substituted: true } };
  if (defect === 'digest') baseline.digest = '0'.repeat(64);
  if (defect === 'entry-path') baseline.entries[1][0] = 'bin/../projects/keep';
  if (defect === 'entry-shape') baseline.entries[1] = [baseline.entries[1][0], 'file', 0o600, 'not-a-hash'];
  if (defect === 'duplicate-entry') baseline.entries.push(baseline.entries[1]);
  if (defect === 'missing-root') baseline.entries = baseline.entries.filter(entry => entry[0] !== 'tools' && !entry[0].startsWith('tools/'));
  if (['entry-path', 'entry-shape', 'duplicate-entry', 'missing-root'].includes(defect)) {
    baseline.digest = createHash('sha256').update(JSON.stringify(baseline.entries)).digest('hex');
  }
  await atomicJSON(path.join(transaction, 'baseline.json'), baseline);
  const pending = path.join(f.ctx.root, '.station-update.json');
  await atomicJSON(pending, { schema: 1, root: f.ctx.root, profile: f.ctx.profile, id,
    targets: updateRoots(f.ctx), moved: ['bin'], from: defect === 'predecessor' ? '11.28' : '11.29', to: '11.30' });
  await fs.rename(f.ctx.bin, path.join(transaction, 'old-0'));
  await fs.mkdir(f.ctx.bin, { mode: 0o700 });
  await fs.writeFile(path.join(f.ctx.bin, 'software'), 'PARTIAL_NEW', { mode: 0o600 });
  const pendingBefore = await fs.readFile(pending);
  const softwareBefore = await fs.readFile(path.join(f.ctx.root, '.station-software.json'));
  await assert.rejects(recoverUpdate(f.next), /baseline/);
  assert.deepEqual(await fs.readFile(pending), pendingBefore);
  assert.deepEqual(await fs.readFile(path.join(f.ctx.root, '.station-software.json')), softwareBefore);
  assert.equal(await fs.readFile(path.join(f.ctx.bin, 'software'), 'utf8'), 'PARTIAL_NEW');
  assert.equal(await fs.readFile(path.join(transaction, 'old-0/software'), 'utf8'), 'OLD');
  await assert.rejects(fs.lstat(path.join(transaction, 'failed-0')), { code: 'ENOENT' });
  assert.equal(await fs.readFile(path.join(f.privateProfile, '.env'), 'utf8'), 'SYNTHETIC_PRIVATE_TEST');
  assert.equal(await fs.readFile(path.join(f.ctx.projects, 'keep'), 'utf8'), 'PROJECT');
});

test('failed restored-tree verification preserves the installed baseline and pending journal', async t => {
  const f = await fixture(t), id = 'update-00000000-0000-4000-a000-000000000001';
  const transaction = path.join(f.ctx.evidence, id); await fs.mkdir(transaction, { mode: 0o700 });
  await atomicJSON(path.join(transaction, 'baseline.json'), await softwareSnapshot(f.ctx));
  const pending = path.join(f.ctx.root, '.station-update.json');
  await atomicJSON(pending, { schema: 1, root: f.ctx.root, profile: f.ctx.profile, id, targets: updateRoots(f.ctx), moved: ['bin'] });
  await fs.rename(f.ctx.bin, path.join(transaction, 'old-0'));
  await fs.writeFile(path.join(transaction, 'old-0/software'), 'DAMAGED_BACKUP', { mode: 0o600 });
  const marker = path.join(f.ctx.root, '.station-software.json');
  await atomicJSON(marker, { synthetic: 'do-not-publish-restored-baseline-before-verification' });
  const before = await fs.readFile(marker), pendingBefore = await fs.readFile(pending);
  await assert.rejects(recoverUpdate(f.next), /Restored predecessor differs/);
  assert.deepEqual(await fs.readFile(marker), before);
  assert.deepEqual(await fs.readFile(pending), pendingBefore);
  assert.equal(await fs.readFile(path.join(f.ctx.bin, 'software'), 'utf8'), 'DAMAGED_BACKUP');
  await assert.rejects(fs.lstat(path.join(transaction, 'recovered.json')), { code: 'ENOENT' });
});
test('gateway errors, existing definitions and private RMUX endpoints block mutation', async t => {
  const f = await fixture(t);
  await assert.rejects(assertIdle(f.ctx, { run: async () => ({ code: 1, stdout: '', stderr: '' }) }), /absence/);
  const daemon = path.join(f.ctx.cache, 'rmux', `rmux-${process.getuid()}`);
  await fs.mkdir(daemon, { recursive: true, mode: 0o700 }); await fs.writeFile(path.join(daemon, 'default'), 'socket-fixture');
  await assert.rejects(assertIdle(f.ctx, f), /RMUX/);
  const service = path.join(f.ctx.accountHome, '.config/systemd/user', `hermes-gateway-${f.ctx.profile}.service`);
  await fs.mkdir(path.dirname(service), { recursive: true }); await fs.writeFile(service, 'existing');
  await assert.rejects(assertIdle(f.ctx, f), /definition/);
});
test('macOS checks both launchd namespaces and rejects an occupied user namespace', async t => {
  const f = await fixture(t), calls = [];
  const run = async (binary, argv) => { if (binary === '/bin/ps') return f.run(binary); calls.push(argv); return argv[1].startsWith('gui/')
    ? { code: 113, stdout: '', stderr: 'Could not find service' } : { code: 0, stdout: 'state = running', stderr: '' }; };
  await assert.rejects(assertIdle({ ...f.ctx, platform: 'darwin' }, { run }), /absence/);
  assert.equal(calls.length, 2);
});

test('a residual same-root process blocks update even without a gateway or session endpoint', async t => {
  const f = await fixture(t), run = async binary => binary === '/bin/ps'
    ? { code: 0, stdout: `${process.pid} ${process.ppid} updater\n987654 1 orphaned-build ${f.ctx.root}/tools\n`, stderr: '' }
    : f.run(binary);
  await assert.rejects(assertIdle(f.ctx, { run }), /Another process references/);
});

test('recovery preserves a proved-dead lock but never interrupts a live owner', async t => {
  const f = await fixture(t), lock = path.join(f.ctx.root, '.install.lock');
  await atomicJSON(path.join(f.ctx.root, '.station-update.json'), { schema: 1, root: f.ctx.root, profile: f.ctx.profile,
    id: 'update-00000000-0000-4000-a000-000000000001', targets: updateRoots(f.ctx), moved: [] });
  await fs.mkdir(lock, { mode: 0o700 });
  await atomicJSON(path.join(lock, 'owner.json'), { pid: process.pid });
  await assert.rejects(acquireRecoveryLock(f.ctx), /still be alive/);
  await assert.rejects(fs.lstat(path.join(f.ctx.root, '.update-recovery.lock')), { code: 'ENOENT' });
  assert.equal(JSON.parse(await fs.readFile(path.join(lock, 'owner.json'))).pid, process.pid);
  const child = spawn(process.execPath, ['-e', ''], { stdio: 'ignore' });
  await new Promise((resolve, reject) => { child.once('exit', resolve); child.once('error', reject); });
  await atomicJSON(path.join(lock, 'owner.json'), { pid: child.pid });
  const unlock = await acquireRecoveryLock(f.ctx);
  assert.equal((await fs.readdir(f.ctx.evidence)).filter(x => x.startsWith('stale-update-lock-')).length, 1);
  assert.equal(JSON.parse(await fs.readFile(path.join(lock, 'owner.json'))).pid, process.pid);
  await assert.rejects(fs.lstat(path.join(f.ctx.root, '.update-recovery.lock')), { code: 'ENOENT' });
  await unlock();
});

test('existing recovery guard is preserved without inspecting or moving the normal lock', async t => {
  const f = await fixture(t), guard = path.join(f.ctx.root, '.update-recovery.lock');
  await fs.mkdir(guard, { mode: 0o700 });
  await atomicJSON(path.join(guard, 'owner.json'), { pid: process.pid, token: 'preserve-this-owner' });
  const before = await fs.readFile(path.join(guard, 'owner.json'));
  await assert.rejects(acquireRecoveryLock(f.ctx), /interrupted recovery owns/);
  assert.deepEqual(await fs.readFile(path.join(guard, 'owner.json')), before);
  assert.deepEqual(await fs.readdir(f.ctx.evidence), []);
  await assert.rejects(fs.lstat(path.join(f.ctx.root, '.install.lock')), { code: 'ENOENT' });
});

test('concurrent recoveries cannot displace one another after inspecting a dead owner', async t => {
  const f = await fixture(t), lock = path.join(f.ctx.root, '.install.lock');
  await atomicJSON(path.join(f.ctx.root, '.station-update.json'), { schema: 1, root: f.ctx.root, profile: f.ctx.profile,
    id: 'update-00000000-0000-4000-a000-000000000001', targets: updateRoots(f.ctx), moved: [] });
  const child = spawn(process.execPath, ['-e', ''], { stdio: 'ignore' });
  await new Promise((resolve, reject) => { child.once('exit', resolve); child.once('error', reject); });
  await fs.mkdir(lock, { mode: 0o700 });
  await atomicJSON(path.join(lock, 'owner.json'), { pid: child.pid });
  let entered, resume;
  const atRename = new Promise(resolve => { entered = resolve; });
  const continueRename = new Promise(resolve => { resume = resolve; });
  const rename = fs.rename.bind(fs);
  let intercepted = false;
  t.mock.method(fs, 'rename', async (from, to) => {
    if (from === lock && !intercepted) { intercepted = true; entered(); await continueRename; }
    return rename(from, to);
  });
  const first = acquireRecoveryLock(f.ctx);
  let unlock;
  try {
    await atRename;
    await assert.rejects(acquireRecoveryLock(f.ctx), /recovery owns/);
    assert.equal(JSON.parse(await fs.readFile(path.join(lock, 'owner.json'))).pid, child.pid);
  } finally {
    resume();
    unlock = await first;
  }
  try {
    assert.equal(JSON.parse(await fs.readFile(path.join(lock, 'owner.json'))).pid, process.pid);
    assert.equal((await fs.readdir(f.ctx.evidence)).filter(x => x.startsWith('stale-update-lock-')).length, 1);
    await assert.rejects(acquireRecoveryLock(f.ctx), /still be alive/);
    assert.equal(JSON.parse(await fs.readFile(path.join(lock, 'owner.json'))).pid, process.pid);
    await assert.rejects(fs.lstat(path.join(f.ctx.root, '.update-recovery.lock')), { code: 'ENOENT' });
  } finally { await unlock(); }
});

test('failed journal validation releases only the newly acquired recovery guard', async t => {
  const f = await fixture(t);
  await atomicJSON(path.join(f.ctx.root, '.station-update.json'), { schema: 1, targets: ['projects'] });
  await assert.rejects(acquireRecoveryLock(f.ctx), /Invalid update/);
  await assert.rejects(fs.lstat(path.join(f.ctx.root, '.update-recovery.lock')), { code: 'ENOENT' });
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(f.ctx.root, '.station-update.json'))), { schema: 1, targets: ['projects'] });
});
