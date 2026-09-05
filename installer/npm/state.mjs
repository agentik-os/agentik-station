import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash, randomUUID } from 'node:crypto';

const markerName = '.station-workstation.json';
const managedDirs = ['bin', 'tools', 'cache', 'evidence', 'resources', 'projects', 'personal', 'personal/home'];
export async function assertSafePath(target, { allowMissing = true } = {}) {
  if (!path.isAbsolute(target) || /[\x00-\x1f\x7f]/.test(target)) throw new Error('Expected an absolute path without control characters.');
  let current = path.parse(target).root;
  for (const part of target.slice(current.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    let stat;
    try { stat = await fs.lstat(current); }
    catch (error) { if (error.code === 'ENOENT' && allowMissing) return; throw error; }
    if (stat.isSymbolicLink() || (!stat.isDirectory() && !stat.isFile())) throw new Error(`Unsafe path type: ${current}`);
    const safeTemporaryParent=stat.uid===0 && ['/tmp','/private/tmp'].includes(current) && (stat.mode & 0o1000);
    if (stat.isDirectory() && (stat.uid !== 0 && stat.uid !== process.getuid() || (stat.mode & 0o022) && !safeTemporaryParent)) throw new Error(`Directory is writable by another identity or has an unexpected owner: ${current}`);
    if (current !== target && !stat.isDirectory()) throw new Error(`Parent is not a directory: ${current}`);
    if (stat.isFile() && stat.nlink !== 1) throw new Error(`Hard-linked file refused: ${current}`);
  }
}
export async function atomicJSON(target, value, { exclusive = false } = {}) {
  const content = `${JSON.stringify(value, null, 2)}\n`;
  await assertSafePath(target);
  const temporary = `${target}.${randomUUID()}.tmp`;
  try {
    const handle = await fs.open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    try { await handle.writeFile(content); await handle.sync(); }
    finally { await handle.close(); }
    if (exclusive) { await fs.link(temporary, target); await fs.unlink(temporary); }
    else { await assertSafePath(target); await fs.rename(temporary, target); }
  } catch (error) { await fs.unlink(temporary).catch(() => {}); throw error; }
}
export async function readJSON(target) {
  await assertSafePath(target, { allowMissing: false });
  const handle = await fs.open(target, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size > 1024 * 1024) throw new Error('Invalid Station state file.');
    return JSON.parse(await handle.readFile('utf8'));
  } finally { await handle.close(); }
}
export async function createContext({ root, sourceRoot, platform = process.platform, arch = process.arch, accountHome = os.userInfo().homedir }) {
  if (!['darwin', 'linux'].includes(platform) || !['arm64', 'x64'].includes(arch)) throw new Error('Workstation supports macOS/Linux arm64 or x64. Use a Linux WSL environment on Windows.');
  if (os.userInfo().username === 'agk-station') throw new Error('The canonical agk-station account must use Host commands; Workstation requires a personal account.');
  const selected = path.resolve(root || path.join(accountHome, 'station'));
  if ([path.parse(selected).root, accountHome, sourceRoot].some(p => selected === path.resolve(p) || path.resolve(p).startsWith(`${selected}${path.sep}`))) throw new Error('Choose a dedicated Station directory, not an account, repository or filesystem root.');
  await assertSafePath(selected);
  const pins = Object.fromEntries((await fs.readFile(path.join(sourceRoot, 'config/versions.lock'), 'utf8')).split(/\r?\n/).filter(l => l && !l.startsWith('#')).map(l => [l.slice(0,l.indexOf('=')),l.slice(l.indexOf('=')+1)]));
  const home = path.join(selected, 'personal/home');
  const release=(await fs.readFile(path.join(sourceRoot,'VERSION'),'utf8')).trim();
  if(!/^\d+\.\d+$/.test(release)) throw new Error('Invalid Station release version.');
  return Object.freeze({ root: selected, sourceRoot, release, platform, arch, accountHome, home,
    ...Object.fromEntries(['tools', 'bin', 'cache', 'evidence', 'resources', 'projects'].map(d => [d, path.join(selected,d)])),
    hermesHome: path.join(home, '.hermes'), profile: `station-${createHash('sha256').update(selected).digest('hex').slice(0,12)}`, pins });
}
export async function inspectInstallation(ctx) {
  await assertSafePath(ctx.root);
  let stat;
  try { stat = await fs.lstat(ctx.root); } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  if (!stat.isDirectory() || stat.uid !== process.getuid() || (stat.mode & 0o077)) throw new Error('Station root must be your private directory (mode 0700). Unmanaged roots are never adopted.');
  let marker;
  try { marker = await readJSON(path.join(ctx.root, markerName)); }
  catch { throw new Error('Existing directory is not a recognized Station Workstation; choose a new root.'); }
  if (marker.schema !== 1 || marker.mode !== 'workstation' || marker.root !== ctx.root || marker.profile !== ctx.profile || marker.uid !== process.getuid()) throw new Error('Workstation ownership/context mismatch.');
  for (const dir of managedDirs) {
    const target=path.join(ctx.root, dir);
    await assertSafePath(target, { allowMissing: false });
    const stat=await fs.lstat(target);
    if (!stat.isDirectory() || stat.uid !== process.getuid() || (stat.mode & 0o077)) throw new Error(`Managed path is not your private directory: ${target}`);
  }
  return marker;
}
export async function initialize(ctx) {
  if (process.getuid() === 0) throw new Error('Workstation must run as your ordinary user, without sudo.');
  if (await inspectInstallation(ctx)) throw new Error('Already installed: use verify or explicitly repair this root.');
  // Only create the selected leaf: a typo must not build arbitrary ancestor trees.
  await fs.mkdir(ctx.root, { mode: 0o700 });
  for (const dir of managedDirs) await fs.mkdir(path.join(ctx.root, dir), { mode: 0o700 });
  await atomicJSON(path.join(ctx.root, markerName), { schema: 1, mode: 'workstation', root: ctx.root, uid: process.getuid(), profile: ctx.profile, created: new Date().toISOString() }, { exclusive: true });
}
export async function acquireLock(ctx) {
  const lock = path.join(ctx.root, '.install.lock');
  await assertSafePath(lock);
  try { await fs.mkdir(lock, { mode: 0o700 }); }
  catch (error) { if (error.code === 'EEXIST') throw new Error('Another operation or interrupted attempt owns .install.lock. Inspect it before removing the lock; never run concurrent installers.'); throw error; }
  await atomicJSON(path.join(lock, 'owner.json'), { pid: process.pid, started: new Date().toISOString() }, { exclusive: true });
  return async () => { await fs.unlink(path.join(lock, 'owner.json')); await fs.rmdir(lock); };
}
export async function receipt(ctx, action, report) {
  const target = path.join(ctx.evidence, `${new Date().toISOString().replaceAll(':','-')}-${action}-${randomUUID()}.json`);
  await atomicJSON(target, { schema: 1, mode: 'workstation', release:ctx.release, action, root: ctx.root, profile: ctx.profile, ...report }, { exclusive: true });
  return target;
}
