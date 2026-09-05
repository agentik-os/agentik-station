import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { PERSONAL_OS_IDS, OS_INSTALL_EXEC, OS_PROFILE_READBACK, personalOSPaths, provisionOS, verifyOS } from '../os.mjs';
import { runtimePaths } from '../runtime.mjs';

const okay = stdout => ({ code: 0, stdout, stderr: '' });
const json = async file => JSON.parse(await fs.readFile(file, 'utf8'));
const write = async (file, content) => { await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 }); await fs.writeFile(file, content, { mode: 0o600 }); };
const writeJSON = (file, content) => write(file, JSON.stringify(content));

async function fixture(t, rootName = 'station') {
  const scratch = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'station-os-'));
  t.after(() => fs.rm(scratch, { recursive: true, force: true }));
  const root = path.join(scratch, rootName);
  const ctx = { root, sourceRoot: path.join(scratch, 'source'), accountHome: '/never-read/account',
    home: path.join(root, 'personal/home'), profile: 'station-0123456789ab', pins: {},
    ...Object.fromEntries(['tools', 'bin', 'cache', 'evidence', 'resources', 'projects'].map(name => [name, path.join(root, name)])) };
  ctx.hermesHome = path.join(ctx.home, '.hermes');
  for (const target of [ctx.home, ctx.tools, ctx.bin, ctx.cache, ctx.resources, ctx.projects]) await fs.mkdir(target, { recursive: true, mode: 0o700 });
  return { ctx, scratch };
}

async function compiled(ctx, id, version = '1.0', generation = 'a') {
  const p = personalOSPaths(ctx, id);
  for (const target of [p.home, p.workspace, p.distribution]) await fs.mkdir(target, { recursive: true, mode: 0o700 });
  const mapping = Object.fromEntries(['director', 'worker'].map(role => [role,
    `w-${crypto.createHash('sha256').update([ctx.root, ctx.profile, id, role].join('\0')).digest('hex').slice(0, 16)}-${role}`]));
  const record = { schema_version: 4, os_id: id, os_version: version, profiles: Object.values(mapping),
    nano_director: mapping.director, role_profile_map: mapping, workspace_root: p.workspace, hermes_home: p.home,
    boundary: 'personal-same-uid', claim: 'COMPILED_NOT_INSTALLED', inputs_sha256: generation.repeat(64), artifacts_sha256: generation.repeat(64) };
  const binding = { schema_version: 1, boundary: 'personal-same-uid', os_id: id, workstation_profile: ctx.profile,
    hermes_home: p.home, workspace_root: p.workspace, role_profile_map: mapping, zone_isolation: false, accounts_enrolled: false };
  for (const name of record.profiles) {
    const source = path.join(p.distribution, 'profiles', name);
    await writeJSON(path.join(source, 'config.yaml'), { profile: { id: name }, kanban: { dispatch_in_gateway: false } });
    await writeJSON(path.join(source, 'distribution.yaml'), { name, version,
      distribution_owned: ['config.yaml', 'distribution.yaml', 'PERSONAL.json', 'skills/'] });
    await writeJSON(path.join(source, 'PERSONAL.json'), binding);
    await write(path.join(source, 'skills/station-orchestration/SKILL.md'), '# scoped task\n');
  }
  await writeJSON(path.join(p.distribution, 'COMPILED.json'), record);
  return record;
}

function runner(ctx, options = {}) {
  const calls = [];
  const run = async (bin, args, settings) => {
    calls.push({ bin, args, settings });
    if (args[2] === path.join(ctx.sourceRoot, 'scripts/station_workstation_os.py')) {
      const id = args[args.indexOf('--os-id') + 1], p = personalOSPaths(ctx, id);
      if (!args.includes('--check')) await compiled(ctx, id);
      if (options.failCompile && args.includes('--check')) return { code: 1, stdout: '', stderr: 'sensitive native detail' };
      const value = await json(path.join(p.distribution, 'COMPILED.json'));
      return okay(JSON.stringify(options.transform ? options.transform(value) : value));
    }
    if (args[3] === OS_INSTALL_EXEC) {
      const source = args[args.indexOf('install') + 1], name = args[args.indexOf('--name') + 1];
      const home = settings.env.HERMES_HOME, id = path.basename(path.dirname(home));
      const checkpoint = await json(personalOSPaths(ctx, id).record);
      assert.equal(checkpoint.profiles[name], 'pending', 'private authority checkpoint precedes native install');
      if (!options.noPayload) {
        const target = path.join(home, 'profiles', name);
        await fs.mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
        await fs.cp(source, target, { recursive: true, errorOnExist: true, force: false });
        const manifest = await json(path.join(target, 'distribution.yaml'));
        await writeJSON(path.join(target, 'distribution.yaml'), { ...manifest, source, installed_at: '2026-09-05T00:00:00Z' });
      }
      return { code: options.failInstall ? 23 : 0, stdout: '', stderr: 'never-recorded-token' };
    }
    if (args[3] === OS_PROFILE_READBACK) {
      if (options.failReadback) return { code: 1, stdout: '', stderr: 'never-recorded-token' };
      if (options.python) {
        try { return okay(execFileSync(options.python, args, { encoding: 'utf8', env: settings.env, cwd: settings.cwd, stdio: 'pipe' })); }
        catch (error) { return { code: 1, stdout: '', stderr: String(error.stderr) }; }
      }
      return okay('personal-os-profile-ok\n');
    }
    throw new Error('Unexpected OS command');
  };
  return { run, calls, installs: () => calls.filter(call => call.args[3] === OS_INSTALL_EXEC) };
}

test('default delivery uses exactly three scoped native teams and private checkpoints', async t => {
  const { ctx } = await fixture(t), native = runner(ctx);
  process.env.STATION_OS_TEST_TOKEN = 'never-inherit';
  t.after(() => delete process.env.STATION_OS_TEST_TOKEN);
  await provisionOS(ctx, { run: native.run });
  assert.deepEqual(PERSONAL_OS_IDS, ['stepper-os', 'builder-os', 'librarian-os']);
  assert.equal(native.installs().length, 6);
  const homes = new Set();
  for (const call of native.calls) {
    assert.equal(call.bin, runtimePaths(ctx).python);
    assert.deepEqual(call.args.slice(0, 2), ['-I', '-B']);
    assert.equal(call.settings.env.HOME, ctx.home);
    assert.equal(call.settings.env.STATION_OS_TEST_TOKEN, undefined);
    assert.equal(Object.values(call.settings.env).includes(ctx.accountHome), false);
    assert.equal(call.settings.timeoutMs, 120000);
    assert.equal(call.args.some(value => ['--force', '--force-config', '--alias', 'login', 'start', 'update', 'clone'].includes(value)), false);
  }
  for (const call of native.installs()) {
    homes.add(call.settings.env.HERMES_HOME);
    assert.deepEqual(call.args.slice(4, 9), [runtimePaths(ctx).hermes, '--profile', 'default', 'profile', 'install']);
    assert.equal(call.args.at(-1), '--yes');
    assert.match(call.args[3], /umask\(0o077\)/);
    assert.ok(call.settings.cwd.startsWith(`${ctx.root}/personal/os/`));
  }
  assert.equal(homes.size, 3);
  for (const id of PERSONAL_OS_IDS) {
    const p = personalOSPaths(ctx, id), evidence = await json(p.record);
    assert.ok(Object.values(evidence.profiles).every(value => value === 'installed'));
    assert.equal((await fs.stat(p.record)).mode & 0o777, 0o600);
    assert.equal((await fs.stat(p.home)).mode & 0o777, 0o700);
    assert.equal((await fs.stat(p.launcher)).mode & 0o777, 0o700);
    assert.equal(p.home.startsWith(ctx.tools), false);
  }
});

test('verification requires current compiled provenance and separate recorded native profiles', async t => {
  const { ctx } = await fixture(t), native = runner(ctx);
  await provisionOS(ctx, { run: native.run });
  const prior = await Promise.all(PERSONAL_OS_IDS.map(id => fs.readFile(personalOSPaths(ctx, id).record)));
  native.calls.length = 0;
  const checks = await verifyOS(ctx, { run: native.run });
  assert.equal(checks.filter(check => check.required).length, 6);
  assert.ok(checks.filter(check => check.required).every(check => check.status === 'verified'));
  assert.ok(checks.filter(check => !check.required).every(check => check.status === 'not-configured'));
  assert.equal(native.installs().length, 0);
  assert.ok(native.calls.filter(call => call.args[2]?.endsWith('station_workstation_os.py')).every(call => call.args.includes('--check')));
  for (const [i, id] of PERSONAL_OS_IDS.entries()) assert.deepEqual(await fs.readFile(personalOSPaths(ctx, id).record), prior[i]);
});

test('missing distributions cannot be treated as native software presence', async t => {
  const { ctx } = await fixture(t);
  let called = false;
  const checks = await verifyOS(ctx, { run: async () => { called = true; throw new Error('must not run'); } });
  assert.equal(called, false);
  assert.ok(checks.filter(check => check.required).every(check => check.status === 'failed'));
});

test('compiled artifact or source mismatch prevents every native install', async t => {
  const { ctx } = await fixture(t), native = runner(ctx, { failCompile: true });
  await assert.rejects(provisionOS(ctx, { run: native.run }), /delivery failed/);
  assert.equal(native.installs().length, 0);
  await assert.rejects(fs.lstat(personalOSPaths(ctx, 'stepper-os').record), { code: 'ENOENT' });
});

for (const label of ['workspace', 'role', 'duplicate-profile', 'claim']) test(`compiled ${label} mismatch is rejected`, async t => {
  const { ctx } = await fixture(t);
  const native = runner(ctx, { transform: value => {
    if (label === 'workspace') value.workspace_root = ctx.accountHome;
    if (label === 'role') value.role_profile_map.director = 'unscoped-director';
    if (label === 'duplicate-profile') value.profiles.push(value.profiles[0]);
    if (label === 'claim') value.claim = 'OPERATIONAL';
    return value;
  } });
  await assert.rejects(provisionOS(ctx, { run: native.run }), /delivery failed/);
  assert.equal(native.installs().length, 0);
});

test('existing unrecorded profile is never adopted even with matching metadata', async t => {
  const { ctx } = await fixture(t), c = await compiled(ctx, 'stepper-os'), p = personalOSPaths(ctx, 'stepper-os');
  const target = path.join(p.home, 'profiles', c.profiles[0]);
  await fs.cp(path.join(p.distribution, 'profiles', c.profiles[0]), target, { recursive: true });
  const original = await fs.readFile(path.join(target, 'config.yaml'));
  const native = runner(ctx);
  await assert.rejects(provisionOS(ctx, { run: native.run }), /delivery failed/);
  assert.equal(native.installs().length, 0);
  assert.deepEqual(await fs.readFile(path.join(target, 'config.yaml')), original);
  await assert.rejects(fs.lstat(p.record), { code: 'ENOENT' });
});

test('interrupted install retains pending checkpoint and refuses to adopt partial target', async t => {
  const { ctx } = await fixture(t), failed = runner(ctx, { failInstall: true });
  await assert.rejects(provisionOS(ctx, { run: failed.run }), /delivery failed/);
  assert.equal(failed.installs().length, 1);
  const p = personalOSPaths(ctx, 'stepper-os'), checkpoint = await json(p.record);
  assert.ok(Object.values(checkpoint.profiles).includes('pending'));
  const retry = runner(ctx);
  await assert.rejects(provisionOS(ctx, { run: retry.run }), /delivery failed/);
  assert.equal(retry.installs().length, 0);
  assert.deepEqual(await json(p.record), checkpoint);
});

test('failed native install with no target may resume only its recorded absent slot', async t => {
  const { ctx } = await fixture(t), failed = runner(ctx, { failInstall: true, noPayload: true });
  await assert.rejects(provisionOS(ctx, { run: failed.run }), /delivery failed/);
  const retry = runner(ctx);
  await provisionOS(ctx, { run: retry.run });
  assert.equal(retry.installs().length, 6);
});

test('zero exit without a native profile cannot commit installed status', async t => {
  const { ctx } = await fixture(t), native = runner(ctx, { noPayload: true });
  await assert.rejects(provisionOS(ctx, { run: native.run }), /delivery failed/);
  assert.equal(Object.values((await json(personalOSPaths(ctx, 'stepper-os').record)).profiles).includes('installed'), false);
});

test('software updates preserve existing configuration, checkpoint and native generation', async t => {
  const { ctx } = await fixture(t), native = runner(ctx, { python: await yamlPython() });
  await provisionOS(ctx, { run: native.run });
  const p = personalOSPaths(ctx, 'stepper-os'), prior = await fs.readFile(p.record), record = await json(p.record);
  const oldLauncher = await fs.readFile(p.launcher), oldInode = (await fs.stat(p.launcher)).ino;
  const config = path.join(p.home, 'profiles', record.compiled.profiles[0], 'config.yaml');
  await writeJSON(config, { profile: { id: record.compiled.profiles[0] }, custom_provider: 'operator-setting' });
  const before = await fs.readFile(config);
  await compiled(ctx, 'stepper-os', '2.0', 'b');
  native.calls.length = 0;
  const events = [];
  await provisionOS(ctx, { run: native.run, emit: event => events.push(event) });
  assert.equal(native.installs().length, 0);
  assert.deepEqual(await fs.readFile(p.record), prior);
  assert.deepEqual(await fs.readFile(config), before);
  assert.deepEqual(await fs.readFile(p.launcher), oldLauncher);
  assert.equal((await fs.stat(p.launcher)).ino, oldInode);
  assert.ok(events.some(event => event.message.includes('upgrade pending')));
  const checks = await verifyOS(ctx, { run: native.run });
  assert.equal(checks.find(check => check.id === 'os:stepper-os:native-profiles').status, 'verified');
  assert.match(checks.find(check => check.id === 'os:stepper-os:enrollment').detail, /upgrade.*pending/);
});

test('interrupted checkpoint cannot cross compiled source generations', async t => {
  const { ctx } = await fixture(t), failed = runner(ctx, { failInstall: true, noPayload: true });
  await assert.rejects(provisionOS(ctx, { run: failed.run }));
  await compiled(ctx, 'stepper-os', '2.0', 'b');
  const retry = runner(ctx);
  await assert.rejects(provisionOS(ctx, { run: retry.run }), /delivery failed/);
  assert.equal(retry.installs().length, 0);
});

test('compiled source generation changing after its checkpoint blocks native execution', async t => {
  const { ctx } = await fixture(t), native = runner(ctx);
  let checked = 0;
  const run = async (bin, args, settings) => {
    if (args.includes('--check') && ++checked === 2) await compiled(ctx, 'stepper-os', '1.0', 'b');
    return native.run(bin, args, settings);
  };
  await assert.rejects(provisionOS(ctx, { run }), /delivery failed/);
  assert.equal(native.installs().length, 0);
  assert.ok(Object.values((await json(personalOSPaths(ctx, 'stepper-os').record)).profiles).every(status => status === 'planned'));
});

for (const label of ['state-symlink', 'distribution-symlink', 'public-state', 'record-hardlink']) test(`${label} is refused before native installation`, async t => {
  const { ctx, scratch } = await fixture(t), p = personalOSPaths(ctx, 'stepper-os');
  await compiled(ctx, 'stepper-os');
  if (label === 'state-symlink' || label === 'distribution-symlink') {
    const target = label === 'state-symlink' ? p.state : p.distribution;
    const parked = path.join(scratch, 'parked');
    await fs.rename(target, parked);
    await fs.symlink(parked, target);
  } else if (label === 'public-state') await fs.chmod(p.state, 0o755);
  else {
    await writeJSON(p.record, {});
    await fs.link(p.record, path.join(scratch, 'record-alias'));
  }
  const native = runner(ctx);
  await assert.rejects(provisionOS(ctx, { run: native.run }), /delivery failed/);
  assert.equal(native.installs().length, 0);
});

test('failure output and configuration values are not exposed in events or checks', async t => {
  const { ctx } = await fixture(t), native = runner(ctx, { failReadback: true }), events = [];
  await assert.rejects(provisionOS(ctx, { run: native.run, emit: value => events.push(value) }), error => !error.message.includes('never-recorded-token'));
  const checks = await verifyOS(ctx, { run: native.run });
  assert.equal(JSON.stringify({ events, checks }).includes('never-recorded-token'), false);
  assert.ok(checks.filter(check => check.required).every(check => check.status !== 'verified' || check.id.endsWith(':distribution')));
});

test('native OS aliases select only their recorded director, private environment and owning workspace', async t => {
  const { ctx } = await fixture(t, "station's private $(literal)"), native = runner(ctx);
  await provisionOS(ctx, { run: native.run });
  const code = 'console.log(JSON.stringify({argv:process.argv.slice(1),cwd:process.cwd(),home:process.env.HOME,hermes:process.env.HERMES_HOME,secret:process.env.STATION_OS_TEST_TOKEN,umask:process.umask()}))';
  const quote = value => `'${value.replaceAll("'", "'\\''")}'`;
  const executable = runtimePaths(ctx).hermes;
  await write(executable, `#!/bin/sh\nexec ${quote(process.execPath)} -e ${quote(code)} -- "$@"\n`);
  await fs.chmod(executable, 0o700);
  for (const id of PERSONAL_OS_IDS) {
    const p = personalOSPaths(ctx, id), record = await json(p.record);
    const result = JSON.parse(execFileSync(p.launcher, ['chat', 'literal argument'], {
      encoding: 'utf8', cwd: ctx.projects,
      env: { HOME: '/not-selected/account', HERMES_HOME: '/not-selected/hermes', PATH: '/usr/bin:/bin', STATION_OS_TEST_TOKEN: 'do-not-inherit' },
    }));
    assert.deepEqual(result.argv, ['--profile', record.compiled.nano_director, 'chat', 'literal argument']);
    assert.equal(result.home, ctx.home);
    assert.equal(result.hermes, p.home);
    assert.equal(result.cwd, p.workspace);
    assert.equal(result.secret, undefined);
    assert.equal(result.umask, 0o077);
  }
});

for (const kind of ['bytes', 'mode', 'symlink', 'hardlink', 'missing']) test(`changed OS launcher ${kind} fails required native check without being overwritten`, async t => {
  const { ctx, scratch } = await fixture(t), native = runner(ctx);
  await provisionOS(ctx, { run: native.run });
  const p = personalOSPaths(ctx, 'stepper-os');
  if (kind === 'bytes') await write(p.launcher, '#!/bin/sh\nexit 9\n');
  if (kind === 'mode') await fs.chmod(p.launcher, 0o600);
  if (kind === 'symlink') {
    await fs.rename(p.launcher, path.join(scratch, 'preserved-launcher'));
    await fs.symlink(path.join(scratch, 'preserved-launcher'), p.launcher);
  }
  if (kind === 'hardlink') await fs.link(p.launcher, path.join(scratch, 'launcher-alias'));
  if (kind === 'missing') await fs.unlink(p.launcher);
  const checks = await verifyOS(ctx, { run: native.run });
  assert.equal(checks.find(check => check.id === 'os:stepper-os:native-profiles').status, 'failed');
  native.calls.length = 0;
  if (kind === 'missing') {
    // Missing generated software is repairable; no profile is reinstalled.
    await provisionOS(ctx, { run: native.run });
    assert.equal((await fs.stat(p.launcher)).mode & 0o777, 0o700);
  } else {
    const before = await fs.lstat(p.launcher);
    await assert.rejects(provisionOS(ctx, { run: native.run }), /delivery failed/);
    const after = await fs.lstat(p.launcher);
    assert.equal(after.ino, before.ino);
    assert.equal(after.mode, before.mode);
  }
  assert.equal(native.installs().length, 0);
});

test('occupied launcher is not overwritten and blocks first native profile install', async t => {
  const { ctx } = await fixture(t), native = runner(ctx), p = personalOSPaths(ctx, 'stepper-os');
  await write(p.launcher, '#!/bin/sh\n# operator-owned custom entry\n');
  await fs.chmod(p.launcher, 0o700);
  const original = await fs.readFile(p.launcher);
  await assert.rejects(provisionOS(ctx, { run: native.run }), /delivery failed/);
  assert.equal(native.installs().length, 0);
  assert.deepEqual(await fs.readFile(p.launcher), original);
});

async function yamlPython() {
  for (const directory of (process.env.PATH || '').split(path.delimiter)) {
    if (!path.isAbsolute(directory)) continue;
    const candidate = path.join(directory, 'python3');
    try { execFileSync(candidate, ['-I', '-B', '-c', 'import yaml'], { stdio: 'pipe' }); return candidate; }
    catch { /* Use an existing interpreter only; never install test dependencies. */ }
  }
  return null;
}

test('actual isolated Python readback verifies complete fresh payload and rejects metadata substitutions', async t => {
  const python = await yamlPython();
  if (!python) return t.skip('Requires an existing Python with PyYAML, as installed with Hermes.');
  const { ctx } = await fixture(t), native = runner(ctx, { python });
  await provisionOS(ctx, { run: native.run });
  assert.ok((await verifyOS(ctx, { run: native.run })).filter(check => check.required).every(check => check.status === 'verified'));
  const p = personalOSPaths(ctx, 'stepper-os'), record = await json(p.record), name = record.compiled.profiles[0];
  const target = path.join(p.home, 'profiles', name), manifestPath = path.join(target, 'distribution.yaml');
  const manifest = await fs.readFile(manifestPath);
  await writeJSON(manifestPath, { name, version: '999', source: path.join(p.distribution, 'profiles', name) });
  let checks = await verifyOS(ctx, { run: native.run });
  assert.equal(checks.find(check => check.id === 'os:stepper-os:native-profiles').status, 'failed');
  await write(manifestPath, manifest);
  await fs.chmod(path.join(target, 'config.yaml'), 0o644);
  checks = await verifyOS(ctx, { run: native.run });
  assert.equal(checks.find(check => check.id === 'os:stepper-os:native-profiles').status, 'failed');
  await fs.chmod(path.join(target, 'config.yaml'), 0o600);
  await fs.unlink(path.join(target, 'PERSONAL.json'));
  await fs.symlink(path.join(p.distribution, 'profiles', name, 'PERSONAL.json'), path.join(target, 'PERSONAL.json'));
  checks = await verifyOS(ctx, { run: native.run });
  assert.equal(checks.find(check => check.id === 'os:stepper-os:native-profiles').status, 'failed');
});

test('actual fresh readback refuses missing skill payload and never records installed', async t => {
  const python = await yamlPython();
  if (!python) return t.skip('Requires an existing Python with PyYAML.');
  const { ctx } = await fixture(t), native = runner(ctx, { python });
  const run = async (bin, args, settings) => {
    const result = await native.run(bin, args, settings);
    if (args[3] === OS_INSTALL_EXEC) {
      const name = args[args.indexOf('--name') + 1];
      await fs.unlink(path.join(settings.env.HERMES_HOME, 'profiles', name, 'skills/station-orchestration/SKILL.md'));
    }
    return result;
  };
  await assert.rejects(provisionOS(ctx, { run }), /delivery failed/);
  const record = await json(personalOSPaths(ctx, 'stepper-os').record);
  assert.equal(Object.values(record.profiles).includes('installed'), false);
});
