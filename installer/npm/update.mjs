/** Explicit same-owner software migration. Never upgrades arbitrary upstream latest. */
import fs from 'node:fs/promises';
import { constants, createReadStream } from 'node:fs';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { assertSafePath, atomicJSON, inspectInstallation, acquireLock } from './state.mjs';

const SNAPSHOT = '.station-software.json';
const PENDING = '.station-update.json';
const EXCLUDED = new Set(['.git', '__pycache__', '.pytest_cache', '.DS_Store']);
const MAX_ENTRIES = 200000;
const NEW_OS_ROOTS = ['stepper-os', 'builder-os', 'librarian-os'].map(id => `personal/home/os/${id}`);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const exists = async target => { try { return await fs.lstat(target); } catch (e) { if (e.code === 'ENOENT') return null; throw e; } };

export function updateRoots(ctx) {
  const profile = `personal/home/.hermes/profiles/${ctx.profile}`;
  return ['bin', 'tools', 'resources', `${profile}/plugins/agentik_os`,
    `${profile}/plugins/platforms/discord`, `${profile}/dashboard-themes`, `${profile}/agents`];
}

async function readRecord(ctx, name, maximumBytes = 64 * 1024 * 1024) {
  const target = path.join(ctx.root, name);
  await assertSafePath(target, { allowMissing: false });
  const handle = await fs.open(target, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const info = await handle.stat();
    if (!info.isFile() || info.uid !== process.getuid() || info.nlink !== 1 || info.mode & 0o077 || info.size > maximumBytes) throw new Error('Unsafe update evidence.');
    return JSON.parse(await handle.readFile('utf8'));
  } finally { await handle.close(); }
}

async function tree(ctx, relative, entries, { optional = false, protectedState = false } = {}) {
  const target = path.join(ctx.root, relative), info = await exists(target);
  if (!info) { if (optional) return; throw new Error('Required owned software is missing; inspect before update.'); }
  if (entries.length >= MAX_ENTRIES || info.uid !== process.getuid()) throw new Error('Software inventory exceeds bounds or has another owner.');
  if (info.isSymbolicLink()) {
    if (protectedState) throw new Error('Linked protected state is not eligible for automatic migration.');
    // Capture link bytes, never traverse package/venv links while inventorying.
    entries.push([relative, 'link', await fs.readlink(target)]);
  } else if (info.isDirectory()) {
    entries.push([relative, 'dir', info.mode & 0o777]);
    for (const name of (await fs.readdir(target)).sort()) {
      if (!EXCLUDED.has(name) && !name.endsWith('.pyc')) await tree(ctx, `${relative}/${name}`, entries, { protectedState });
    }
  } else if (info.isFile()) {
    if (protectedState && info.nlink !== 1) throw new Error('Hard-linked protected state is not eligible for migration.');
    const hash = createHash('sha256');
    const handle = await fs.open(target, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    try {
      const opened = await handle.stat();
      if (!opened.isFile() || opened.ino !== info.ino || opened.dev !== info.dev) throw new Error('Software path was substituted.');
      for await (const bytes of createReadStream(target, { fd: handle.fd, autoClose: false })) hash.update(bytes);
    } finally { await handle.close(); }
    const after = await fs.lstat(target);
    if (info.ino !== after.ino || info.dev !== after.dev || info.size !== after.size || info.mtimeMs !== after.mtimeMs) throw new Error('Software changed during inventory.');
    entries.push([relative, 'file', info.mode & 0o777, hash.digest('hex')]);
  } else throw new Error('Special file in owned software; update refused.');
}

export async function softwareSnapshot(ctx) {
  const entries = [];
  for (const relative of updateRoots(ctx)) {
    await assertSafePath(path.join(ctx.root, relative), { allowMissing: false });
    if (!(await fs.lstat(path.join(ctx.root, relative))).isDirectory()) throw new Error('Software roots must be real directories.');
    await tree(ctx, relative, entries);
  }
  return { schema: 1, root: ctx.root, uid: process.getuid(), profile: ctx.profile,
    release: ctx.release, pins: ctx.pins, entries, digest: digest(JSON.stringify(entries)) };
}

export async function recordSoftware(ctx, { initial = false } = {}) {
  const target = path.join(ctx.root, SNAPSHOT);
  if (await exists(target)) {
    if (initial) throw new Error('An existing software baseline must not be adopted by install.');
    return; // Repair never replaces a predecessor baseline to hide drift.
  }
  await atomicJSON(target, await softwareSnapshot(ctx), { exclusive: true });
}

export async function requireNoPendingUpdate(ctx) {
  if (await exists(path.join(ctx.root, PENDING))) throw new Error('Interrupted software update: use update-recover --yes before any repair, enrollment or activation.');
}

function validateBaseline(ctx, baseline) {
  const invalid = () => { throw new Error('Invalid predecessor software baseline.'); };
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  if (!object(baseline) || baseline.schema !== 1 || baseline.root !== ctx.root
      || baseline.profile !== ctx.profile || baseline.uid !== process.getuid()
      || typeof baseline.release !== 'string' || !/^\d+\.\d+$/.test(baseline.release)
      || !baseline.release.split('.').every(part => Number.isSafeInteger(Number(part)))
      || !object(baseline.pins) || Object.entries(baseline.pins).some(([key, value]) =>
        !/^[A-Z][A-Z0-9_]*$/.test(key) || typeof value !== 'string' || !/^\S+$/.test(value))
      || !Array.isArray(baseline.entries) || baseline.entries.length > MAX_ENTRIES
      || baseline.digest !== digest(JSON.stringify(baseline.entries))) invalid();
  const roots = updateRoots(ctx), seen = new Map();
  for (const entry of baseline.entries) {
    if (!Array.isArray(entry) || typeof entry[0] !== 'string') invalid();
    const [relative, kind, value, hash] = entry;
    const root = roots.find(candidate => relative === candidate || relative.startsWith(`${candidate}/`));
    if (!root || relative !== path.posix.normalize(relative) || /[\x00-\x1f\x7f]/.test(relative)
        || seen.has(relative) || (relative !== root && seen.get(path.posix.dirname(relative)) !== 'dir')) invalid();
    if (kind === 'dir' || kind === 'file') {
      if (!Number.isInteger(value) || value < 0 || value > 0o777
          || (kind === 'dir' ? entry.length !== 3 : entry.length !== 4 || !/^[a-f0-9]{64}$/.test(hash))) invalid();
    } else if (kind !== 'link' || entry.length !== 3 || typeof value !== 'string' || !value || /[\x00-\x1f\x7f]/.test(value)) invalid();
    seen.set(relative, kind);
  }
  if (roots.some(root => seen.get(root) !== 'dir')) invalid();
}

export async function updatePlan(ctx) {
  await inspectInstallation(ctx);
  await requireNoPendingUpdate(ctx);
  let prior;
  try { prior = await readRecord(ctx, SNAPSHOT); }
  catch { throw new Error('No valid predecessor software baseline. Legacy installations need a reviewed migration; no software or accounts were adopted.'); }
  validateBaseline(ctx, prior);
  const now = await softwareSnapshot(ctx);
  if (!equal(now.entries, prior.entries)) throw new Error('Installed software has changed since verification. Customizations are preserved; review them before upgrading.');
  const version = value => value.split('.').map(Number);
  const [oldMajor, oldMinor] = version(prior.release), [newMajor, newMinor] = version(ctx.release);
  if (newMajor < oldMajor || newMajor === oldMajor && newMinor < oldMinor) throw new Error('Downgrades require explicit recovery, not update.');
  const changedPins = [...new Set([...Object.keys(prior.pins), ...Object.keys(ctx.pins)])].sort()
    .filter(key => prior.pins[key] !== ctx.pins[key]);
  if (prior.release === ctx.release && changedPins.length) throw new Error('Same release with different dependency pins is not an immutable update.');
  return { status: 'review-required', from: prior.release, to: ctx.release, root: ctx.root,
    changedPins, targets: updateRoots(ctx), projectsAndAccounts: 'preserved',
    upstreamPolicy: 'the target npm package supplies reviewed coupled pins, never independent latest',
    legacyBaseline: 'required', operational: false, rollback: 'update-recover --yes while an update is pending' };
}

async function recordedOSProfiles(ctx) {
  // Read only exact private installation receipts. Directory names, native
  // configs and credentials are never adopted as service-selection authority.
  const profiles = [], object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const identifier = /^[a-z][a-z0-9-]{0,62}$/;
  const invalid = () => { throw new Error('Invalid or unrecorded personal OS installation; inspect before migration.'); };
  for (const relative of NEW_OS_ROOTS) {
    const root = path.join(ctx.root, relative);
    await assertSafePath(root);
    const info = await exists(root);
    if (!info) continue;
    if (!info.isDirectory() || info.uid !== process.getuid() || info.mode & 0o077) invalid();
    const record = await readRecord(ctx, `${relative}/OS_INSTALL.json`, 65536);
    const c = record?.compiled, id = path.basename(relative);
    if (!object(record) || record.schema_version !== 1 || record.root !== ctx.root
        || record.workstation_profile !== ctx.profile || record.uid !== process.getuid()
        || !object(record.profiles) || !object(c) || c.schema_version !== 4 || c.os_id !== id
        || c.boundary !== 'personal-same-uid' || c.claim !== 'COMPILED_NOT_INSTALLED'
        || c.workspace_root !== path.join(ctx.root, 'personal/os', id, 'workspace')
        || c.hermes_home !== path.join(root, 'hermes')
        || typeof c.os_version !== 'string' || !/^[0-9][a-zA-Z0-9.+-]{0,63}$/.test(c.os_version)
        || typeof c.inputs_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(c.inputs_sha256)
        || typeof c.artifacts_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(c.artifacts_sha256)
        || !object(c.role_profile_map) || !Array.isArray(c.profiles)
        || !c.profiles.length || c.profiles.length > 64) invalid();
    const expected = Object.keys(c.role_profile_map).map(role => {
      if (!identifier.test(role)) invalid();
      const suffix = digest([ctx.root, ctx.profile, id, role].join('\0')).slice(0, 16);
      const name = `w-${suffix}-${role.slice(0, 25).replace(/-+$/, '')}`;
      if (c.role_profile_map[role] !== name) invalid();
      return name;
    }).sort();
    if (!equal([...c.profiles].sort(), expected) || new Set(expected).size !== expected.length
        || !expected.includes(c.nano_director) || !equal(Object.keys(record.profiles).sort(), expected)
        || Object.values(record.profiles).some(status => !['planned', 'pending', 'installed'].includes(status))) invalid();
    profiles.push(...expected);
  }
  return profiles;
}

export async function assertIdle(ctx, { run }) {
  const osProfiles = await recordedOSProfiles(ctx), profiles = [ctx.profile, ...osProfiles];
  const services = profiles.map(profile => ({ label: `ai.hermes.gateway-${profile}`, unit: `hermes-gateway-${profile}.service` }));
  const definitions = services.flatMap(({ label, unit }) => [
    path.join(ctx.accountHome, 'Library/LaunchAgents', `${label}.plist`), path.join(ctx.home, 'Library/LaunchAgents', `${label}.plist`),
    path.join(ctx.accountHome, '.config/systemd/user', unit), path.join(ctx.home, '.config/systemd/user', unit)]);
  for (const target of definitions) if (await exists(target)) throw new Error('An owned gateway definition exists. Stop and explicitly remove that service binding before migration; no service was changed.');
  const env = { PATH: '/usr/bin:/bin', HOME: ctx.home, XDG_RUNTIME_DIR: `/run/user/${process.getuid()}`,
    DBUS_SESSION_BUS_ADDRESS: `unix:path=/run/user/${process.getuid()}/bus` };
  // SIGKILL can leave an installer child alive after its lock owner dies. Read
  // same-UID process metadata only; never export command lines or signal them.
  const processes = await run('/bin/ps', ['-ww', '-U', String(process.getuid()), '-o', 'pid=,ppid=,args='],
    { env, cwd: ctx.root, allowFailure: true, timeoutMs: 10000 });
  if (processes.code !== 0) throw new Error('Could not prove absence of residual Station processes.');
  const rows = processes.stdout.split('\n').filter(line => line.trim()).map(line => {
    const match = /^\s*(\d+)\s+(\d+)\s+(.*)$/.exec(line);
    if (!match) throw new Error('Ambiguous process inventory; update refused.');
    return { pid: Number(match[1]), parent: Number(match[2]), args: match[3] };
  });
  const ancestors = new Set(); let cursor = process.pid;
  if (!rows.some(row => row.pid === cursor)) throw new Error('Incomplete process inventory; update refused.');
  while (cursor && !ancestors.has(cursor)) { ancestors.add(cursor); cursor = rows.find(row => row.pid === cursor)?.parent; }
  const selectors = osProfiles.map(profile => new RegExp(`(?:^|\\s)(?:--profile(?:=|\\s+)|-p\\s+)["']?${profile}(?:["']?(?:\\s|$))`));
  if (rows.some(row => !ancestors.has(row.pid) && (row.args.includes(ctx.root) || selectors.some(selector => selector.test(row.args))))) throw new Error('Another process references this Station root or a recorded OS profile. Wait for its completion before migration or recovery; no process was stopped.');
  for (const { label, unit } of services) for (const domain of ctx.platform === 'darwin' ? ['gui', 'user'] : ['user']) {
    const state = ctx.platform === 'darwin'
      ? await run('/bin/launchctl', ['print', `${domain}/${process.getuid()}/${label}`], { env, cwd: ctx.root, allowFailure: true, timeoutMs: 10000 })
      : await run('/usr/bin/systemctl', ['--user', 'show', unit, '--property=LoadState', '--value'], { env, cwd: ctx.root, allowFailure: true, timeoutMs: 10000 });
    if (ctx.platform === 'darwin' ? !(state.code === 113 && /Could not find service/.test(state.stderr))
        : !(state.code === 0 && state.stdout.trim() === 'not-found')) throw new Error('Gateway absence could not be proved; migration refused.');
  }
  const rmux = path.join(ctx.cache, 'rmux', `rmux-${process.getuid()}`);
  if (await exists(rmux) && (await fs.readdir(rmux)).some(name => !name.endsWith('.log'))) throw new Error('A private RMUX endpoint exists. Close sessions and stop only that owned daemon before updating.');
}

async function protectedFiles(ctx) {
  const profile = `personal/home/.hermes/profiles/${ctx.profile}`;
  const entries = [];
  for (const relative of ['personal/home/.hermes/.env', 'personal/home/.hermes/config.yaml',
    `${profile}/.env`, `${profile}/config.yaml`, 'personal/home/.composio', 'personal/home/.config', 'personal/home/os']) {
    await assertSafePath(path.dirname(path.join(ctx.root, relative)));
    await tree(ctx, relative, entries, { optional: true, protectedState: true });
  }
  return entries;
}

/** Existing state must match exactly. Only explicitly absent bundled OS roots
 * may be created by the new installer, and only after their native checks pass.
 */
export function protectedStatePreserved(before, after, newOSRoots, checks) {
  if (!Array.isArray(newOSRoots) || newOSRoots.some(root => !NEW_OS_ROOTS.includes(root))) return false;
  const old = new Map(before.map(entry => [entry[0], entry]));
  if (before.some(entry => newOSRoots.some(root => entry[0] === root || entry[0].startsWith(`${root}/`)))) return false;
  const remaining = [];
  for (const entry of after) {
    if (old.has(entry[0])) { remaining.push(entry); continue; }
    if (entry[0] === 'personal/home/os' && entry[1] === 'dir' && entry[2] === 0o700 && newOSRoots.length) continue;
    const root = newOSRoots.find(candidate => entry[0] === candidate || entry[0].startsWith(`${candidate}/`));
    if (!root) return false;
    const id = root.split('/').at(-1);
    if (!['distribution', 'native-profiles'].every(kind => checks.some(check => check.id === `os:${id}:${kind}`
        && check.required === true && check.status === 'verified'))) return false;
  }
  return equal(before, remaining);
}

function validateJournal(ctx, journal) {
  if (journal.schema !== 1 || journal.root !== ctx.root || journal.profile !== ctx.profile
      || !/^update-[a-f0-9-]{36}$/.test(journal.id) || !equal(journal.targets, updateRoots(ctx))
      || !Array.isArray(journal.moved) || journal.moved.some(x => !journal.targets.includes(x))
      || new Set(journal.moved).size !== journal.moved.length) throw new Error('Invalid update recovery journal.');
}

export async function acquireRecoveryLock(ctx) {
  // Serialize dead-lock inspection and displacement, not just installation.
  // Otherwise a second recovery can rename the first recovery's NEW live lock.
  // A killed recovery leaves this guard intact for explicit inspection; never
  // recursively recover a recovery guard or remove an existing one blindly.
  const guardName = '.update-recovery.lock', guard = path.join(ctx.root, guardName);
  await assertSafePath(guard);
  try { await fs.mkdir(guard, { mode: 0o700 }); }
  catch (error) {
    if (error.code === 'EEXIST') throw new Error('Another or interrupted recovery owns .update-recovery.lock. Preserve it and inspect its owner before retrying.');
    throw error;
  }
  const guardInfo = await fs.lstat(guard);
  const guardOwner = { pid: process.pid, token: randomUUID() };
  await atomicJSON(path.join(guard, 'owner.json'), guardOwner, { exclusive: true });
  try {
    validateJournal(ctx, await readRecord(ctx, PENDING));
    const lock = path.join(ctx.root, '.install.lock');
    if (await exists(lock)) {
      await assertSafePath(lock, { allowMissing: false });
      const info = await fs.lstat(lock);
      if (!info.isDirectory() || info.uid !== process.getuid() || info.mode & 0o077) throw new Error('Unsafe recovery lock.');
      const owner = await readRecord(ctx, '.install.lock/owner.json');
      if (!Number.isSafeInteger(owner.pid) || owner.pid <= 0) throw new Error('Invalid recovery lock owner.');
      try { process.kill(owner.pid, 0); throw new Error('The lock owner is still alive; recovery must not interrupt it.'); }
      catch (error) { if (error.code !== 'ESRCH') throw new Error('The lock owner may still be alive; recovery refused.'); }
      if (!equal(owner, await readRecord(ctx, '.install.lock/owner.json'))) throw new Error('Recovery lock owner changed.');
      const saved = path.join(ctx.evidence, `stale-update-lock-${randomUUID()}`);
      await assertSafePath(saved);
      if (await exists(saved)) throw new Error('Recovery lock evidence collision.');
      // Preserve the exact dead-owner record instead of deleting it. A normal
      // installation that acquires the now-vacant canonical name wins normally.
      await fs.rename(lock, saved);
    }
    // Keep the recovery guard until the normal lock has actually been acquired.
    const unlock = await acquireLock(ctx);
    return unlock;
  } finally {
    const current = await fs.lstat(guard);
    if (current.dev !== guardInfo.dev || current.ino !== guardInfo.ino
        || !equal(guardOwner, await readRecord(ctx, `${guardName}/owner.json`))) throw new Error('Recovery guard changed; preserve it for inspection.');
    await fs.unlink(path.join(guard, 'owner.json'));
    await fs.rmdir(guard);
  }
}

/** Caller holds the normal installation lock. Native environments stay at their final paths. */
export async function recoverUpdate(ctx) {
  const journal = await readRecord(ctx, PENDING); validateJournal(ctx, journal);
  const transaction = path.join(ctx.root, 'evidence', journal.id);
  await assertSafePath(transaction, { allowMissing: false });
  // Reject corrupt or misbound recovery evidence before changing any tree.
  const saved = await readRecord(ctx, `evidence/${journal.id}/baseline.json`);
  validateBaseline(ctx, saved);
  if (journal.from !== undefined && saved.release !== journal.from) throw new Error('Recovery baseline does not match the recorded predecessor.');
  // Infer completed renames from exact backup paths, including a crash before journal flush.
  for (let index = journal.targets.length - 1; index >= 0; index--) {
    const relative = journal.targets[index], target = path.join(ctx.root, relative);
    const backup = path.join(transaction, `old-${index}`), failed = path.join(transaction, `failed-${index}`);
    if (!await exists(backup)) continue;
    await assertSafePath(backup, { allowMissing: false });
    if (await exists(target)) {
      await assertSafePath(target, { allowMissing: false });
      if (await exists(failed)) throw new Error('Recovery collision: preserve both versions for explicit review.');
      await fs.rename(target, failed);
    }
    await fs.rename(backup, target);
  }
  const restored = await softwareSnapshot(ctx);
  if (!equal(restored.entries, saved.entries)) throw new Error('Restored predecessor differs; recovery evidence retained.');
  await atomicJSON(path.join(ctx.root, SNAPSHOT), saved);
  await atomicJSON(path.join(transaction, 'recovered.json'), { status: 'restored', operational: false });
  await fs.unlink(path.join(ctx.root, PENDING));
  return { status: 'ready-for-setup', restored: saved.release, evidence: transaction, operational: false };
}

export async function applyUpdate(ctx, { run, provision, verify, emit = () => {} }) {
  const plan = await updatePlan(ctx);
  if (plan.from === plan.to) return { status: 'ready-for-setup', from: plan.from, to: plan.to,
    softwareChanged: false, reason: 'already at the target immutable release', operational: false };
  await assertIdle(ctx, { run });
  const before = await protectedFiles(ctx);
  const newOSRoots = [];
  for (const relative of NEW_OS_ROOTS) {
    await assertSafePath(path.join(ctx.root, relative));
    if (!await exists(path.join(ctx.root, relative))) newOSRoots.push(relative);
  }
  const id = `update-${randomUUID()}`, transaction = path.join(ctx.evidence, id);
  await assertSafePath(transaction); await fs.mkdir(transaction, { mode: 0o700 });
  await atomicJSON(path.join(transaction, 'baseline.json'), await readRecord(ctx, SNAPSHOT), { exclusive: true });
  const journal = { schema: 1, root: ctx.root, profile: ctx.profile, id, targets: updateRoots(ctx), moved: [], from: plan.from, to: plan.to };
  await atomicJSON(path.join(ctx.root, PENDING), journal, { exclusive: true });
  try {
    for (const [index, relative] of journal.targets.entries()) {
      const target = path.join(ctx.root, relative), backup = path.join(transaction, `old-${index}`);
      await assertSafePath(target, { allowMissing: false });
      if (await exists(backup)) throw new Error('Update backup collision.');
      await fs.rename(target, backup); journal.moved.push(relative);
      await atomicJSON(path.join(ctx.root, PENDING), journal);
      await fs.mkdir(target, { mode: 0o700 });
    }
    await provision({ ...ctx, preserveEnrollment: true }, { run, emit });
    const checked = await verify(ctx, { run, emit });
    const checks = Array.isArray(checked) ? checked : checked.checks;
    if (!Array.isArray(checks) || !checks.some(c => c.required === true)
        || checks.some(c => c.required === true && c.status !== 'verified')) throw new Error('Target software verification failed.');
    if (!protectedStatePreserved(before, await protectedFiles(ctx), newOSRoots, checks)) throw new Error('Protected configuration changed during native verification; inspect preserved evidence.');
    const snapshot = await softwareSnapshot(ctx);
    await atomicJSON(path.join(ctx.root, SNAPSHOT), snapshot);
    const report = { status: 'ready-for-setup', from: plan.from, to: plan.to, checks,
      evidence: transaction, servicesRestarted: false, accountsMigrated: false,
      newlyPreparedOS: newOSRoots.map(root => root.split('/').at(-1)), operational: false };
    await atomicJSON(path.join(transaction, 'completed.json'), report);
    await fs.unlink(path.join(ctx.root, PENDING));
    return report;
  } catch {
    try { await recoverUpdate(ctx); }
    catch { throw new Error('Update and automatic software recovery are incomplete. Preserve .station-update.json and use update-recover --yes after inspection.'); }
    throw new Error('Update failed; previous software restored. No account or project file was restored/overwritten. Inspect the private transaction evidence.');
  }
}
