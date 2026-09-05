import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { gateway, gatewayEnvironment } from '../gateway.mjs';

const IDS = { application: '111111111111111111', guild: '222222222222222222', channel: '333333333333333333', users: ['444444444444444444'] };
const TOKEN = 'synthetic.not-a-real-token.123456789';

async function fixture(t, platform = 'darwin') {
  const parent = await fs.realpath(os.tmpdir());
  const scratch = await fs.mkdtemp(path.join(parent, 'station gateway tests '));
  t.after(() => fs.rm(scratch, { recursive: true, force: true }));
  const root = path.join(scratch, 'station');
  const ctx = { root, sourceRoot: root, home: path.join(root, 'personal', 'home'), tools: path.join(root, 'tools'), bin: path.join(root, 'bin'), cache: path.join(root, 'cache'), evidence: path.join(root, 'evidence'), resources: path.join(root, 'resources'), projects: path.join(root, 'projects'), profile: 'station-0123456789ab', platform, arch: 'arm64', accountHome: path.join(scratch, 'account') };
  ctx.hermesHome = path.join(ctx.home, '.hermes');
  const profileHome = path.join(ctx.hermesHome, 'profiles', ctx.profile);
  for (const directory of [profileHome, ctx.accountHome, ctx.tools, ctx.bin, ctx.cache]) await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  await fs.writeFile(path.join(profileHome, 'config.yaml'), 'model: synthetic\n', { mode: 0o600 });
  return { ctx, scratch, profileHome };
}

function configOutput(overrides = {}) {
  return { discord: { allow_from: IDS.users, allowed_roles: [], allowed_channels: [IDS.channel], allow_all_users: false, allow_bots: 'none', require_mention: true, auto_thread: false }, model_declared: true, ...overrides };
}

async function enrolled(profileHome) {
  await fs.writeFile(path.join(profileHome, '.env'), `DISCORD_BOT_TOKEN=${TOKEN}\nDISCORD_ALLOWED_USERS=${IDS.users.join(',')}\nDISCORD_ALLOWED_CHANNELS=${IDS.channel}\nDISCORD_HOME_CHANNEL=${IDS.channel}\nDISCORD_ALLOWED_ROLES=\nDISCORD_ALLOW_ALL_USERS=false\nDISCORD_ALLOW_BOTS=none\nDISCORD_AUTO_THREAD=false\nDISCORD_REQUIRE_MENTION=true\nGATEWAY_ALLOWED_USERS=\nGATEWAY_ALLOW_ALL_USERS=false\n`, { mode: 0o600 });
  await fs.writeFile(path.join(profileHome, 'station-discord.json'), JSON.stringify({ schema: 1, ...IDS }), { mode: 0o600 });
}

function interactive({ answers = [IDS.application, IDS.guild, IDS.channel, IDS.users.join(','), TOKEN], confirmed = true } = {}) {
  const prompts = [];
  return { prompts, prompt: async options => { prompts.push(options); return answers.shift(); }, confirm: async options => { prompts.push(options); return confirmed; } };
}

function mocked(ctx, options = {}) {
  const calls = [];
  let started = false;
  const profileHome = path.join(ctx.hermesHome, 'profiles', ctx.profile);
  const run = async (executable, argv, execution) => {
    calls.push({ executable, argv, options: execution });
    if (argv.includes('-c')) {
      const script = argv[argv.indexOf('-c') + 1];
      if (script.includes('generate_launchd_plist')) {
        const payload = ctx.platform === 'darwin'
          ? { Label: `ai.hermes.gateway-${ctx.profile}`, ProgramArguments: [path.join(ctx.tools, 'hermes', 'venv', 'bin', 'python'), '-m', 'hermes_cli.main', '--profile', ctx.profile, 'gateway', 'run'], EnvironmentVariables: { HERMES_HOME: profileHome, PATH: '/untrusted/inherited' }, WorkingDirectory: profileHome, RunAtLoad: true, KeepAlive: true }
          : { unit: `[Unit]\nDescription=Hermes\n[Service]\nExecStart=/unquoted path/python -m hermes_cli.main --profile ${ctx.profile} gateway run\nWorkingDirectory=${profileHome}\nEnvironment="HERMES_HOME=${profileHome}"\nEnvironment="PATH=/untrusted/inherited"\nExecStopPost=-/unquoted path/python -m gateway.cgroup_cleanup\n[Install]\nWantedBy=default.target\n` };
        return { code: 0, stdout: JSON.stringify(options.generated || payload), stderr: '' };
      }
      return { code: 0, stdout: argv.length === 5 ? 'model: synthetic\ndiscord: {}\n' : JSON.stringify(options.config || configOutput()), stderr: '' };
    }
    if (argv.includes('doctor')) return { code: options.doctorCode || 0, stdout: '', stderr: '' };
    if (argv.includes('bootstrap') || argv.includes('start')) {
      if (options.startFailure) throw new Error('Synthetic startup failure');
      started = true;
      return { code: 0, stdout: '', stderr: '' };
    }
    if (executable === '/bin/launchctl' && argv[0] === 'print') {
      if (argv[1].split('/').length === 2) return { code: 0, stdout: 'domain exists', stderr: '' };
      return started || options.loaded ? { code: 0, stdout: 'state = running\npid = 123', stderr: '' } : { code: 113, stdout: '', stderr: '' };
    }
    if (executable === '/usr/bin/systemctl' && argv.includes('show')) return started || options.loaded ? { code: 0, stdout: 'LoadState=loaded\nActiveState=active\nMainPID=123\n', stderr: '' } : { code: 0, stdout: 'LoadState=not-found\nActiveState=inactive\nMainPID=0\n', stderr: '' };
    return { code: 0, stdout: '', stderr: '' };
  };
  return { run, calls };
}

test('configuration enrolls only the private profile, never invokes the activating native wizard', async t => {
  const { ctx, profileHome } = await fixture(t);
  const io = interactive();
  const runner = mocked(ctx);
  const result = await gateway(ctx, 'configure', { ...runner, interactive: io });
  assert.equal(result.status, 'prepared');
  assert.equal(result.checks.find(item => item.id === 'discord-live').status, 'not-configured');
  assert.match(result.inviteUrl, /permissions=117824&guild_id=/);
  assert.equal(io.prompts.find(item => item.secret).message.includes('masked'), true);
  const env = await fs.readFile(path.join(profileHome, '.env'), 'utf8');
  assert.ok(env.includes(TOKEN));
  assert.equal((await fs.stat(path.join(profileHome, '.env'))).mode & 0o777, 0o600);
  assert.equal(JSON.stringify(runner.calls).includes(TOKEN), false);
  assert.equal(JSON.stringify(result).includes(TOKEN), false);
  assert.equal(runner.calls.some(call => call.argv.includes('gateway') || call.argv.includes('install')), false);
});

test('model setup is profile-specific and model-only, with no inherited account environment', async t => {
  const { ctx } = await fixture(t);
  const runner = mocked(ctx);
  await gateway(ctx, 'model', { ...runner, interactive: interactive() });
  const model = runner.calls.find(call => call.argv.includes('setup'));
  assert.deepEqual(model.argv, ['--profile', ctx.profile, 'setup', 'model']);
  assert.equal(model.options.env.HOME, ctx.home);
  assert.equal(model.options.env.HERMES_HOME, ctx.hermesHome);
  assert.equal(model.options.interactive, true);
  assert.equal(Object.hasOwn(model.options.env, 'OPENAI_API_KEY'), false);
});

test('all credential and activation actions require a private interactive flow', async t => {
  const { ctx } = await fixture(t);
  for (const action of ['configure', 'model', 'activate']) await assert.rejects(gateway(ctx, action, mocked(ctx)), /interactive terminal/);
});

test('wildcard users and newline token input fail before any mutation', async t => {
  const { ctx, profileHome } = await fixture(t);
  for (const answers of [[IDS.application, IDS.guild, IDS.channel, '*', TOKEN], [IDS.application, IDS.guild, IDS.channel, IDS.users.join(','), `${TOKEN}\nEVIL=value`]]) {
    await assert.rejects(gateway(ctx, 'configure', { ...mocked(ctx), interactive: interactive({ answers }) }), /numeric Discord ID|Invalid bot-token/);
  }
  await assert.rejects(fs.access(path.join(profileHome, '.env')), { code: 'ENOENT' });
});

test('token replacement preserves unrelated enrollment without exporting it', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  await fs.appendFile(path.join(profileHome, '.env'), 'OPENAI_API_KEY=synthetic-private-provider-key\n');
  const runner = mocked(ctx);
  const result = await gateway(ctx, 'configure', { ...runner, interactive: interactive() });
  assert.match(await fs.readFile(path.join(profileHome, '.env'), 'utf8'), /OPENAI_API_KEY=synthetic-private-provider-key/);
  assert.equal(JSON.stringify({ calls: runner.calls, result }).includes('synthetic-private-provider-key'), false);
});

test('symlinked private credential destination is refused without following it', async t => {
  const { ctx, profileHome, scratch } = await fixture(t);
  const outside = path.join(scratch, 'outside');
  await fs.writeFile(outside, 'do not read or change', { mode: 0o600 });
  await fs.symlink(outside, path.join(profileHome, '.env'));
  await assert.rejects(gateway(ctx, 'configure', { ...mocked(ctx), interactive: interactive() }));
  assert.equal(await fs.readFile(outside, 'utf8'), 'do not read or change');
});

test('symlinked profile ancestor is refused', async t => {
  const { ctx, profileHome, scratch } = await fixture(t);
  const moved = path.join(scratch, 'moved-profile');
  await fs.rename(profileHome, moved);
  await fs.symlink(moved, profileHome);
  await assert.rejects(gateway(ctx, 'model', { ...mocked(ctx), interactive: interactive() }), /Unsafe directory/);
});

test('hardlinked or world-readable credential files are refused, not chmod-repaired', async t => {
  const { ctx, profileHome, scratch } = await fixture(t);
  const filename = path.join(profileHome, '.env');
  await fs.writeFile(filename, 'synthetic', { mode: 0o644 });
  await assert.rejects(gateway(ctx, 'configure', { ...mocked(ctx), interactive: interactive() }), /Unsafe gateway file/);
  await fs.chmod(filename, 0o600);
  await fs.link(filename, path.join(scratch, 'credential-alias'));
  await assert.rejects(gateway(ctx, 'configure', { ...mocked(ctx), interactive: interactive() }), /Unsafe gateway file/);
});

test('a FIFO at the credential path is refused without a blocking read', { timeout: 5000 }, async t => {
  const { ctx, profileHome } = await fixture(t);
  execFileSync('/usr/bin/mkfifo', [path.join(profileHome, '.env')]);
  await assert.rejects(gateway(ctx, 'configure', { ...mocked(ctx), interactive: interactive() }), /Unsafe gateway file/);
});

test('a duplicate managed policy key refuses ambiguous dotenv repair', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  await fs.appendFile(path.join(profileHome, '.env'), 'DISCORD_ALLOWED_USERS=*\n');
  const before = await fs.readFile(path.join(profileHome, '.env'), 'utf8');
  await assert.rejects(gateway(ctx, 'configure', { ...mocked(ctx), interactive: interactive() }), /Duplicate Discord policy/);
  assert.equal(await fs.readFile(path.join(profileHome, '.env'), 'utf8'), before);
});

test('an unnamespaced profile or escaping root fails before execution', async t => {
  const { ctx } = await fixture(t);
  const runner = mocked(ctx);
  await assert.rejects(gateway({ ...ctx, profile: 'default' }, 'status', runner), /unique Station/);
  await assert.rejects(gateway({ ...ctx, hermesHome: '/elsewhere' }, 'status', runner), /escapes/);
  assert.equal(runner.calls.length, 0);
});

test('a missing model declaration or altered channel gate blocks activation', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  for (const config of [configOutput({ model_declared: false }), configOutput({ discord: { ...configOutput().discord, allowed_channels: ['*'] } })]) {
    const runner = mocked(ctx, { config });
    await assert.rejects(gateway(ctx, 'activate', { ...runner, interactive: interactive() }), /Activation blocked/);
    assert.equal(runner.calls.some(call => call.argv.includes('bootstrap')), false);
  }
});

test('Doctor failure blocks service generation and activation', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const runner = mocked(ctx, { doctorCode: 1 });
  await assert.rejects(gateway(ctx, 'activate', { ...runner, interactive: interactive() }), /Doctor failed/);
  assert.equal(runner.calls.some(call => call.argv.includes('bootstrap') || call.argv.includes('start')), false);
});

test('existing launchd file or dangling symlink is never replaced', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const filename = path.join(ctx.accountHome, 'Library', 'LaunchAgents', `ai.hermes.gateway-${ctx.profile}.plist`);
  await fs.mkdir(path.dirname(filename), { recursive: true, mode: 0o700 });
  await fs.symlink('/nonexistent-synthetic-target', filename);
  const runner = mocked(ctx);
  await assert.rejects(gateway(ctx, 'activate', { ...runner, interactive: interactive() }), /already occupies/);
  assert.equal(runner.calls.some(call => call.executable === '/bin/launchctl'), false);
});

test('already loaded service without a file still prevents activation', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const runner = mocked(ctx, { loaded: true });
  await assert.rejects(gateway(ctx, 'activate', { ...runner, interactive: interactive() }), /already uses/);
  assert.equal(runner.calls.some(call => call.argv.includes('bootstrap')), false);
});

test('enrollment refuses to rewrite a loaded service policy without an explicit stop', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const before = await fs.readFile(path.join(profileHome, '.env'), 'utf8');
  for (const action of ['configure', 'model']) await assert.rejects(gateway(ctx, action, { ...mocked(ctx, { loaded: true }), interactive: interactive() }), /Stop this namespaced/);
  assert.equal(await fs.readFile(path.join(profileHome, '.env'), 'utf8'), before);
});

test('declining activation performs no external file write or start', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const runner = mocked(ctx);
  const result = await gateway(ctx, 'activate', { ...runner, interactive: interactive({ confirmed: false }) });
  assert.equal(result.status, 'cancelled');
  await assert.rejects(fs.access(path.join(ctx.accountHome, 'Library')), { code: 'ENOENT' });
  assert.equal(runner.calls.some(call => call.argv.includes('bootstrap')), false);
});

test('a service collision introduced during human confirmation is preserved', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const filename = path.join(ctx.accountHome, 'Library', 'LaunchAgents', `ai.hermes.gateway-${ctx.profile}.plist`);
  const io = interactive();
  io.confirm = async () => {
    await fs.mkdir(path.dirname(filename), { recursive: true, mode: 0o700 });
    await fs.writeFile(filename, 'appeared-during-human-review', { mode: 0o600 });
    return true;
  };
  await assert.rejects(gateway(ctx, 'activate', { ...mocked(ctx), interactive: io }), /already occupies/);
  assert.equal(await fs.readFile(filename, 'utf8'), 'appeared-during-human-review');
});

test('macOS activation uses a scoped native definition and clears the daemon environment', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const runner = mocked(ctx);
  const result = await gateway(ctx, 'activate', { ...runner, interactive: interactive() });
  assert.equal(result.status, 'observed');
  const filename = path.join(ctx.accountHome, 'Library', 'LaunchAgents', `ai.hermes.gateway-${ctx.profile}.plist`);
  const body = await fs.readFile(filename, 'utf8');
  assert.match(body, /<string>\/usr\/bin\/env<\/string><string>-i<\/string>/);
  assert.ok(body.includes(`<string>HOME=${ctx.home}</string>`));
  assert.ok(body.includes(`<string>HERMES_HOME=${profileHome}</string>`));
  assert.ok(body.includes(`<string>ai.hermes.gateway-${ctx.profile}</string>`));
  assert.equal(body.includes('/untrusted/inherited'), false);
  assert.equal(body.includes(TOKEN), false);
  const start = runner.calls.find(call => call.argv.includes('bootstrap'));
  assert.deepEqual(start.argv, ['bootstrap', `gui/${process.getuid()}`, filename]);
  assert.equal(runner.calls.some(call => call.argv.includes('install')), false);
  assert.equal(result.checks.find(item => item.id === 'discord-live').status, 'not-configured');
});

test('Linux uses real user-manager config but private child HOME and quotes paths with spaces', async t => {
  const { ctx, profileHome } = await fixture(t, 'linux');
  await enrolled(profileHome);
  const runner = mocked(ctx);
  const result = await gateway(ctx, 'activate', { ...runner, interactive: interactive() });
  assert.equal(result.status, 'observed');
  const filename = path.join(ctx.home, '.config', 'systemd', 'user', `hermes-gateway-${ctx.profile}.service`);
  const body = await fs.readFile(filename, 'utf8');
  assert.match(body, /ExecStart="\/usr\/bin\/env" "-i"/);
  assert.ok(body.includes(`"HOME=${ctx.home}"`));
  assert.ok(body.includes(`"${path.join(ctx.tools, 'hermes', 'venv', 'bin', 'python')}"`));
  assert.equal(body.includes('/unquoted path'), false);
  assert.equal(body.includes('/untrusted/inherited'), false);
  const link = runner.calls.find(call => call.argv.includes('link'));
  assert.equal(link.options.env.HOME, ctx.accountHome);
  assert.equal(link.options.env.XDG_CONFIG_HOME, path.join(ctx.accountHome, '.config'));
  assert.deepEqual(link.argv, ['--user', 'link', filename]);
  assert.equal(runner.calls.some(call => call.executable.includes('sudo') || call.executable.includes('loginctl')), false);
});

test('Linux rejects an existing real-account unit even when private unit is absent', async t => {
  const { ctx, profileHome } = await fixture(t, 'linux');
  await enrolled(profileHome);
  const filename = path.join(ctx.accountHome, '.config', 'systemd', 'user', `hermes-gateway-${ctx.profile}.service`);
  await fs.mkdir(path.dirname(filename), { recursive: true, mode: 0o700 });
  await fs.writeFile(filename, 'unrelated-existing-unit', { mode: 0o600 });
  await assert.rejects(gateway(ctx, 'activate', { ...mocked(ctx), interactive: interactive() }), /already occupies/);
  assert.equal(await fs.readFile(filename, 'utf8'), 'unrelated-existing-unit');
});

test('failed activation retains the prepared definition for explicit repair', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const runner = mocked(ctx, { startFailure: true });
  await assert.rejects(gateway(ctx, 'activate', { ...runner, interactive: interactive() }), /Synthetic startup failure/);
  const filename = path.join(ctx.accountHome, 'Library', 'LaunchAgents', `ai.hermes.gateway-${ctx.profile}.plist`);
  assert.ok((await fs.stat(filename)).isFile());
});

test('status separates local configuration, process observation, and live acceptance', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const runner = mocked(ctx, { loaded: true });
  const result = await gateway(ctx, 'status', runner);
  assert.equal(result.status, 'observed');
  assert.equal(result.checks.find(check => check.id === 'discord-live').status, 'not-configured');
  assert.equal(JSON.stringify(result).includes(TOKEN), false);
  assert.equal(runner.calls.some(call => call.argv.includes('start') || call.argv.includes('install')), false);
});

test('native generated profile mismatch fails closed', async t => {
  const { ctx, profileHome } = await fixture(t);
  await enrolled(profileHome);
  const runner = mocked(ctx, { generated: { Label: 'ai.hermes.gateway', ProgramArguments: ['hermes', 'gateway', 'run'] } });
  await assert.rejects(gateway(ctx, 'activate', { ...runner, interactive: interactive() }), /Unexpected native launchd/);
  assert.equal(runner.calls.some(call => call.argv.includes('bootstrap')), false);
});

test('the service environment never inherits parent credentials', async t => {
  const { ctx } = await fixture(t);
  process.env.STATION_GATEWAY_TEST_SECRET = 'never-forward-this';
  try {
    const env = gatewayEnvironment(ctx, { profile: true, service: true });
    assert.equal(env.STATION_GATEWAY_TEST_SECRET, undefined);
    assert.equal(env.HOME, ctx.home);
    assert.equal(env.HERMES_HOME, path.join(ctx.hermesHome, 'profiles', ctx.profile));
  } finally { delete process.env.STATION_GATEWAY_TEST_SECRET; }
});
