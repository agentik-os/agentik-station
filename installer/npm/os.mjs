/** Native personal OS teams. Software delivery is never account enrollment. */
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { atomicJSON, assertSafePath, readJSON } from './state.mjs';
import { launcher, privateEnv, runtimePaths } from './runtime.mjs';

export const PERSONAL_OS_IDS = Object.freeze(['stepper-os', 'builder-os', 'librarian-os']);
export const OS_INSTALL_EXEC = 'import os, sys; os.umask(0o077); os.execv(sys.argv[1], sys.argv[1:])';
const identifier = /^[a-z][a-z0-9-]{0,62}$/;
const digest = /^[a-f0-9]{64}$/;
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
const missing = async target => { try { await fs.lstat(target); return false; } catch (error) { if (error.code === 'ENOENT') return true; throw error; } };

export function personalOSPaths(ctx, id) {
  if (!PERSONAL_OS_IDS.includes(id) || !path.isAbsolute(ctx.root) || path.normalize(ctx.root) !== ctx.root
      || /[\x00-\x1f\x7f]/.test(ctx.root) || !identifier.test(ctx.profile)
      || ctx.home !== path.join(ctx.root, 'personal/home') || ctx.resources !== path.join(ctx.root, 'resources')
      || ctx.bin !== path.join(ctx.root, 'bin')) {
    throw new Error('Invalid personal OS context.');
  }
  const state = path.join(ctx.home, 'os', id);
  return { state, home: path.join(state, 'hermes'), record: path.join(state, 'OS_INSTALL.json'),
    launcher: path.join(ctx.bin, id.slice(0, -3)),
    workspace: path.join(ctx.root, 'personal/os', id, 'workspace'),
    distribution: path.join(ctx.resources, 'os-distributions', id) };
}

async function privatePath(ctx, target, { allowMissing = false } = {}) {
  if (!target.startsWith(`${ctx.root}${path.sep}`)) throw new Error('Personal OS path escaped its Workstation.');
  await assertSafePath(target, { allowMissing });
  const relative = path.relative(ctx.root, target).split(path.sep);
  for (let i = 0; i <= relative.length; i++) {
    const item = path.join(ctx.root, ...relative.slice(0, i));
    let info;
    try { info = await fs.lstat(item); } catch (error) { if (error.code === 'ENOENT' && allowMissing) return; throw error; }
    if (info.uid !== process.getuid() || (info.mode & 0o077) || info.isSymbolicLink()
        || (!info.isDirectory() && !(i === relative.length && info.isFile() && info.nlink === 1))) {
      throw new Error('Personal OS paths must be private, owned and unlinked.');
    }
  }
}

function compiledRecord(ctx, id, value) {
  const p = personalOSPaths(ctx, id);
  if (!object(value) || value.schema_version !== 4 || value.os_id !== id
      || typeof value.os_version !== 'string' || !/^[0-9][a-zA-Z0-9.+-]{0,63}$/.test(value.os_version)
      || value.workspace_root !== p.workspace || value.hermes_home !== p.home
      || value.boundary !== 'personal-same-uid' || value.claim !== 'COMPILED_NOT_INSTALLED'
      || !digest.test(value.inputs_sha256) || !digest.test(value.artifacts_sha256)
      || !object(value.role_profile_map) || !Array.isArray(value.profiles)
      || value.profiles.length < 1 || value.profiles.length > 64) throw new Error('Invalid personal OS compilation evidence.');
  const roles = Object.keys(value.role_profile_map).sort();
  const mapping = Object.fromEntries(roles.map(role => {
    if (!identifier.test(role)) throw new Error('Invalid personal OS role.');
    const suffix = crypto.createHash('sha256').update([ctx.root, ctx.profile, id, role].join('\0')).digest('hex').slice(0, 16);
    const expected = `w-${suffix}-${role.slice(0, 25).replace(/-+$/, '')}`;
    if (value.role_profile_map[role] !== expected) throw new Error('Personal OS role escaped its namespace.');
    return [role, expected];
  }));
  const profiles = Object.values(mapping).sort();
  if (!same([...value.profiles].sort(), profiles) || new Set(profiles).size !== profiles.length
      || !profiles.includes(value.nano_director)) throw new Error('Incomplete personal OS role inventory.');
  return { schema_version: 4, os_id: id, os_version: value.os_version, profiles,
    nano_director: value.nano_director, role_profile_map: mapping, workspace_root: p.workspace,
    hermes_home: p.home, boundary: 'personal-same-uid', claim: 'COMPILED_NOT_INSTALLED',
    inputs_sha256: value.inputs_sha256, artifacts_sha256: value.artifacts_sha256 };
}

async function compile(ctx, id, run, check) {
  const p = personalOSPaths(ctx, id), runtime = runtimePaths(ctx);
  await privatePath(ctx, p.distribution, { allowMissing: !check });
  await privatePath(ctx, p.home, { allowMissing: !check });
  await privatePath(ctx, p.workspace, { allowMissing: !check });
  const args = ['-I', '-B', path.join(ctx.sourceRoot, 'scripts/station_workstation_os.py'),
    '--root', ctx.root, '--profile', ctx.profile, '--os-id', id, '--output', p.distribution,
    ...(check ? ['--check'] : [])];
  const result = await run(runtime.python, args, { env: privateEnv(ctx), cwd: ctx.projects, timeoutMs: 120000, allowFailure: true });
  if (result.code !== 0 || typeof result.stdout !== 'string' || Buffer.byteLength(result.stdout) > 65536) throw new Error('Personal OS source/compilation check failed.');
  const record = compiledRecord(ctx, id, JSON.parse(result.stdout));
  await privatePath(ctx, path.join(p.distribution, 'COMPILED.json'));
  if (!same(compiledRecord(ctx, id, await readJSON(path.join(p.distribution, 'COMPILED.json'))), record)) throw new Error('Personal OS compiled readback changed.');
  return record;
}

function installRecord(ctx, id, value) {
  if (!object(value) || value.schema_version !== 1 || value.root !== ctx.root
      || value.workstation_profile !== ctx.profile || value.uid !== process.getuid()
      || !object(value.profiles)) throw new Error('Personal OS installation checkpoint is invalid.');
  const compiled = compiledRecord(ctx, id, value.compiled);
  if (!same(Object.keys(value.profiles).sort(), compiled.profiles)
      || Object.values(value.profiles).some(status => !['planned', 'pending', 'installed'].includes(status))) {
    throw new Error('Personal OS installation checkpoint is incomplete.');
  }
  return { schema_version: 1, root: ctx.root, workstation_profile: ctx.profile, uid: process.getuid(),
    compiled, profiles: Object.fromEntries(compiled.profiles.map(name => [name, value.profiles[name]])) };
}

async function loadInstall(ctx, id) {
  const { record } = personalOSPaths(ctx, id);
  await privatePath(ctx, record);
  return installRecord(ctx, id, await readJSON(record));
}

function launcherBytes(ctx, id, record) {
  const p = personalOSPaths(ctx, id);
  const scoped = { ...ctx, hermesHome: p.home, profile: record.compiled.nano_director };
  const script = launcher(scoped, runtimePaths(ctx).hermes, [], { hermes: true, privateFiles: true });
  const entry = '\nexec /usr/bin/env -i ';
  if (!script.includes(entry)) throw new Error('Unsupported private launcher format.');
  const quoted = `'${p.workspace.replaceAll("'", "'\\''")}'`;
  return script.replace(entry, `\ncd ${quoted} || exit 1${entry}`);
}

async function launcherMatches(ctx, id, record) {
  const p = personalOSPaths(ctx, id);
  await privatePath(ctx, p.launcher);
  const handle = await fs.open(p.launcher, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const info = await handle.stat();
    if (!info.isFile() || info.nlink !== 1 || info.uid !== process.getuid() || (info.mode & 0o7777) !== 0o700 || info.size > 65536) return false;
    return await handle.readFile('utf8') === launcherBytes(ctx, id, record);
  } finally { await handle.close(); }
}

async function publishLauncher(ctx, id, record) {
  const p = personalOSPaths(ctx, id);
  await privatePath(ctx, p.launcher, { allowMissing: true });
  if (!await missing(p.launcher)) {
    if (!await launcherMatches(ctx, id, record)) throw new Error('Existing personal OS launcher differs; no overwrite.');
    return;
  }
  const temporary = `${p.launcher}.${crypto.randomUUID()}.tmp`;
  const handle = await fs.open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o700);
  try {
    try { await handle.writeFile(launcherBytes(ctx, id, record)); await handle.sync(); }
    finally { await handle.close(); }
    await fs.link(temporary, p.launcher);
  } finally { await fs.unlink(temporary); }
}

// Parse only bounded, private metadata, not a profile import or a native command
// that might load its .env, plugins, model, cron, or gateway. Never print values.
export const OS_PROFILE_READBACK = String.raw`
import json, os, pathlib, stat, sys
import yaml
root, name, version, binding_json, source, fresh = sys.argv[1:]
root, source = pathlib.Path(root), pathlib.Path(source)
binding = json.loads(binding_json)
def safe(path):
    relative = path.relative_to(root)
    for current in (root, *[root.joinpath(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1)]):
        info = current.lstat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077 or stat.S_ISLNK(info.st_mode):
            raise ValueError('unsafe private metadata')
        if not stat.S_ISDIR(info.st_mode) and not (current == path and stat.S_ISREG(info.st_mode) and info.st_nlink == 1):
            raise ValueError('unsafe metadata type')
def read(path, limit=262144):
    safe(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('unsafe metadata file')
        return handle.read(limit + 1)
target = pathlib.Path(binding['hermes_home']) / 'profiles' / name
config = yaml.safe_load(read(target / 'config.yaml'))
manifest = yaml.safe_load(read(target / 'distribution.yaml'))
if not isinstance(config, dict) or not isinstance(config.get('profile'), dict) or config['profile'].get('id') != name:
    raise ValueError('profile configuration is not readable or bound')
if not isinstance(manifest, dict) or manifest.get('name') != name or str(manifest.get('version')) != version or manifest.get('source') != str(source):
    raise ValueError('native distribution metadata differs')
if json.loads(read(target / 'PERSONAL.json')) != binding:
    raise ValueError('personal role binding differs')
if fresh == 'fresh':
    expected = yaml.safe_load(read(source / 'distribution.yaml'))
    entries = expected.get('distribution_owned')
    if not isinstance(entries, list) or not entries:
        raise ValueError('no explicit distribution payload')
    for entry in entries:
        relative = pathlib.PurePosixPath(entry)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe payload entry')
        original = source.joinpath(*relative.parts)
        if not original.exists():
            continue
        safe(original)
        files = sorted(original.rglob('*')) if original.is_dir() else [original]
        for item in files:
            safe(item)
            if item.is_dir():
                continue
            rel = item.relative_to(source)
            if rel == pathlib.Path('distribution.yaml'):
                continue
            if read(item, 8388608) != read(target / rel, 8388608):
                raise ValueError('native payload differs from compiled source')
print('personal-os-profile-ok')
`;

async function readback(ctx, id, record, name, run, fresh = false) {
  const p = personalOSPaths(ctx, id), c = record.compiled;
  await privatePath(ctx, path.join(p.home, 'profiles', name));
  const binding = { schema_version: 1, boundary: 'personal-same-uid', os_id: id,
    workstation_profile: ctx.profile, hermes_home: p.home, workspace_root: p.workspace,
    role_profile_map: c.role_profile_map, zone_isolation: false, accounts_enrolled: false };
  const result = await run(runtimePaths(ctx).python, ['-I', '-B', '-c', OS_PROFILE_READBACK,
    ctx.root, name, c.os_version, JSON.stringify(binding), path.join(p.distribution, 'profiles', name), fresh ? 'fresh' : 'preserved'],
  { env: privateEnv(ctx, { HERMES_HOME: p.home }), cwd: p.workspace, timeoutMs: 120000, allowFailure: true });
  if (result.code !== 0 || result.stdout.trim() !== 'personal-os-profile-ok') throw new Error('Personal OS native profile readback failed.');
}

export async function provisionOS(ctx, { run, emit = () => {} }) {
  for (const id of PERSONAL_OS_IDS) {
    emit({ phase: `os:${id}`, status: 'running', message: 'Preparing native personal OS software; accounts and schedulers remain inactive.' });
    try {
      const p = personalOSPaths(ctx, id);
      if (await missing(p.distribution)) await compile(ctx, id, run, false);
      const current = await compile(ctx, id, run, true);
      let record;
      if (await missing(p.record)) {
        // All targets must be absent before recording authority to install any.
        // An existing directory plus a matching manifest is not adoption consent.
        for (const name of current.profiles) {
          const target = path.join(p.home, 'profiles', name);
          await privatePath(ctx, target, { allowMissing: true });
          if (!await missing(target)) throw new Error('Unrecorded personal OS profile exists; explicit review is required.');
        }
        record = { schema_version: 1, root: ctx.root, workstation_profile: ctx.profile, uid: process.getuid(),
          compiled: current, profiles: Object.fromEntries(current.profiles.map(name => [name, 'planned'])) };
        await privatePath(ctx, p.record, { allowMissing: true });
        await atomicJSON(p.record, record, { exclusive: true });
      } else record = await loadInstall(ctx, id);
      const changed = !same(record.compiled, current);
      if (changed && Object.values(record.profiles).some(status => status !== 'installed')) throw new Error('An interrupted personal OS install must be reviewed before a new source generation.');
      await privatePath(ctx, p.launcher, { allowMissing: true });
      if (!await missing(p.launcher) && !await launcherMatches(ctx, id, record)) throw new Error('Existing personal OS launcher differs; no overwrite.');
      for (const name of record.compiled.profiles) {
        if (record.profiles[name] === 'installed') { await readback(ctx, id, record, name, run); continue; }
        const target = path.join(p.home, 'profiles', name);
        await privatePath(ctx, target, { allowMissing: true });
        if (!await missing(target)) throw new Error('Interrupted or unrecorded personal OS profile exists; no automatic adoption or overwrite.');
        if (!same(await compile(ctx, id, run, true), record.compiled)) throw new Error('Personal OS source generation changed before native installation.');
        record.profiles[name] = 'pending';
        await atomicJSON(p.record, record);
        const result = await run(runtimePaths(ctx).python, ['-I', '-B', '-c', OS_INSTALL_EXEC,
          runtimePaths(ctx).hermes, '--profile', 'default', 'profile', 'install',
          path.join(p.distribution, 'profiles', name), '--name', name, '--yes'],
        { env: privateEnv(ctx, { HERMES_HOME: p.home }), cwd: p.workspace, timeoutMs: 120000, allowFailure: true });
        if (result.code !== 0) throw new Error('Native personal OS profile installation failed.');
        await readback(ctx, id, record, name, run, true);
        record.profiles[name] = 'installed';
        await atomicJSON(p.record, record);
      }
      await publishLauncher(ctx, id, record);
      emit({ phase: `os:${id}`, status: 'prepared', message: changed
        ? 'New compiled software delivered; existing native profiles preserved, explicit profile upgrade pending.'
        : 'Native personal OS profiles installed and read back; no model, account, cron or gateway was activated.' });
    } catch {
      emit({ phase: `os:${id}`, status: 'failed', message: 'Personal OS software failed; preserve private checkpoints and inspect before explicit repair.' });
      throw new Error(`${id} personal OS delivery failed; no native output or configuration values were recorded.`);
    }
  }
}

export async function verifyOS(ctx, { run, emit = () => {} }) {
  const checks = [];
  for (const id of PERSONAL_OS_IDS) {
    let compiled, record;
    try { compiled = await compile(ctx, id, run, true); } catch { /* Bounded failed evidence only. */ }
    checks.push({ id: `os:${id}:distribution`, required: true, status: compiled ? 'verified' : 'failed',
      detail: compiled ? 'Current bundled personal OS distribution matches canonical source; software only.' : 'Current personal OS distribution is missing, unsafe or differs from reviewed source.' });
    let native = false;
    try {
      if (!compiled) throw new Error('Compiled source has not been verified.');
      record = await loadInstall(ctx, id);
      if (Object.values(record.profiles).some(status => status !== 'installed')) throw new Error('Interrupted native installation.');
      for (const name of record.compiled.profiles) await readback(ctx, id, record, name, run);
      if (!await launcherMatches(ctx, id, record)) throw new Error('Personal OS director launcher differs.');
      native = true;
    } catch { /* Never adopt profile directories or import account-bearing config. */ }
    const changed = native && !same(record.compiled, compiled);
    checks.push({ id: `os:${id}:native-profiles`, required: true, status: native ? 'verified' : 'failed',
      detail: native ? (changed
        ? 'Previously recorded native profiles are preserved and metadata verified; new source is delivered but profile upgrade remains pending.'
        : 'Recorded native profiles are scoped and readable; private director launcher binds the exact home/workspace. No account or behavioral acceptance claim.')
        : 'Native profile installation evidence or bounded metadata readback failed; explicit review/repair is required.' });
    checks.push({ id: `os:${id}:enrollment`, required: false, status: 'not-configured',
      detail: changed ? 'Explicit profile upgrade and account/role/task acceptance are pending. No user configuration was overwritten.'
        : 'Personal same-UID team, not a Zone. Model identities, peer routing and real tasks require explicit enrollment/acceptance; no scheduler or gateway was started.' });
    emit({ phase: 'verify', status: native && compiled ? 'verified' : 'failed', message: `os:${id}` });
  }
  return checks;
}
