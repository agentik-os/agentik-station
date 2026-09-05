// Workstation enrollment is deliberately separate from Hermes' gateway wizard:
// the pinned wizard can start services before enrollment has finished.
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { privateEnv } from './runtime.mjs';

const PROFILE = /^station-[a-f0-9]{12}$/;
const SNOWFLAKE = /^[1-9][0-9]{16,19}$/;
const MAX_FILE = 1024 * 1024;
const DISCORD_KEYS = new Set([
  'DISCORD_BOT_TOKEN', 'DISCORD_ALLOWED_USERS', 'DISCORD_ALLOWED_CHANNELS',
  'DISCORD_ALLOWED_ROLES', 'DISCORD_ALLOW_ALL_USERS', 'DISCORD_HOME_CHANNEL',
  'DISCORD_ALLOW_BOTS', 'GATEWAY_ALLOWED_USERS', 'GATEWAY_ALLOW_ALL_USERS',
  'DISCORD_AUTO_THREAD', 'DISCORD_REQUIRE_MENTION',
]);

// Display only: executable invocation always uses argv arrays through run().
function nextCommand(ctx, command) {
  return `agentik-station ${command} --root '${ctx.root.replaceAll("'", "'\\''")}'`;
}

function coordinates(ctx) {
  if (!PROFILE.test(ctx.profile || '')) throw new Error('A unique Station Workstation profile is required.');
  if (!['darwin', 'linux'].includes(ctx.platform)) throw new Error('Gateway activation supports macOS and Linux only.');
  for (const key of ['root', 'home', 'tools', 'bin', 'cache', 'hermesHome', 'accountHome']) {
    if (typeof ctx[key] !== 'string' || !path.isAbsolute(ctx[key]) || path.resolve(ctx[key]) !== ctx[key] || /[\x00-\x1f\x7f]/.test(ctx[key])) {
      throw new Error(`Invalid Workstation ${key} path.`);
    }
    if (!['root', 'accountHome'].includes(key) && !ctx[key].startsWith(`${ctx.root}${path.sep}`)) throw new Error(`Workstation ${key} escapes its root.`);
  }
  if (ctx.hermesHome !== path.join(ctx.home, '.hermes')) throw new Error('Unexpected Workstation Hermes namespace.');
  return {
    profileHome: path.join(ctx.hermesHome, 'profiles', ctx.profile),
    executable: path.join(ctx.tools, 'hermes', 'venv', 'bin', 'hermes'),
    python: path.join(ctx.tools, 'hermes', 'venv', 'bin', 'python'),
    source: path.join(ctx.tools, 'hermes', 'source'),
    label: `ai.hermes.gateway-${ctx.profile}`,
    unit: `hermes-gateway-${ctx.profile}.service`,
  };
}

// This is a same-UID namespace, not a sandbox against another process of that UID.
// Refuse substituted paths/special files; never repair an existing account tree.
async function directoryChain(target, { missing = false } = {}) {
  const parts = path.resolve(target).split(path.sep).filter(Boolean);
  let cursor = path.parse(target).root;
  let absent = false;
  for (const part of parts) {
    cursor = path.join(cursor, part);
    try {
      const stat = await fs.lstat(cursor);
      if (absent || !stat.isDirectory() || stat.isSymbolicLink()) throw new Error('Unsafe directory in gateway path.');
      if (stat.mode & 0o022 && !(stat.mode & 0o1000)) throw new Error('Gateway directory is writable by another identity.');
    } catch (error) {
      if (error.code !== 'ENOENT' || !missing) throw error;
      absent = true;
    }
  }
}

async function regular(target, { optional = false, secret = false } = {}) {
  await directoryChain(path.dirname(target));
  let handle;
  try {
    handle = await fs.open(target, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size > MAX_FILE || stat.uid !== process.getuid() || (stat.mode & 0o022) || (secret && stat.mode & 0o077)) {
      throw new Error('Unsafe gateway file: expected an owned, bounded, private regular file.');
    }
    return { text: await handle.readFile('utf8'), stat };
  } catch (error) {
    if (optional && error.code === 'ENOENT') return null;
    throw error;
  } finally { await handle?.close(); }
}

async function writeAtomic(target, text, prior = null) {
  await directoryChain(path.dirname(target));
  const temp = path.join(path.dirname(target), `.station-gateway-${randomBytes(12).toString('hex')}`);
  const handle = await fs.open(temp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try {
    await handle.writeFile(text, 'utf8');
    await handle.sync();
  } finally { await handle.close(); }
  try {
    if (prior) {
      const now = await fs.lstat(target);
      if (!now.isFile() || now.nlink !== 1 || now.ino !== prior.stat.ino || now.dev !== prior.stat.dev || now.mtimeMs !== prior.stat.mtimeMs) throw new Error('Gateway configuration changed during enrollment; review and retry.');
      await fs.rename(temp, target);
    } else {
      // link is an exclusive publish: unlike rename, it cannot replace a collision.
      await fs.link(temp, target);
    }
  } finally { await fs.unlink(temp).catch(() => {}); }
}

export function gatewayEnvironment(ctx, { profile = false, service = false } = {}) {
  const c = coordinates(ctx);
  const env = privateEnv(ctx, {
    HERMES_HOME: profile ? c.profileHome : ctx.hermesHome,
    XDG_STATE_HOME: path.join(ctx.home, '.local', 'state'),
  });
  if (!service && ctx.platform === 'linux') {
    env.XDG_RUNTIME_DIR = `/run/user/${process.getuid()}`;
    env.DBUS_SESSION_BUS_ADDRESS = `unix:path=${env.XDG_RUNTIME_DIR}/bus`;
  }
  return env;
}

function needInteractive(interactive) {
  if (!interactive || typeof interactive.prompt !== 'function' || typeof interactive.confirm !== 'function') throw new Error('Use an interactive terminal for private enrollment and activation. Tokens are never accepted as command arguments.');
  return interactive;
}

function numeric(value, label) {
  const clean = String(value ?? '').trim();
  if (!SNOWFLAKE.test(clean)) throw new Error(`${label} must be a numeric Discord ID (enable Developer Mode to copy it).`);
  return clean;
}

function users(value) {
  const result = [...new Set(String(value ?? '').split(',').map(item => numeric(item, 'Authorized user')))];
  if (!result.length || result.length > 32) throw new Error('Choose between one and 32 explicit human users.');
  return result;
}

function dotenvValues(text) {
  const result = {};
  for (const line of text.split(/\r?\n/)) {
    const match = /^(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$/.exec(line.trim());
    if (!match || !DISCORD_KEYS.has(match[1])) continue;
    if (Object.hasOwn(result, match[1])) throw new Error('Duplicate Discord policy keys need explicit repair before enrollment.');
    const raw = match[2].trim();
    result[match[1]] = /^(['"]).*\1$/.test(raw) ? raw.slice(1, -1) : raw;
  }
  return result;
}

function updatedEnv(text, values) {
  dotenvValues(text); // fail closed on ambiguous managed policy
  const lines = text.split(/\r?\n/).filter(line => {
    const match = /^(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=/.exec(line.trim());
    return !match || !DISCORD_KEYS.has(match[1]);
  });
  return `${lines.join('\n').trimEnd()}\n${Object.entries(values).map(([key, value]) => `${key}=${value}`).join('\n')}\n`;
}

const CONFIG_SCRIPT = String.raw`
import json, os, sys, yaml
filename = sys.argv[1]
with open(filename, encoding="utf-8") as handle:
    value = yaml.safe_load(handle) or {}
if not isinstance(value, dict):
    raise ValueError("profile config must be a mapping")
if len(sys.argv) == 3:
    binding = json.loads(sys.argv[2])
    discord = value.setdefault("discord", {})
    if not isinstance(discord, dict):
        raise ValueError("discord config must be a mapping")
    discord.update(allow_from=binding["users"], allowed_roles=[],
                   allowed_channels=[binding["channel"]], allow_all_users=False,
                   allow_bots="none", require_mention=True, auto_thread=False)
    # Native Discord uses allow_from, not an invented allowed_users alias.
    discord.pop("allowed_users", None)
    print(yaml.safe_dump(value, sort_keys=False))
else:
    discord = value.get("discord") or {}
    if not isinstance(discord, dict):
        raise ValueError("discord config must be a mapping")
    print(json.dumps({"discord": {key: discord.get(key) for key in
        ("allow_from", "allowed_roles", "allowed_channels", "allow_all_users", "allow_bots", "require_mention", "auto_thread")},
        "model_declared": bool(value.get("model"))}))
`;

async function inspectConfig(ctx, run) {
  const c = coordinates(ctx);
  await directoryChain(c.profileHome);
  const envFile = await regular(path.join(c.profileHome, '.env'), { optional: true, secret: true });
  const configFile = await regular(path.join(c.profileHome, 'config.yaml'), { optional: true });
  const bindingFile = await regular(path.join(c.profileHome, 'station-discord.json'), { optional: true, secret: true });
  if (!envFile || !configFile || !bindingFile) return { configured: false, detail: `Run ${nextCommand(ctx, 'discord')} in a terminal; no account or service was tested.` };
  let binding;
  try { binding = JSON.parse(bindingFile.text); } catch { throw new Error('Invalid private Discord enrollment record; inspect and repair it.'); }
  numeric(binding.application, 'Application');
  numeric(binding.guild, 'Server');
  numeric(binding.channel, 'Channel');
  const allowed = users(Array.isArray(binding.users) ? binding.users.join(',') : '');
  const env = dotenvValues(envFile.text);
  const expected = {
    DISCORD_ALLOWED_USERS: allowed.join(','), DISCORD_ALLOWED_CHANNELS: binding.channel,
    DISCORD_HOME_CHANNEL: binding.channel, DISCORD_ALLOWED_ROLES: '',
    DISCORD_ALLOW_ALL_USERS: 'false', DISCORD_ALLOW_BOTS: 'none',
    DISCORD_AUTO_THREAD: 'false', DISCORD_REQUIRE_MENTION: 'true',
    GATEWAY_ALLOWED_USERS: '', GATEWAY_ALLOW_ALL_USERS: 'false',
  };
  if (!/^[A-Za-z0-9._-]{20,512}$/.test(env.DISCORD_BOT_TOKEN || '') || Object.entries(expected).some(([key, value]) => env[key] !== value)) {
    return { configured: false, detail: `Discord token or explicit human/channel restrictions are missing or changed; rerun ${nextCommand(ctx, 'discord')}.` };
  }
  const response = await run(c.python, ['-I', '-c', CONFIG_SCRIPT, path.join(c.profileHome, 'config.yaml')], { cwd: ctx.root, env: gatewayEnvironment(ctx), timeoutMs: 15000 });
  let config;
  try { config = JSON.parse(response.stdout); } catch { throw new Error('Could not safely read the native Hermes configuration.'); }
  const discord = config.discord;
  if (!discord || JSON.stringify(discord.allow_from) !== JSON.stringify(allowed) || JSON.stringify(discord.allowed_channels) !== JSON.stringify([binding.channel]) || JSON.stringify(discord.allowed_roles) !== '[]' || discord.allow_all_users !== false || discord.allow_bots !== 'none' || discord.require_mention !== true || discord.auto_thread !== false) {
    return { configured: false, detail: `Native Discord configuration differs from the prepared human/channel policy; rerun ${nextCommand(ctx, 'discord')}.` };
  }
  return { configured: true, modelDeclared: config.model_declared === true, detail: 'Private token and explicit numeric human/channel policy prepared; account validity and live Discord routing are not verified.' };
}

async function configure(ctx, run, interactive) {
  const io = needInteractive(interactive);
  const c = coordinates(ctx);
  await directoryChain(c.profileHome);
  const envPath = path.join(c.profileHome, '.env');
  const configPath = path.join(c.profileHome, 'config.yaml');
  const bindingPath = path.join(c.profileHome, 'station-discord.json');
  const previousEnv = await regular(envPath, { optional: true, secret: true });
  const previousConfig = await regular(configPath);
  const previousBinding = await regular(bindingPath, { optional: true, secret: true });
  if ((await probeService(ctx, run)).loaded) throw new Error('Stop this namespaced gateway service explicitly before changing enrollment; a prepared file cannot update its in-memory authorization.');
  if (!await io.confirm({ message: 'Configure only this private Station Discord profile? This does not start a bot, create a server, grant sudo, or change your personal Hermes.' })) return { action: 'configure', status: 'cancelled', checks: [] };
  const application = numeric(await io.prompt({ message: 'Discord Application ID — create your bot at https://discord.com/developers/applications' }), 'Application');
  const guild = numeric(await io.prompt({ message: 'Discord Server ID (Developer Mode → Copy Server ID)' }), 'Server');
  const channel = numeric(await io.prompt({ message: 'Private command channel ID (Copy Channel ID)' }), 'Channel');
  const allowed = users(await io.prompt({ message: 'Authorized HUMAN user IDs, separated by commas — never a role name or *' }));
  const token = String(await io.prompt({ message: 'Bot token (masked; stored only in this private profile)', secret: true }) ?? '').trim();
  if (!/^[A-Za-z0-9._-]{20,512}$/.test(token)) throw new Error('Invalid bot-token format; no configuration was changed.');
  const binding = { schema: 1, application, guild, channel, users: allowed };
  const inviteUrl = `https://discord.com/oauth2/authorize?client_id=${application}&scope=bot%20applications.commands&permissions=117824&guild_id=${guild}&disable_guild_select=true`;
  if (!await io.confirm({ message: `Enable Message Content Intent in the Developer Portal and review this text-only invite (no Administrator):\n${inviteUrl}\nHave you reviewed the bot, server, channel, human IDs and permissions? The guild ID targets the invite; native channel restrictions apply to guild messages, while authorized humans may also DM. Voice requires separate Connect/Speak approval.` })) return { action: 'configure', status: 'cancelled', checks: [], inviteUrl };
  const patched = await run(c.python, ['-I', '-c', CONFIG_SCRIPT, configPath, JSON.stringify(binding)], { cwd: ctx.root, env: gatewayEnvironment(ctx), timeoutMs: 15000 });
  if (!patched.stdout || Buffer.byteLength(patched.stdout) > MAX_FILE) throw new Error('Native configuration preparation failed; no token was written.');
  const envText = updatedEnv(previousEnv?.text || '', {
    DISCORD_BOT_TOKEN: token, DISCORD_ALLOWED_USERS: allowed.join(','),
    DISCORD_ALLOWED_CHANNELS: channel, DISCORD_HOME_CHANNEL: channel,
    DISCORD_ALLOWED_ROLES: '', DISCORD_ALLOW_ALL_USERS: 'false', DISCORD_ALLOW_BOTS: 'none',
    DISCORD_AUTO_THREAD: 'false', DISCORD_REQUIRE_MENTION: 'true',
    GATEWAY_ALLOWED_USERS: '', GATEWAY_ALLOW_ALL_USERS: 'false',
  });
  // Policy first, token last; a partial attempt is never reported as configured.
  await writeAtomic(configPath, patched.stdout, previousConfig);
  await writeAtomic(bindingPath, `${JSON.stringify(binding, null, 2)}\n`, previousBinding);
  await writeAtomic(envPath, envText, previousEnv);
  return {
    action: 'configure', status: 'prepared', inviteUrl,
    checks: [{ id: 'discord-policy', status: 'verified', detail: 'Private token saved with explicit human and channel restrictions. No credential was sent to Discord.' }, { id: 'discord-live', status: 'not-configured', detail: 'Invitation, token validity, permissions, wrong-user/wrong-channel rejection and a live reply still require acceptance.' }],
    next: ['model', 'verify', 'activate'].map(command => nextCommand(ctx, command)),
  };
}

function servicePaths(ctx) {
  const c = coordinates(ctx);
  return ctx.platform === 'darwin'
    ? { ...c, target: path.join(ctx.accountHome, 'Library', 'LaunchAgents', `${c.label}.plist`) }
    : { ...c, target: path.join(ctx.home, '.config', 'systemd', 'user', c.unit), accountUnit: path.join(ctx.accountHome, '.config', 'systemd', 'user', c.unit) };
}

function managerEnvironment(ctx) {
  // systemctl's client-side link/enable operation must use the account's real
  // configuration directory; only the Hermes child receives the private HOME.
  const env = gatewayEnvironment(ctx);
  if (ctx.platform === 'linux') {
    env.HOME = ctx.accountHome;
    env.XDG_CONFIG_HOME = path.join(ctx.accountHome, '.config');
  }
  return env;
}

async function probeService(ctx, run) {
  const c = servicePaths(ctx);
  const options = { cwd: ctx.root, env: managerEnvironment(ctx), allowFailure: true, timeoutMs: 15000 };
  if (ctx.platform === 'darwin') {
    for (const domain of [`gui/${process.getuid()}`, `user/${process.getuid()}`]) {
      const probe = await run('/bin/launchctl', ['print', `${domain}/${c.label}`], options);
      if (probe.code === 0) return { loaded: true, running: /\bstate\s*=\s*running\b/.test(probe.stdout) && /\bpid\s*=\s*[1-9][0-9]*\b/.test(probe.stdout), domain };
    }
    return { loaded: false, running: false };
  }
  const probe = await run('/usr/bin/systemctl', ['--user', 'show', c.unit, '--property=LoadState,ActiveState,MainPID'], options);
  return { loaded: probe.code === 0 && /^LoadState=loaded$/m.test(probe.stdout), running: probe.code === 0 && /^ActiveState=active$/m.test(probe.stdout) && /^MainPID=[1-9][0-9]*$/m.test(probe.stdout) };
}

// Use the pinned native generator, then scope the service process itself. Native
// user units/plists omit HOME; a clean install-time env alone is not sufficient.
const GENERATE_SCRIPT = String.raw`
import json, os, plistlib, sys
sys.path.insert(0, sys.argv[1])
from hermes_cli.gateway import generate_launchd_plist, generate_systemd_unit
if sys.argv[2] == "darwin":
    value = plistlib.loads(generate_launchd_plist().encode())
    print(json.dumps(value))
else:
    print(json.dumps({"unit": generate_systemd_unit()}))
`;

function systemdQuote(value) {
  return `"${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"').replaceAll('%', '%%').replaceAll('$', '$$')}"`;
}

export async function prepareGatewayService(ctx, { run } = {}) {
  const c = coordinates(ctx);
  await directoryChain(c.profileHome);
  await regular(path.join(c.profileHome, 'config.yaml'));
  await regular(path.join(c.profileHome, '.env'), { optional: true, secret: true });
  const response = await run(c.python, ['-I', '-c', GENERATE_SCRIPT, c.source, ctx.platform], { cwd: ctx.root, env: gatewayEnvironment(ctx, { profile: true }), timeoutMs: 30000 });
  let generated;
  try { generated = JSON.parse(response.stdout); } catch { throw new Error('Pinned Hermes did not produce a valid service definition.'); }
  const privateEnv = gatewayEnvironment(ctx, { profile: true, service: true });
  privateEnv.HERMES_SUPERVISED_CHILD = '1';
  const prefix = ['/usr/bin/env', '-i', ...Object.entries(privateEnv).map(([key, value]) => `${key}=${value}`)];
  if (ctx.platform === 'darwin') {
    if (generated.Label !== c.label || !Array.isArray(generated.ProgramArguments) || !generated.ProgramArguments.includes('gateway') || !generated.ProgramArguments.includes('run') || generated.EnvironmentVariables?.HERMES_HOME !== c.profileHome) throw new Error('Unexpected native launchd profile binding.');
    generated.ProgramArguments = [...prefix, ...generated.ProgramArguments];
    generated.EnvironmentVariables = privateEnv;
    generated.WorkingDirectory = c.profileHome;
    const xml = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
    const encode = value => {
      if (typeof value === 'boolean') return value ? '<true/>' : '<false/>';
      if (Number.isSafeInteger(value)) return `<integer>${value}</integer>`;
      if (typeof value === 'string') return `<string>${xml(value)}</string>`;
      if (Array.isArray(value)) return `<array>${value.map(encode).join('')}</array>`;
      if (value && typeof value === 'object') return `<dict>${Object.entries(value).map(([key, item]) => `<key>${xml(key)}</key>${encode(item)}`).join('')}</dict>`;
      throw new Error('Unsupported native launchd value.');
    };
    return `<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">${encode(generated)}</plist>\n`;
  }
  if (typeof generated.unit !== 'string' || !generated.unit.includes('[Service]') || !generated.unit.includes(`HERMES_HOME=${c.profileHome}`) || !generated.unit.includes(`--profile ${ctx.profile}`)) throw new Error('Unexpected native systemd profile binding.');
  const command = [...prefix, c.python, '-m', 'hermes_cli.main', '--profile', ctx.profile, 'gateway', 'run'].map(systemdQuote).join(' ');
  const cleanup = [...prefix, c.python, '-m', 'gateway.cgroup_cleanup'].map(systemdQuote).join(' ');
  return generated.unit.replace(/^ExecStart=.*$/m, `ExecStart=${command}`)
    .replace(/^ExecStopPost=.*$/m, `ExecStopPost=-${cleanup}`)
    .replace(/^WorkingDirectory=.*$/m, `WorkingDirectory=${systemdQuote(c.profileHome)}`)
    .replace(/^Environment=.*\r?\n/gm, '');
}

async function assertAbsent(target) {
  await directoryChain(path.dirname(target), { missing: true });
  try { await fs.lstat(target); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
  throw new Error('A gateway unit/plist already occupies this name. Preserve it and review its ownership; activation never replaces or restarts it.');
}

async function activate(ctx, run, interactive) {
  const io = needInteractive(interactive);
  const c = servicePaths(ctx);
  const state = await inspectConfig(ctx, run);
  if (!state.configured || !state.modelDeclared) throw new Error(`Activation blocked: ${state.configured ? `run ${nextCommand(ctx, 'model')} and verify the selected provider first.` : state.detail}`);
  await assertAbsent(c.target);
  if (c.accountUnit && c.accountUnit !== c.target) await assertAbsent(c.accountUnit);
  if ((await probeService(ctx, run)).loaded) throw new Error('A service already uses this Station profile. Activation will not replace or restart it.');
  const doctor = await run(c.executable, ['--profile', ctx.profile, 'doctor'], { cwd: ctx.root, env: gatewayEnvironment(ctx), timeoutMs: 60000, allowFailure: true });
  if (doctor.code !== 0) throw new Error('Hermes Doctor failed. Repair this private profile before activating a gateway; no service was started.');
  const definition = await prepareGatewayService(ctx, { run });
  const disclosure = ctx.platform === 'darwin'
    ? `Create ${c.target} and load this one launchd service now? macOS installation immediately starts it and enables login restart.`
    : `Create ${c.target}, link/enable it in your account systemd configuration, and start this one user service now? No sudo or linger changes are made; logout persistence is not guaranteed.`;
  if (!await io.confirm({ message: `${disclosure}\nThe gateway connects to Discord and model providers; incoming approved messages may incur charges and use tools with your Unix account authority. This is not a sudo or filesystem sandbox.` })) return { action: 'activate', status: 'cancelled', checks: [] };
  // Recheck after the human review, before any service write.
  await assertAbsent(c.target);
  if (c.accountUnit && c.accountUnit !== c.target) await assertAbsent(c.accountUnit);
  if ((await probeService(ctx, run)).loaded) throw new Error('The service name became occupied during review; nothing was replaced.');
  await fs.mkdir(path.dirname(c.target), { recursive: true, mode: 0o700 });
  await directoryChain(path.dirname(c.target));
  await writeAtomic(c.target, definition);
  const options = { cwd: ctx.root, env: managerEnvironment(ctx), timeoutMs: 30000 };
  if (ctx.platform === 'darwin') {
    // Choose an available native domain, never silently fall back to a detached process.
    let domain;
    for (const candidate of [`gui/${process.getuid()}`, `user/${process.getuid()}`]) {
      const result = await run('/bin/launchctl', ['print', candidate], { ...options, allowFailure: true });
      if (result.code === 0) { domain = candidate; break; }
    }
    if (!domain) throw new Error('No launchd user domain is available. The prepared plist is preserved; inspect it before explicit repair.');
    await run('/bin/launchctl', ['bootstrap', domain, c.target], options);
  } else {
    await run('/usr/bin/systemctl', ['--user', 'link', c.target], options);
    await run('/usr/bin/systemctl', ['--user', 'daemon-reload'], options);
    await run('/usr/bin/systemctl', ['--user', 'enable', c.unit], options);
    await run('/usr/bin/systemctl', ['--user', 'start', c.unit], options);
  }
  let observed = await probeService(ctx, run);
  for (let attempt = 0; !observed.running && attempt < 7; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 250));
    observed = await probeService(ctx, run);
  }
  return {
    action: 'activate', status: observed.running ? 'observed' : 'failed',
    checks: [{ id: 'gateway-process', status: observed.running ? 'verified' : 'failed', detail: observed.running ? 'The exact namespaced service is running; live account/routing acceptance is still pending.' : 'Activation was attempted but a running process was not observed. Preserve the service definition and inspect scoped logs before repair.' }, { id: 'discord-live', status: 'not-configured', detail: 'Test an approved message, a wrong user, a wrong channel, and a reply before operational acceptance.' }],
  };
}

export async function gateway(ctx, action, { run, interactive = false } = {}) {
  if (typeof run !== 'function') throw new Error('A bounded, environment-cleared command runner is required.');
  const c = coordinates(ctx);
  await directoryChain(ctx.root);
  if (action === 'configure') return configure(ctx, run, interactive);
  if (action === 'activate') return activate(ctx, run, interactive);
  if (action === 'model') {
    needInteractive(interactive);
    await directoryChain(c.profileHome);
    await regular(path.join(c.profileHome, '.env'), { optional: true, secret: true });
    await regular(path.join(c.profileHome, 'config.yaml'));
    if ((await probeService(ctx, run)).loaded) throw new Error('Stop this namespaced gateway service explicitly before changing model enrollment.');
    await run(c.executable, ['--profile', ctx.profile, 'setup', 'model'], { cwd: ctx.root, env: gatewayEnvironment(ctx), timeoutMs: 1800000, interactive: true });
    return { action, status: 'prepared', checks: [{ id: 'model-enrollment', status: 'not-configured', detail: 'Native model-only wizard completed; account scope, billing and a live model response remain unverified.' }], next: ['discord', 'verify', 'activate'].map(command => nextCommand(ctx, command)) };
  }
  if (action === 'status') {
    const config = await inspectConfig(ctx, run);
    const observed = await probeService(ctx, run);
    return { action, status: observed.running ? 'observed' : 'not-configured', checks: [
      { id: 'discord-policy', status: config.configured ? 'verified' : 'not-configured', detail: config.detail },
      { id: 'gateway-process', status: observed.running ? 'verified' : 'not-configured', detail: observed.running ? 'Namespaced gateway process observed, not live Discord acceptance.' : 'No running namespaced gateway observed; no service was changed.' },
      { id: 'discord-live', status: 'not-configured', detail: 'Account, guild/channel permissions, authorization rejection and a live reply have not been accepted.' },
    ] };
  }
  throw new Error('Unknown gateway action: use model, configure, status, or activate.');
}
