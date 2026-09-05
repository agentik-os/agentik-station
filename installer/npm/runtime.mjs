/** Personal Workstation runtime. Never invokes a Host bootstrap or sudo. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { provisionWeb, verifyWeb } from './web.mjs';
import { provisionConnectors, verifyConnectors } from './connectors.mjs';

const RMUX_HASHES = Object.freeze({
  'darwin-arm64': 'aac857519071f680be53aa9a328dc0cd04c2abe66ec726f78aa9e26337c5ef7b',
  'darwin-x64': 'b897898eadc4d96c6d555b79affd834bd488013c44f8c6f815bb5195eafd1e0a',
  'linux-arm64': '7e916560ea0fb90864b8c24e5d0f81b4e3e0b013b8aad5ab53839d7e8e5e1926',
  'linux-x64': '1bec11eff08c3313c3a400196e7a93d00b8ad4a24f81ef13debb03355c2696c5',
});
const CLI_PACKAGES = [
  ['vercel', 'VERCEL_CLI_VERSION', 'VERCEL_CLI_INTEGRITY', 'vercel'],
  ['@openai/codex', 'CODEX_CLI_VERSION', 'CODEX_CLI_INTEGRITY', 'codex'],
  ['shadcn', 'SHADCN_CLI_VERSION', 'SHADCN_CLI_INTEGRITY', 'shadcn'],
  ['chatbotx', 'CHATBOTX_CLI_VERSION', 'CHATBOTX_CLI_NPM_INTEGRITY', 'chatbotx'],
  ['discord.js', 'DISCORD_JS_VERSION', 'DISCORD_JS_INTEGRITY', null],
];
const EXCLUDED = new Set(['.git', 'node_modules', 'target', '__pycache__', '.pytest_cache', '.DS_Store']);
// Pinned attribution emails contain case-only aliases that cannot coexist on
// the default macOS filesystem. No runtime source is omitted or ignored.
const MACOS_SPARSE_RULES = '/*\n!/contributors/emails/\n';
export const RMUX_EXTRACTOR = String.raw`
import os, pathlib, stat, sys, tarfile, uuid
archive, root, package = sys.argv[1:]
required = {'bin/rmux', 'bin/rmux-daemon', 'libexec/rmux/rmux'}
allowed = required | {'LICENSE', 'LICENSE-MIT', 'LICENSE-APACHE', 'share/rmux/artifact-metadata.json'}
selected = {}
with tarfile.open(archive) as bundle:
    for member in bundle.getmembers():
        prefix = package + '/'
        if not member.name.startswith(prefix):
            continue
        relative = member.name[len(prefix):]
        if relative not in allowed:
            continue
        if relative in selected or not member.isfile() or not 0 < member.size < 100_000_000:
            raise ValueError('Invalid or duplicate RMUX archive member')
        selected[relative] = bundle.extractfile(member).read()
if not required <= selected.keys():
    raise ValueError('Incomplete RMUX tiny/daemon/full executable layout')
for relative, content in selected.items():
    target = pathlib.Path(root) / relative
    if target.exists() or target.is_symlink():
        meta = target.lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or target.read_bytes() != content:
            raise ValueError('Changed RMUX member; explicit review required')
        continue
    temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700 if relative in required else 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, target)
    finally:
        temporary.unlink()
`;
const shellQuote = value => `'${String(value).replaceAll("'", "'\\''")}'`;

export function runtimePaths(ctx) {
  return {
    source: path.join(ctx.tools, 'hermes/source'),
    venv: path.join(ctx.tools, 'hermes/venv'),
    hermes: path.join(ctx.tools, 'hermes/venv/bin/hermes'),
    python: path.join(ctx.tools, 'hermes/venv/bin/python'),
    agk: path.join(ctx.tools, 'agk-terminal'),
    rmux: path.join(ctx.tools, 'rmux/bin/rmux'),
    npm: path.join(ctx.resources, 'cli'),
    profile: path.join(ctx.hermesHome, 'profiles', ctx.profile),
  };
}

/** No inherited token, SSH agent, npm auth, Python path or provider variables. */
export function privateEnv(ctx, additions = {}) {
  const p = runtimePaths(ctx);
  return {
    HOME: ctx.home, USER: 'station-workstation', LOGNAME: 'station-workstation',
    PATH: [ctx.bin, path.join(p.agk, 'venv/bin'), path.dirname(process.execPath), '/usr/bin', '/bin', '/usr/sbin', '/sbin'].join(':'),
    HERMES_HOME: ctx.hermesHome, HERMES_MANAGED_DIR: path.join(ctx.cache, 'hermes-managed'),
    XDG_CONFIG_HOME: path.join(ctx.home, '.config'), XDG_CACHE_HOME: ctx.cache,
    XDG_DATA_HOME: path.join(ctx.home, '.local/share'), TMPDIR: path.join(ctx.cache, 'tmp'),
    UV_CACHE_DIR: path.join(ctx.cache, 'uv'), UV_PYTHON_INSTALL_DIR: path.join(ctx.tools, 'python'),
    CARGO_HOME: path.join(ctx.cache, 'cargo'), CARGO_TARGET_DIR: path.join(ctx.cache, 'cargo-target'),
    npm_config_cache: path.join(ctx.cache, 'npm'), npm_config_userconfig: path.join(ctx.home, '.npmrc'),
    npm_config_globalconfig: path.join(ctx.home, '.npm-globalrc'),
    GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null', GIT_TERMINAL_PROMPT: '0',
    PYTHONDONTWRITEBYTECODE: '1', PYTHONNOUSERSITE: '1',
    AGK_TERMINAL_ROOT: p.agk, AGK_ENVIRONMENT: 'private',
    AGENTIK_ENVIRONMENT: 'private', STATION_WORKSTATION_ROOT: ctx.root,
    AGK_ENV_CONFIG: path.join(ctx.home, '.config/agk/environment.yaml'),
    AGK_AGENT_CATALOG: path.join(p.profile, 'agents'),
    AGK_RULES_CONFIG: path.join(p.agk, 'config/rules.yaml'),
    AGK_TOPOLOGY_CONFIG: path.join(p.agk, 'config/topology.yaml'),
    AGK_OS_REGISTRY: path.join(ctx.resources, 'os-registry'),
    RMUX_TMPDIR: path.join(ctx.cache, 'rmux'),
    // rmux-sdk starts its hidden daemon with --__internal-daemon as argv[1].
    // The public -S wrapper is not that entrypoint; bind the reviewed raw daemon.
    RMUX_SDK_DAEMON_BINARY: path.join(ctx.tools, 'rmux/bin/rmux-daemon'),
    LANG: 'en_US.UTF-8', LC_ALL: 'en_US.UTF-8', TERM: 'xterm-256color',
    ...additions,
  };
}

async function info(target) {
  try { return await fs.lstat(target); } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}

async function ownedPath(ctx, target) {
  const relative = path.relative(ctx.root, target);
  if (!relative || relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new Error('Runtime path escapes Workstation root');
  let current = ctx.root;
  for (const part of ['', ...relative.split(path.sep)]) {
    current = path.join(current, part);
    const st = await info(current);
    if (st && (st.isSymbolicLink() || (!st.isFile() && !st.isDirectory()) || st.nlink > 1 && st.isFile())) throw new Error(`Unsafe managed runtime path: ${current}`);
  }
}

async function directory(ctx, target) {
  await ownedPath(ctx, target);
  await fs.mkdir(target, { recursive: true, mode: 0o700 });
}

async function writeOwned(ctx, target, bytes, mode = 0o600) {
  await ownedPath(ctx, target);
  await directory(ctx, path.dirname(target));
  const prior = await info(target);
  if (prior) {
    if (!prior.isFile() || !Buffer.from(await fs.readFile(target)).equals(Buffer.from(bytes))) throw new Error(`Changed existing managed software; inspect before repair: ${target}`);
    return;
  }
  const temporary = `${target}.${crypto.randomUUID()}.tmp`;
  const handle = await fs.open(temporary, 'wx', mode);
  try { await handle.writeFile(bytes); await handle.sync(); } finally { await handle.close(); }
  try { await fs.link(temporary, target); } finally { await fs.unlink(temporary); }
}

async function copyTree(ctx, source, destination) {
  const st = await fs.lstat(source);
  if (st.isSymbolicLink() || !st.isDirectory() && !st.isFile() || st.isFile() && st.nlink > 1) throw new Error(`Unsafe packaged source: ${source}`);
  if (st.isDirectory()) {
    await directory(ctx, destination);
    for (const name of await fs.readdir(source)) if (!EXCLUDED.has(name)) await copyTree(ctx, path.join(source, name), path.join(destination, name));
  } else await writeOwned(ctx, destination, await fs.readFile(source), st.mode & 0o111 ? 0o700 : 0o600);
}

async function executable(name, search = process.env.PATH || '') {
  for (const base of search.split(path.delimiter).filter(item => path.isAbsolute(item))) {
    const candidate = path.join(base, name);
    try {
      await fs.access(candidate, fs.constants.X_OK);
      const resolved = await fs.realpath(candidate);
      if ((await fs.stat(resolved)).isFile()) return candidate;
    } catch { /* next explicitly discovered tool */ }
  }
  return null;
}

export async function prerequisites(ctx, { run } = {}) {
  const found = {};
  const checks = [];
  for (const name of ['uv', 'git', 'cargo', 'curl', 'npm']) {
    found[name] = await executable(name);
    checks.push({ id: `prerequisite:${name}`, status: found[name] ? 'verified' : 'blocked', detail: found[name] ? `Available build prerequisite: ${found[name]}` : `Install ${name} with your platform package manager, then rerun the reviewed plan; Station does not sudo or edit your shell.` });
  }
  // Rustup proxies need their existing toolchain, not a new one downloaded into
  // a personal account. Resolve it read-only, then build with private Cargo HOME.
  if (found.cargo && run && path.basename(await fs.realpath(found.cargo)) === 'rustup') {
    const rustup = await executable('rustup');
    if (rustup) {
      const result = await run(rustup, ['which', 'cargo'], { env: { HOME: ctx.accountHome, PATH: '/usr/bin:/bin', RUSTUP_AUTO_INSTALL: '0' }, allowFailure: true });
      const resolved = result.stdout.trim();
      if (result.code === 0 && path.isAbsolute(resolved) && (await info(resolved))?.isFile()) found.cargo = resolved;
      else checks.push({ id: 'prerequisite:rust-toolchain', status: 'blocked', detail: 'Existing Rust toolchain could not be resolved without installing into your account.' });
    }
  }
  if (!RMUX_HASHES[`${ctx.platform}-${ctx.arch}`]) checks.push({ id: 'platform', status: 'blocked', detail: 'Workstation supports native macOS/Linux x64 and arm64 only.' });
  if (Buffer.byteLength(path.join(ctx.cache, 'rmux', `rmux-${process.getuid?.() ?? 0}`, 'default')) >= 100) checks.push({ id: 'rmux:socket-path', status: 'blocked', detail: 'Choose a shorter Workstation root; native Unix socket paths must fit within 100 bytes.' });
  return { found, checks };
}

export function launcher(ctx, executablePath, argv = [], { hermes = false, agk = false, privateFiles = false } = {}) {
  const env = privateEnv(ctx, agk ? { HERMES_HOME: runtimePaths(ctx).profile } : {});
  const entries = Object.entries(env).filter(([key]) => key !== 'TERM').map(([key, value]) => shellQuote(`${key}=${value}`));
  return `#!/bin/sh\n# Station personal Workstation; same Unix user, not a Zone sandbox.\n${privateFiles ? 'umask 077\n' : ''}exec /usr/bin/env -i ${entries.join(' ')} "TERM=\${TERM:-xterm-256color}" ${shellQuote(executablePath)} ${[...(hermes ? ['--profile', ctx.profile] : []), ...argv].map(shellQuote).join(' ')} "$@"\n`;
}

async function installHermes(ctx, found, run) {
  const p = runtimePaths(ctx), env = privateEnv(ctx);
  await checkoutHermes(ctx, { git: found.git, run, env });
  await run(found.uv, ['sync', '--frozen', '--no-dev', '--extra', 'voice', '--extra', 'messaging', '--extra', 'mcp', '--python', ctx.pins.HERMES_PYTHON_VERSION], {
    cwd: p.source, env: { ...env, UV_PROJECT_ENVIRONMENT: p.venv }, timeoutMs: 1200000,
  });
  await createWorkstationProfile(ctx, { run, env });
  await writeOwned(ctx, path.join(ctx.bin, 'hermes'), launcher(ctx, p.hermes, [], { hermes: true }), 0o700);
}

/** Seed nonsecret routes only when creating this new native profile. */
export async function createWorkstationProfile(ctx, { run, env = privateEnv(ctx) }) {
  const p = runtimePaths(ctx);
  const marker = path.join(p.profile, '.station-workstation-profile.json');
  if (!await info(p.profile)) {
    await run(p.hermes, ['profile', 'create', ctx.profile, '--no-alias'], { env, cwd: ctx.projects, timeoutMs: 120000 });
    for (const [key, value] of [
      ['runtime_identity.environment_id', 'private'],
      ['stt.enabled', 'true'], ['stt.provider', 'openai'],
      ['stt.openai.model', ctx.pins.OPENAI_STT_MODEL],
      ['tts.provider', 'openai'], ['tts.openai.model', ctx.pins.OPENAI_TTS_MODEL],
      ['tts.openai.voice', ctx.pins.OPENAI_TTS_VOICE],
    ]) {
      if (typeof value !== 'string' || !value) throw new Error('Missing reviewed nonsecret profile default');
      await run(p.hermes, ['--profile', ctx.profile, 'config', 'set', key, value], { env });
    }
    const secretFile = path.join(p.profile, '.env');
    await ownedPath(ctx, secretFile);
    if ((await info(secretFile))?.isFile()) await fs.chmod(secretFile, 0o600);
    await writeOwned(ctx, marker, JSON.stringify({ schema: 1, root: ctx.root, profile: ctx.profile }) + '\n');
  } else {
    await ownedPath(ctx, marker);
    const record = JSON.parse(await fs.readFile(marker, 'utf8'));
    if (record.root !== ctx.root || record.profile !== ctx.profile) throw new Error('Existing Hermes profile is not the enrolled Workstation profile');
  }
}

/** Testable source boundary; no force checkout/reset or widened sparse ignore. */
export async function checkoutHermes(ctx, { git, run, env = privateEnv(ctx) }) {
  const p = runtimePaths(ctx);
  if (!/^[a-f0-9]{40}$/.test(ctx.pins.HERMES_COMMIT) || ctx.pins.HERMES_REPOSITORY !== 'NousResearch/hermes-agent') throw new Error('Invalid reviewed Hermes source pin');
  await directory(ctx, p.source);
  await ownedPath(ctx, path.join(p.source, '.git'));
  if (!await info(path.join(p.source, '.git'))) {
    if ((await fs.readdir(p.source)).length) throw new Error('Refusing unmanaged Hermes source directory');
    await run(git, ['init', p.source], { env });
    await run(git, ['-C', p.source, 'remote', 'add', 'origin', 'https://github.com/NousResearch/hermes-agent.git'], { env });
    await run(git, ['-C', p.source, 'fetch', '--depth=1', 'origin', ctx.pins.HERMES_COMMIT], { env, timeoutMs: 600000 });
    if (ctx.platform === 'darwin') await run(git, ['-C', p.source, 'sparse-checkout', 'set', '--no-cone', '/*', '!/contributors/emails/'], { env });
    await run(git, ['-C', p.source, 'checkout', '--detach', ctx.pins.HERMES_COMMIT], { env });
  }
  const revision = await run(git, ['-C', p.source, 'rev-parse', 'HEAD'], { env });
  if (revision.stdout.trim() !== ctx.pins.HERMES_COMMIT) throw new Error('Hermes checkout does not match the reviewed commit; no reset performed');
  const changed = await run(git, ['-C', p.source, 'status', '--porcelain', '--untracked-files=no'], { env });
  if (changed.stdout.trim()) throw new Error('Hermes tracked source was modified; review before repair');
  if (ctx.platform === 'darwin' && await fs.readFile(path.join(p.source, '.git/info/sparse-checkout'), 'utf8') !== MACOS_SPARSE_RULES) throw new Error('Unexpected Hermes sparse checkout; only case-colliding attribution emails may be excluded');
}

async function installRMUX(ctx, found, run) {
  const p = runtimePaths(ctx), env = privateEnv(ctx);
  const version = ctx.pins.RMUX_VERSION;
  if (version !== '0.10.0') throw new Error('RMUX release changed; review portable artifact hashes before installation');
  if (!(await info(p.rmux) && await info(path.join(ctx.tools, 'rmux/bin/rmux-daemon')) && await info(path.join(ctx.tools, 'rmux/libexec/rmux/rmux')))) {
    const archive = `rmux-${version}-${ctx.platform === 'darwin' ? 'macos' : 'linux'}-${ctx.arch === 'arm64' ? 'aarch64' : 'x86_64'}.tar.gz`;
    const download = path.join(ctx.cache, archive);
    await ownedPath(ctx, download);
    await run(found.curl, ['--proto', '=https', '--tlsv1.2', '--fail', '--silent', '--show-error', '--location', '--max-time', '180', '--output', download, `https://github.com/Helvesec/rmux/releases/download/v${version}/${archive}`], { env, timeoutMs: 200000 });
    const actual = crypto.createHash('sha256').update(await fs.readFile(download)).digest('hex');
    if (actual !== RMUX_HASHES[`${ctx.platform}-${ctx.arch}`]) throw new Error('RMUX archive checksum mismatch; downloaded evidence preserved');
    for (const child of ['bin', 'libexec/rmux', 'share/rmux']) await directory(ctx, path.join(ctx.tools, 'rmux', child));
    // Preserve upstream tiny/daemon/full layout, not merely the two identically
    // named clients. Only exact regular members; never extract archive paths,
    // symlinks, install.sh or daemon-repair logic. Download hash is reviewed above.
    await run(p.python, ['-I', '-S', '-c', RMUX_EXTRACTOR, download, path.join(ctx.tools, 'rmux'), archive.slice(0, -7)], { env });
  }
  const result = await run(p.rmux, ['-V'], { env });
  if (result.stdout.trim() !== `rmux ${version}`) throw new Error('Installed RMUX version differs from reviewed pin');
  const socket = path.join(ctx.cache, 'rmux', `rmux-${process.getuid()}`, 'default');
  await writeOwned(ctx, path.join(ctx.bin, 'rmux'), launcher(ctx, p.rmux, ['-S', socket]), 0o700);
}

async function installAGK(ctx, found, run) {
  const p = runtimePaths(ctx), env = privateEnv(ctx);
  await copyTree(ctx, path.join(ctx.sourceRoot, 'components/agk-tui'), p.agk);
  await run(found.uv, ['venv', '--allow-existing', '--python', ctx.pins.HERMES_PYTHON_VERSION, path.join(p.agk, 'venv')], { env, timeoutMs: 180000 });
  await run(found.uv, ['pip', 'install', '--python', path.join(p.agk, 'venv/bin/python'), '-r', path.join(p.agk, 'requirements.txt')], { env, timeoutMs: 300000 });
  await run(found.cargo, ['build', '--locked', '--release', '--manifest-path', path.join(p.agk, 'apps/agk-tui/Cargo.toml')], {
    env: { ...env, PATH: `${path.dirname(found.cargo)}:${env.PATH}` }, timeoutMs: 1200000,
  });
  await writeOwned(ctx, path.join(p.agk, 'bin/agk-tui'), await fs.readFile(path.join(ctx.cache, 'cargo-target/release/agk-tui')), 0o700);
  const socket = path.join(ctx.cache, 'rmux', `rmux-${process.getuid()}`, 'default');
  await writeOwned(ctx, path.join(p.agk, 'bin/rmux'), launcher(ctx, p.rmux, ['-S', socket]), 0o700);
  for (const name of ['agk', 'agk-terminal']) await writeOwned(ctx, path.join(ctx.bin, name), launcher(ctx, '/bin/bash', [path.join(p.agk, 'bin', name)], { agk: true }), 0o700);
  const config = path.join(ctx.home, '.config/agk/environment.yaml');
  if (!await info(config)) await writeOwned(ctx, config, `environment: private\nprojects_root: ${JSON.stringify(ctx.projects)}\n`);
  await directory(ctx, path.join(ctx.home, '.config/rmux'));
  if (!await info(path.join(ctx.home, '.config/rmux/rmux.conf'))) await writeOwned(ctx, path.join(ctx.home, '.config/rmux/rmux.conf'), await fs.readFile(path.join(p.agk, 'rmux/rmux.conf')));
  // Install complete reviewed plugin/theme/agent sources in our fresh profile;
  // never call legacy sync-hermes.sh (it overwrites existing plugin/config state).
  for (const name of ['agentik_os', 'platforms/discord']) {
    const destination = path.join(p.profile, 'plugins', name);
    await copyTree(ctx, path.join(p.agk, 'hermes/plugins', name), destination);
    await run(p.hermes, ['--profile', ctx.profile, 'plugins', 'doctor', '--ci', destination], { env, timeoutMs: 120000 });
  }
  await copyTree(ctx, path.join(p.agk, 'hermes/dashboard-themes'), path.join(p.profile, 'dashboard-themes'));
  await copyTree(ctx, path.join(p.agk, 'hermes/agents'), path.join(p.profile, 'agents'));
  if (!ctx.preserveEnrollment) for (const name of ['agentik-os', 'platforms/discord']) await run(p.hermes, ['--profile', ctx.profile, 'plugins', 'enable', '--no-allow-tool-override', name], { env });
  // This projection stays wholly in Workstation HOME, never the user's providers.
  if (!ctx.preserveEnrollment) await run(path.join(p.agk, 'venv/bin/python'), [path.join(p.agk, 'scripts/sync-rules.py')], { env });
}

export async function installCLIs(ctx, found, run) {
  const p = runtimePaths(ctx), env = privateEnv(ctx);
  const dependencies = Object.fromEntries(CLI_PACKAGES.map(([name, version]) => [name, ctx.pins[version]]));
  await writeOwned(ctx, path.join(p.npm, 'package.json'), JSON.stringify({ name: 'station-workstation-tools', version: '1.0.0', private: true, dependencies }, null, 2) + '\n');
  await run(found.npm, ['install', '--ignore-scripts', '--no-audit', '--no-fund', '--prefix', p.npm], { env, cwd: p.npm, timeoutMs: 600000 });
  const lock = JSON.parse(await fs.readFile(path.join(p.npm, 'package-lock.json'), 'utf8'));
  for (const [name, version, integrity, bin] of CLI_PACKAGES) {
    const entry = lock.packages?.[`node_modules/${name}`];
    if (entry?.version !== ctx.pins[version] || entry?.integrity !== ctx.pins[integrity]) throw new Error(`Installed npm package does not match reviewed integrity: ${name}`);
    if (bin) {
      const directory = path.join(p.npm, 'node_modules', name);
      const manifest = JSON.parse(await fs.readFile(path.join(directory, 'package.json'), 'utf8'));
      const script = typeof manifest.bin === 'string' ? manifest.bin : manifest.bin?.[bin];
      if (typeof script !== 'string' || !script || path.isAbsolute(script) || script.split('/').includes('..')) throw new Error(`Invalid npm executable path: ${name}`);
      if (bin === 'chatbotx') {
        if (script !== './dist/index.cjs') throw new Error('Unexpected ChatbotX entrypoint');
        await verifyChatbotXEntry(ctx, path.join(directory, script));
      }
      await writeOwned(ctx, path.join(ctx.bin, bin), launcher(ctx, process.execPath, [path.join(directory, script)], { privateFiles: bin === 'chatbotx' }), 0o700);
    }
  }
  await copyTree(ctx, path.join(ctx.sourceRoot, 'resources/chatbotx'), path.join(ctx.resources, 'chatbotx'));
}

async function verifyChatbotXEntry(ctx, script) {
  await ownedPath(ctx, script);
  const stat = await fs.lstat(script);
  if (!stat.isFile() || stat.nlink !== 1 || stat.size > 1024 * 1024
    || crypto.createHash('sha256').update(await fs.readFile(script)).digest('hex') !== ctx.pins.CHATBOTX_CLI_ENTRY_SHA256) {
    throw new Error('ChatbotX executable does not match reviewed package bytes');
  }
}

/** ChatbotX's configured --version fetches a schema and reports an old version.
 * Verify the actual entrypoint with a fresh HOME, never the enrolled account.
 * The published entrypoint has no shebang; managed launchers invoke Node.
 */
export async function verifyChatbotX(ctx, { run }) {
  const p = runtimePaths(ctx), id = 'cli:chatbotx';
  let probeHome;
  try {
    const manifestPath = path.join(p.npm, 'node_modules/chatbotx/package.json');
    const script = path.join(p.npm, 'node_modules/chatbotx/dist/index.cjs');
    const wrapper = path.join(ctx.bin, 'chatbotx');
    for (const target of [manifestPath, script, wrapper, path.join(p.npm, 'package-lock.json')]) await ownedPath(ctx, target);
    const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
    const lock = JSON.parse(await fs.readFile(path.join(p.npm, 'package-lock.json'), 'utf8'));
    const record = lock.packages?.['node_modules/chatbotx'];
    if (manifest.version !== ctx.pins.CHATBOTX_CLI_VERSION || manifest.bin?.chatbotx !== './dist/index.cjs'
      || record?.version !== ctx.pins.CHATBOTX_CLI_VERSION || record?.integrity !== ctx.pins.CHATBOTX_CLI_NPM_INTEGRITY
      || await fs.readFile(wrapper, 'utf8') !== launcher(ctx, process.execPath, [path.join(p.npm, 'node_modules/chatbotx', manifest.bin.chatbotx)], { privateFiles: true })
      || !((await fs.stat(wrapper)).mode & 0o100)) throw new Error('ChatbotX package or launcher mismatch');
    await verifyChatbotXEntry(ctx, script);
    for (const name of ['RESOURCE.json', 'README.md', 'hermes-mcp.example.yaml', 'LICENSE.upstream']) {
      const target = path.join(ctx.resources, 'chatbotx', name);
      await ownedPath(ctx, target);
      if (!(await fs.readFile(target)).equals(await fs.readFile(path.join(ctx.sourceRoot, 'resources/chatbotx', name)))) throw new Error('ChatbotX resource is missing or changed');
    }
    await directory(ctx, ctx.cache);
    probeHome = await fs.mkdtemp(path.join(ctx.cache, 'chatbotx-probe-'));
    const env = {
      HOME: probeHome, PATH: `${path.dirname(process.execPath)}:/usr/bin:/bin`,
      XDG_CONFIG_HOME: probeHome, XDG_CACHE_HOME: probeHome, XDG_DATA_HOME: probeHome,
      NO_COLOR: '1', CI: 'true', LANG: 'C.UTF-8',
    };
    const version = await run(process.execPath, [script, '--version'], { env, cwd: probeHome, timeoutMs: 30000, allowFailure: true });
    const help = await run(process.execPath, [script, '--help'], { env, cwd: probeHome, timeoutMs: 30000, allowFailure: true });
    if (version.code !== 0 || version.stdout.trim() !== ctx.pins.CHATBOTX_CLI_VERSION || help.code !== 0 || !/config/i.test(help.stdout)) throw new Error('ChatbotX native probe failed');
    return { id, status: 'verified', required: true, detail: 'Pinned CLI and Node launcher verified with fresh private HOME; no account, MCP connection or hosted application acceptance.' };
  } catch {
    return { id, status: 'failed', required: true, detail: 'ChatbotX package, private Node launcher or account-free native probe failed; inspect explicit repair.' };
  } finally {
    if (probeHome) await fs.rm(probeHome, { recursive: true, force: true });
  }
}

export async function provision(ctx, { run, emit = () => {} }) {
  const prerequisite = await prerequisites(ctx, { run });
  if (prerequisite.checks.some(check => check.status === 'blocked')) return prerequisite.checks;
  for (const dir of [ctx.bin, ctx.tools, ctx.resources, ctx.projects, ctx.hermesHome, ctx.cache, path.join(ctx.cache, 'tmp'), path.join(ctx.cache, 'rmux')]) await directory(ctx, dir);
  for (const [id, install] of [['hermes', installHermes], ['rmux', installRMUX], ['agk', installAGK], ['tool-resources', installCLIs]]) {
    emit({ phase: id, status: 'running', message: `Installing reviewed ${id} software in Workstation` });
    try { await install(ctx, prerequisite.found, run); }
    catch (error) {
      emit({ phase: id, status: 'failed', message: `${id} failed; preserve this tree and inspect the receipt before explicit repair` });
      throw error;
    }
    emit({ phase: id, status: 'prepared', message: `${id} installed; local verification follows, accounts are not enrolled` });
  }
  await provisionConnectors(ctx, { run, emit, found: prerequisite.found });
  await provisionWeb(ctx, { run, emit, uv: prerequisite.found.uv, env: privateEnv(ctx) });
  return { checks: prerequisite.checks };
}

export async function verify(ctx, { run, emit = () => {} }) {
  const p = runtimePaths(ctx), env = privateEnv(ctx), checks = [];
  async function probe(id, bin, argv, expected, options = {}) {
    try {
      const result = await run(bin, argv, { env, cwd: ctx.projects, timeoutMs: 120000, allowFailure: true, ...options });
      const okay = result.code === 0 && (!expected || expected(`${result.stdout}\n${result.stderr}`));
      checks.push({ id, status: okay ? 'verified' : 'failed', required: true, detail: okay ? 'Native local check passed; no external account or live service claim' : 'Native local check failed; inspect or explicitly repair owned software' });
    } catch { checks.push({ id, status: 'failed', required: true, detail: 'Native executable unavailable; run explicit Workstation repair' }); }
    emit({ phase: 'verify', status: checks.at(-1).status, message: id });
  }
  const git = await executable('git');
  await probe('hermes:revision', git || '/usr/bin/git', ['-C', p.source, 'rev-parse', 'HEAD'], value => value.trim() === ctx.pins.HERMES_COMMIT);
  await probe('hermes:tracked-source', git || '/usr/bin/git', ['-C', p.source, 'status', '--porcelain', '--untracked-files=no'], value => !value.trim());
  if (ctx.platform === 'darwin') {
    let okay = false;
    try { okay = await fs.readFile(path.join(p.source, '.git/info/sparse-checkout'), 'utf8') === MACOS_SPARSE_RULES; } catch { /* failed evidence below */ }
    checks.push({ id: 'hermes:macos-attribution-exclusion', status: okay ? 'verified' : 'failed', required: true, detail: 'macOS omits only contributors/emails case-colliding attribution; all runtime source must remain tracked and clean.' });
  }
  await probe('hermes:imports', p.python, ['-c', "import importlib.metadata as m; import hermes_cli.main, discord, nacl.secret, openai, yaml, mcp, httpx2; from tools.mcp_tool import _ensure_mcp_sdk; assert m.version('hermes-agent') and _ensure_mcp_sdk(); print('imports-ok')"], value => value.includes('imports-ok'));
  await probe('rmux:version', p.rmux, ['-V'], value => value.trim() === `rmux ${ctx.pins.RMUX_VERSION}`);
  let launcherOkay = false;
  try {
    const installed = await fs.readFile(path.join(ctx.bin, 'agk'), 'utf8');
    launcherOkay = installed === launcher(ctx, '/bin/bash', [path.join(p.agk, 'bin/agk')], { agk: true });
    const daemon = await info(path.join(ctx.tools, 'rmux/bin/rmux-daemon'));
    launcherOkay &&= daemon?.isFile() === true && daemon.size > 0 && daemon.nlink === 1 && daemon.uid === process.getuid() && Boolean(daemon.mode & 0o100);
  } catch { /* Missing/stale context is a failure, never a global daemon fallback. */ }
  checks.push({ id: 'rmux:launcher-context', status: launcherOkay ? 'verified' : 'failed', required: true, detail: launcherOkay ? 'AGK binds the reviewed raw SDK daemon, private socket namespace and exact named Hermes profile.' : 'AGK launcher context is missing or stale; review owned software before repair. Never fall back to a personal RMUX daemon.' });
  await probe('agk:commands', path.join(ctx.bin, 'agk'), ['commands'], value => value.includes('AGK-TUI'));
  await probe('agk:controller', path.join(ctx.bin, 'agk'), ['status'], value => value.includes('PRIVATE'));
  await probe('agk:inventory', path.join(ctx.bin, 'agk'), ['doctor', '--offline'], value => value.includes('INSTALLATION_ONLY') && !value.includes('FAIL:'));
  for (const name of ['agentik_os', 'platforms/discord']) await probe(`hermes:plugin:${name}`, p.hermes, ['--profile', ctx.profile, 'plugins', 'doctor', '--ci', path.join(p.profile, 'plugins', name)]);
  await probe('hermes:plugin-discovery', p.python, ['-c', "from hermes_cli.plugins import discover_plugins,get_plugin_manager; discover_plugins(); rows=get_plugin_manager().list_plugins(); expected={'agentik-os','platforms/discord'}; active={r.get('key') or r['name'] for r in rows if r['enabled'] and not r.get('error')}; assert expected<=active, 'Station plugins not natively enabled'; print('plugins-enabled')"], value => value.includes('plugins-enabled'), { env: { ...env, HERMES_HOME: p.profile } });
  for (const [name, version, , bin] of CLI_PACKAGES) {
    if (bin === 'chatbotx') { checks.push(await verifyChatbotX(ctx, { run })); emit({ phase: 'verify', status: checks.at(-1).status, message: 'cli:chatbotx' }); }
    else if (bin) await probe(`cli:${bin}`, path.join(ctx.bin, bin), ['--version'], value => value.includes(ctx.pins[version]));
    else await probe('sdk:discord.js', process.execPath, ['--input-type=module', '-e', `import {createRequire} from 'node:module';const require=createRequire(${JSON.stringify(path.join(p.npm, 'package.json'))});const d=require('discord.js');if(d.version!==${JSON.stringify(ctx.pins[version])})process.exit(1);console.log('sdk-ok')`], value => value.includes('sdk-ok'));
  }
  checks.push(...await verifyConnectors(ctx, { run, emit }));
  checks.push(...await verifyWeb(ctx, { run, emit, env }));
  for (const [id, detail] of [
    ['gateway', 'Software prepared; enroll the exact profile and explicitly activate. No Discord or other chat readback has occurred.'],
    ['accounts', 'Hermes model, GitHub, Vercel, Codex and Composio identities require separate enrollment; no personal credentials were copied.'],
    ['chatbotx:connection', 'CLI installed; choose the owning ChatbotX workspace/API and explicitly enroll its credential. MCP template is disabled; no full application, campaign or account was activated. See resources/chatbotx/README.md.'],
    ['voice:native-libraries', 'Hermes voice/messaging Python extras installed; ffmpeg, Opus and PortAudio plus a real audio/account roundtrip still require acceptance.'],
    ['services', 'Parakeet, memory servers, Tailscale and TigerVNC are not activated on Workstation. Host service recipes are not portable acceptance.'],
    ['strix', 'Security scans require an approved disposable Linux LAB; never run them implicitly on this personal Workstation.'],
    ['ponytail', 'Native compatibility guard remains mandatory; no bypass or readiness claim.'],
  ]) checks.push({ id, status: ['ponytail', 'strix', 'services'].includes(id) ? 'blocked' : 'not-configured', required: false, detail });
  return checks;
}
