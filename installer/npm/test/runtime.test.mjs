import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { privateEnv, runtimePaths, prerequisites, provision, verify, checkoutHermes, createWorkstationProfile, launcher, RMUX_EXTRACTOR } from '../runtime.mjs';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const pins = Object.fromEntries((await fs.readFile(path.join(sourceRoot, 'config/versions.lock'), 'utf8')).split('\n').filter(Boolean).map(line => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]));

async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'station-rt-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const ctx = { root, sourceRoot, home: path.join(root, 'home'), accountHome: '/not-adopted/account', platform: process.platform, arch: process.arch, profile: 'station-test', pins,
    ...Object.fromEntries(['bin', 'tools', 'cache', 'evidence', 'resources', 'projects'].map(name => [name, path.join(root, name)])) };
  ctx.hermesHome = path.join(ctx.home, '.hermes');
  for (const target of [ctx.home, ctx.bin, ctx.tools, ctx.cache, ctx.resources, ctx.projects]) await fs.mkdir(target, { recursive: true });
  return ctx;
}

test('runtime environment contains only private state and no inherited credentials', async t => {
  const ctx = await fixture(t);
  process.env.STATION_RUNTIME_TEST_SECRET = 'must-not-leak';
  t.after(() => delete process.env.STATION_RUNTIME_TEST_SECRET);
  const env = privateEnv(ctx);
  assert.equal(env.STATION_RUNTIME_TEST_SECRET, undefined);
  assert.equal(env.HOME, ctx.home);
  assert.equal(env.HERMES_HOME, ctx.hermesHome);
  assert.equal(env.AGK_ENVIRONMENT, 'private');
  assert.equal(env.USER, 'station-workstation');
  assert.equal(env.GIT_CONFIG_GLOBAL, '/dev/null');
  assert.ok(env.RMUX_TMPDIR.startsWith(ctx.root));
  assert.equal(env.RMUX_SDK_DAEMON_BINARY, path.join(ctx.tools, 'rmux/bin/rmux-daemon'));
  assert.ok(env.npm_config_userconfig.startsWith(ctx.home));
  assert.equal(Object.values(env).some(value => String(value).includes(ctx.accountHome)), false);
});

test('runtime and gateway paths use stable venv and a unique named profile', async t => {
  const ctx = await fixture(t), p = runtimePaths(ctx);
  assert.equal(p.hermes, `${ctx.tools}/hermes/venv/bin/hermes`);
  assert.equal(p.source, `${ctx.tools}/hermes/source`);
  assert.equal(p.profile, `${ctx.hermesHome}/profiles/station-test`);
  assert.equal(p.agk, `${ctx.tools}/agk-terminal`);
});

test('unsupported platform and excessive native socket path are explicit prerequisite blockers', async t => {
  const ctx = await fixture(t);
  ctx.platform = 'win32';
  ctx.cache = path.join(ctx.root, 'x'.repeat(100));
  const result = await prerequisites(ctx);
  assert.ok(result.checks.some(check => check.id === 'platform' && check.status === 'blocked'));
  assert.ok(result.checks.some(check => check.id === 'rmux:socket-path' && check.status === 'blocked'));
});

test('missing prerequisites return gates before runtime writes or command execution', async t => {
  const ctx = await fixture(t);
  ctx.platform = 'unsupported';
  const before = await fs.readdir(ctx.tools);
  const result = await provision(ctx, { run: async () => ({ code: 1, stdout: '', stderr: '' }) });
  assert.ok(result.some(check => check.status === 'blocked'));
  assert.deepEqual(await fs.readdir(ctx.tools), before);
});

test('local verification separates software from accounts, services, audio and worker availability', async t => {
  const ctx = await fixture(t), calls = [];
  const run = async (bin, args, options) => {
    calls.push({ bin, args, options });
    return { code: 0, stdout: `${pins.HERMES_COMMIT}\nimports-ok\nrmux ${pins.RMUX_VERSION}\nAGK-TUI PRIVATE INSTALLATION_ONLY\n${pins.VERCEL_CLI_VERSION}\n${pins.CODEX_CLI_VERSION}\n${pins.SHADCN_CLI_VERSION}\nsdk-ok`, stderr: '' };
  };
  const checks = await verify(ctx, { run });
  for (const name of ['gateway', 'accounts', 'voice:native-libraries']) assert.equal(checks.find(check => check.id === name).status, 'not-configured');
  for (const name of ['ponytail', 'strix', 'services']) {
    assert.equal(checks.find(check => check.id === name).status, 'blocked');
    assert.equal(checks.find(check => check.id === name).required, false);
  }
  assert.ok(calls.some(call => call.args.includes('--ci')));
  assert.ok(calls.some(call => call.args.includes('--offline')));
  assert.ok(calls.every(call => call.options.env.HOME === ctx.home));
  assert.ok(calls.every(call => !call.args.includes('start') && !call.args.includes('activate') && !call.args.includes('login')));
});

test('failed native probes do not become successful presence checks', async t => {
  const ctx = await fixture(t);
  const checks = await verify(ctx, { run: async () => ({ code: 1, stdout: '', stderr: 'failure' }) });
  assert.ok(checks.filter(check => check.id.startsWith('agk:')).every(check => check.status === 'failed'));
  assert.equal(checks.find(check => check.id === 'hermes:revision').status, 'failed');
  assert.equal(checks.some(check => check.status === 'verified'), false);
});

test('verify accepts a native CLI version on stderr but still enforces exit code', async t => {
  const ctx = await fixture(t);
  const checks = await verify(ctx, { run: async (_bin, args) => ({ code: args.includes('--version') ? 0 : 1, stdout: '', stderr: `${pins.VERCEL_CLI_VERSION} ${pins.CODEX_CLI_VERSION} ${pins.SHADCN_CLI_VERSION}` }) });
  assert.equal(checks.find(check => check.id === 'cli:vercel').status, 'verified');
  assert.equal(checks.find(check => check.id === 'agk:inventory').status, 'failed');
});

test('unexpected installed-probe exception is bounded to failed evidence', async t => {
  const ctx = await fixture(t);
  const checks = await verify(ctx, { run: async () => { throw new Error('not installed'); } });
  assert.equal(checks.find(check => check.id === 'hermes:imports').status, 'failed');
  assert.equal(checks.find(check => check.id === 'sdk:discord.js').status, 'failed');
});

async function fakeGit(ctx, { changed = '', sparse = '/*\n!/contributors/emails/\n' } = {}) {
  const calls = [], p = runtimePaths(ctx);
  const run = async (_binary, args) => {
    calls.push(args);
    if (args[0] === 'init') await fs.mkdir(path.join(p.source, '.git/info'), { recursive: true });
    if (args.includes('sparse-checkout')) await fs.writeFile(path.join(p.source, '.git/info/sparse-checkout'), sparse);
    return { code: 0, stdout: args.includes('rev-parse') ? ctx.pins.HERMES_COMMIT : args.includes('status') ? changed : '', stderr: '' };
  };
  return { calls, run };
}

test('macOS excludes only case-colliding attribution before first checkout', async t => {
  const ctx = await fixture(t); ctx.platform = 'darwin';
  const git = await fakeGit(ctx);
  await checkoutHermes(ctx, { git: '/synthetic/git', run: git.run });
  const sparse = git.calls.findIndex(args => args.includes('sparse-checkout'));
  const checkout = git.calls.findIndex(args => args.includes('checkout'));
  assert.ok(sparse >= 0 && sparse < checkout);
  assert.deepEqual(git.calls[sparse].slice(2), ['sparse-checkout', 'set', '--no-cone', '/*', '!/contributors/emails/']);
  assert.ok(git.calls.some(args => args.includes('status') && args.includes('--untracked-files=no')));
  assert.equal(git.calls.flat().includes('--force'), false);
  assert.equal(git.calls.flat().includes('reset'), false);
});

test('Linux checkout does not omit attribution files', async t => {
  const ctx = await fixture(t); ctx.platform = 'linux';
  const git = await fakeGit(ctx);
  await checkoutHermes(ctx, { git: '/synthetic/git', run: git.run });
  assert.equal(git.calls.some(args => args.includes('sparse-checkout')), false);
});

test('modified runtime source still fails despite macOS attribution exclusion', async t => {
  const ctx = await fixture(t); ctx.platform = 'darwin';
  const git = await fakeGit(ctx, { changed: ' M hermes_cli/main.py\n' });
  await assert.rejects(checkoutHermes(ctx, { git: '/synthetic/git', run: git.run }), /tracked source was modified/);
});

test('sparse rules cannot silently omit runtime source', async t => {
  const ctx = await fixture(t); ctx.platform = 'darwin';
  const git = await fakeGit(ctx, { sparse: '/*\n!/hermes_cli/\n' });
  await assert.rejects(checkoutHermes(ctx, { git: '/synthetic/git', run: git.run }), /Unexpected Hermes sparse checkout/);
});

test('source or git symlinks fail before native execution', async t => {
  const ctx = await fixture(t), p = runtimePaths(ctx);
  await fs.mkdir(path.dirname(p.source), { recursive: true });
  await fs.symlink(ctx.projects, p.source, 'dir');
  let ran = false;
  await assert.rejects(checkoutHermes(ctx, { git: '/synthetic/git', run: async () => { ran = true; } }), /Unsafe managed runtime path/);
  assert.equal(ran, false);
});

test('RMUX installs the complete tiny/daemon/full layout without extracting arbitrary archive paths', async t => {
  const ctx = await fixture(t), archive = path.join(ctx.cache, 'rmux.tar.gz'), root = path.join(ctx.tools, 'rmux');
  for (const part of ['bin', 'libexec/rmux', 'share/rmux']) await fs.mkdir(path.join(root, part), { recursive: true });
  const build = "import io,sys,tarfile\nwith tarfile.open(sys.argv[1],'w:gz') as t:\n for name in ['bin/rmux','bin/rmux-daemon','libexec/rmux/rmux','../../escape','install.sh']:\n  b=name.encode(); m=tarfile.TarInfo('package/'+name); m.size=len(b); t.addfile(m,io.BytesIO(b))";
  execFileSync('/usr/bin/python3', ['-I', '-S', '-c', build, archive]);
  execFileSync('/usr/bin/python3', ['-I', '-S', '-c', RMUX_EXTRACTOR, archive, root, 'package']);
  for (const part of ['bin/rmux', 'bin/rmux-daemon', 'libexec/rmux/rmux']) assert.equal(await fs.readFile(path.join(root, part), 'utf8'), part);
  await assert.rejects(fs.lstat(path.join(ctx.root, 'escape')), { code: 'ENOENT' });
  await assert.rejects(fs.lstat(path.join(root, 'install.sh')), { code: 'ENOENT' });
  // Identical owned members resume without replacing executable identities.
  const before = await fs.stat(path.join(root, 'bin/rmux'));
  execFileSync('/usr/bin/python3', ['-I', '-S', '-c', RMUX_EXTRACTOR, archive, root, 'package']);
  assert.equal((await fs.stat(path.join(root, 'bin/rmux'))).ino, before.ino);
});

test('RMUX rejects duplicate/linked required members before publishing any executable', async t => {
  const ctx = await fixture(t), archive = path.join(ctx.cache, 'rmux.tar.gz'), root = path.join(ctx.tools, 'rmux');
  for (const part of ['bin', 'libexec/rmux', 'share/rmux']) await fs.mkdir(path.join(root, part), { recursive: true });
  const build = "import io,sys,tarfile\nwith tarfile.open(sys.argv[1],'w:gz') as t:\n for name in ['bin/rmux','bin/rmux-daemon','libexec/rmux/rmux','bin/rmux']:\n  m=tarfile.TarInfo('package/'+name); m.size=1; t.addfile(m,io.BytesIO(b'x'))";
  execFileSync('/usr/bin/python3', ['-I', '-S', '-c', build, archive]);
  assert.throws(() => execFileSync('/usr/bin/python3', ['-I', '-S', '-c', RMUX_EXTRACTOR, archive, root, 'package'], { stdio: 'pipe' }), /Command failed/);
  await assert.rejects(fs.lstat(path.join(root, 'bin/rmux')), { code: 'ENOENT' });
});

test('fresh profile receives only nonsecret OpenAI voice routes, without service or paid calls', async t => {
  const ctx = await fixture(t), p = runtimePaths(ctx), calls = [];
  const run = async (executable, args, options) => {
    calls.push({ executable, args, options });
    if (args[0] === 'profile') {
      await fs.mkdir(p.profile, { recursive: true });
      await fs.writeFile(path.join(p.profile, '.env'), '# empty native credential template\n', { mode: 0o644 });
    }
    return { code: 0, stdout: '', stderr: '' };
  };
  await createWorkstationProfile(ctx, { run });
  const settings = Object.fromEntries(calls.filter(call => call.args.includes('set')).map(call => call.args.slice(-2)));
  assert.equal(settings['stt.provider'], 'openai');
  assert.equal(settings['stt.openai.model'], pins.OPENAI_STT_MODEL);
  assert.equal(settings['tts.provider'], 'openai');
  assert.equal(settings['tts.openai.model'], pins.OPENAI_TTS_MODEL);
  assert.equal(settings['tts.openai.voice'], pins.OPENAI_TTS_VOICE);
  assert.equal(Object.keys(settings).some(key => /parakeet|auto_tts|token|api_key/.test(key)), false);
  assert.equal(calls.some(call => call.args.some(arg => ['gateway', 'start', 'transcribe', 'speak'].includes(arg))), false);
  assert.ok(calls.every(call => call.options.env.HOME === ctx.home));
  assert.equal((await fs.stat(path.join(p.profile, '.env'))).mode & 0o777, 0o600);
});

test('existing enrolled profile preserves settings and credentials without replaying voice defaults', async t => {
  const ctx = await fixture(t), p = runtimePaths(ctx);
  await fs.mkdir(p.profile, { recursive: true });
  const marker = path.join(p.profile, '.station-workstation-profile.json');
  await fs.writeFile(marker, JSON.stringify({ schema: 1, root: ctx.root, profile: ctx.profile }));
  await fs.writeFile(path.join(p.profile, 'config.yaml'), 'stt:\n  provider: local-custom\n');
  const before = await fs.readFile(path.join(p.profile, 'config.yaml'));
  let called = false;
  await createWorkstationProfile(ctx, { run: async () => { called = true; throw new Error('must not replay config'); } });
  assert.equal(called, false);
  assert.deepEqual(await fs.readFile(path.join(p.profile, 'config.yaml')), before);
});

test('required launcher check rejects stale SDK context even when native version probes pass', async t => {
  const ctx = await fixture(t), p = runtimePaths(ctx);
  await fs.mkdir(path.join(ctx.tools, 'rmux/bin'), { recursive: true });
  await fs.writeFile(path.join(ctx.tools, 'rmux/bin/rmux-daemon'), '#!/bin/sh\n', { mode: 0o700 });
  const expected = launcher(ctx, '/bin/bash', [path.join(p.agk, 'bin/agk')], { agk: true });
  const entry = `'RMUX_SDK_DAEMON_BINARY=${privateEnv(ctx).RMUX_SDK_DAEMON_BINARY}' `;
  await fs.writeFile(path.join(ctx.bin, 'agk'), expected.replace(entry, ''), { mode: 0o700 });
  const run = async () => ({ code: 0, stdout: '', stderr: '' });
  let checks = await verify(ctx, { run });
  assert.equal(checks.find(check => check.id === 'rmux:launcher-context').status, 'failed');
  assert.equal(checks.find(check => check.id === 'rmux:launcher-context').required, true);
  await fs.writeFile(path.join(ctx.bin, 'agk'), expected);
  checks = await verify(ctx, { run });
  assert.equal(checks.find(check => check.id === 'rmux:launcher-context').status, 'verified');
});
