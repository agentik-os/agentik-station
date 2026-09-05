/** Pinned software-only connector CLIs. No shell installer or account adoption. */
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { privateEnv, runtimePaths, launcher } from './runtime.mjs';

// Reviewed 2026-09-05 from the official release checksum manifests:
// https://github.com/cli/cli/releases/download/v2.100.0/gh_2.100.0_checksums.txt
// https://github.com/ComposioHQ/composio/releases/download/%40composio%2Fcli%400.4.0/checksums.txt
// The current composio.dev/install also matched COMPOSIO_INSTALL_SHA256. We use
// its exact release bundle directly: no mutable shell setup/agent-login behavior.
const GH_HASHES = Object.freeze({
  'darwin-arm64': '45f9a62da2f6e641a7fad57e2ce39656dfd7ef331372d80a2a2aed65abb01642',
  'darwin-x64': 'fcd7799e85eb575f3c7d2b1679bfbfedaefa1269d4bc7d096b51e10939b4812b',
  'linux-arm64': 'ea4e7a581a32ccad6cc7923cb1576ac5859ba4b9a16ab22eb8f8a96e78e2e961',
  'linux-x64': 'e4d4bb4498e8d007abe545b6568926793ace1b6447da598294a610018cb164be',
});
const COMPOSIO_HASHES = Object.freeze({
  'darwin-arm64': '1151af41bd79f91696b2674a491c786296a84de568b1d760d1d4e407fe5684c8',
  'darwin-x64': '995ec9205fac64936ffe55968ab985dbbf0edee16268cc6fe97aabc74ec22b2c',
  'linux-arm64': '23e1eb80d1949ea8ad4bb1129db9f691262fe158889a9894245109e98ec63e33',
  'linux-x64': '32674fef4adea8e905ba7b618feb72f1937db43a34b58386a398f3a854d65f76',
});

export function connectorDefinitions(ctx) {
  const target = `${ctx.platform}-${ctx.arch}`;
  if (!GH_HASHES[target] || !COMPOSIO_HASHES[target]) throw new Error('Connector binaries support macOS/Linux x64 and arm64 only.');
  if (ctx.pins.GITHUB_CLI_VERSION !== '2.100.0' || ctx.pins.COMPOSIO_CLI_VERSION !== '0.4.0') throw new Error('Connector release pins changed; review and record the official archive digests first.');
  const ghBase = `gh_2.100.0_${ctx.platform === 'darwin' ? 'macOS' : 'linux'}_${ctx.arch === 'x64' ? 'amd64' : 'arm64'}`;
  const composioBase = `composio-${ctx.platform}-${ctx.arch === 'arm64' ? 'aarch64' : 'x64'}`;
  return [
    { id: 'github', command: 'gh', version: '2.100.0', archive: `${ghBase}${ctx.platform === 'darwin' ? '.zip' : '.tar.gz'}`, prefix: ghBase, binary: 'bin/gh', sha256: GH_HASHES[target], base: 'https://github.com/cli/cli/releases/download/v2.100.0' },
    { id: 'composio', command: 'composio', version: '0.4.0', archive: `${composioBase}.zip`, prefix: composioBase, binary: 'composio', sha256: COMPOSIO_HASHES[target], base: 'https://github.com/ComposioHQ/composio/releases/download/%40composio%2Fcli%400.4.0' },
  ].map(value => ({ ...value, url: `${value.base}/${value.archive}`, destination: path.join(ctx.tools, 'connectors', value.id, value.version), cached: path.join(ctx.cache, 'connectors', value.archive) }));
}

export function signingRepairDefinition(ctx, definition) {
  if (ctx.platform !== 'darwin' || ctx.arch !== 'arm64' || definition.id !== 'composio') return null;
  if (ctx.pins.COMPOSIO_CLI_VERSION !== '0.4.0' || definition.version !== '0.4.0' || definition.sha256 !== COMPOSIO_HASHES['darwin-arm64'] || definition.binary !== 'composio' || definition.prefix !== 'composio-darwin-aarch64') throw new Error('Local signing repair is restricted to the exact reviewed Composio 0.4.0 arm64 archive.');
  return {
    ...definition,
    destination: path.join(ctx.tools, 'connectors', 'composio', '0.4.0-darwin-arm64-adhoc-v1'),
    receipt: path.join(ctx.evidence, 'connectors', 'composio-0.4.0-darwin-arm64-adhoc-v1.json'),
  };
}

async function safe(ctx, target) {
  if (!path.isAbsolute(ctx.root) || path.resolve(ctx.root) !== ctx.root || !target.startsWith(`${ctx.root}${path.sep}`) || path.resolve(target) !== target) throw new Error('Connector path escapes the Workstation root.');
  let current = ctx.root;
  for (const part of ['', ...path.relative(ctx.root, target).split(path.sep)]) {
    current = path.join(current, part);
    try {
      const stat = await fs.lstat(current);
      if (stat.isSymbolicLink() || !stat.isDirectory() && !stat.isFile() || stat.isFile() && stat.nlink !== 1 || stat.uid !== process.getuid() || stat.mode & 0o022) throw new Error('Unsafe or writable-by-other-user connector path.');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

async function mkdir(ctx, target) {
  await safe(ctx, target);
  await fs.mkdir(target, { recursive: true, mode: 0o700 });
  await safe(ctx, target);
}

async function hashFile(ctx, filename) {
  await safe(ctx, filename);
  const handle = await fs.open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size > 256 * 1024 * 1024) throw new Error('Connector archive is not a bounded regular file.');
    const digest = createHash('sha256');
    for await (const bytes of handle.createReadStream({ autoClose: false })) digest.update(bytes);
    return digest.digest('hex');
  } finally { await handle.close(); }
}

async function readSmall(ctx, filename, limit = 65536) {
  await safe(ctx, filename);
  const handle = await fs.open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size > limit) throw new Error('Connector metadata must be a bounded owned regular file.');
    return await handle.readFile('utf8');
  } finally { await handle.close(); }
}

async function writeNew(ctx, target, bytes, mode = 0o600) {
  await safe(ctx, target);
  await mkdir(ctx, path.dirname(target));
  try {
    const existing = await readSmall(ctx, target);
    if (existing !== String(bytes)) throw new Error('Existing connector launcher differs; preserve it and review explicit repair.');
    return;
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const temporary = `${target}.${randomUUID()}.tmp`;
  const handle = await fs.open(temporary, 'wx', mode);
  try { await handle.writeFile(bytes); await handle.sync(); } finally { await handle.close(); }
  try { await fs.link(temporary, target); } finally { await fs.unlink(temporary); }
}

async function connectorLauncher(ctx, definition, binary) {
  const target = path.join(ctx.bin, definition.command), content = launcher(ctx, binary);
  await safe(ctx, target);
  let existing;
  try { existing = await readSmall(ctx, target); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const originalBinary = path.join(definition.destination, definition.binary);
  if (existing && existing !== content && signingRepairDefinition(ctx, definition) && existing === launcher(ctx, originalBinary)) {
    // A previous exact software-only launcher may select the known broken
    // original. Preserve those bytes before this explicitly reviewed repair.
    await writeNew(ctx, path.join(ctx.evidence, 'connectors', 'composio-launcher-before-adhoc-v1.txt'), existing);
    const prior = await fs.lstat(target), temp = `${target}.${randomUUID()}.tmp`;
    await writeNew(ctx, temp, content, 0o700);
    const now = await fs.lstat(target);
    if (now.ino !== prior.ino || now.mtimeMs !== prior.mtimeMs) throw new Error('Connector launcher changed during signing repair.');
    await fs.rename(temp, target);
    return;
  }
  await writeNew(ctx, target, content, 0o700);
}

// Python's stdlib reads ZIP/TAR metadata before any extraction. No extractall,
// symlinks, hardlinks, special files, path traversal, duplicate entries, or
// unbounded decompression. Verification derives expected file hashes afresh from
// the digest-pinned archive instead of trusting a user-writable installed ledger.
export const CONNECTOR_ARCHIVE_SCRIPT = String.raw`
import hashlib, json, os, pathlib, stat, sys, tarfile, zipfile
archive, destination, prefix, required_binary, expected_hash, action = sys.argv[1:7]
derived_hash = sys.argv[7] if len(sys.argv) == 8 else None
destination = pathlib.Path(destination)
fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
metadata = os.fstat(fd)
if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > 256 * 1024 * 1024:
    raise ValueError("unsafe archive file")
raw = os.fdopen(fd, "rb")
digest = hashlib.file_digest(raw, "sha256").hexdigest()
if digest != expected_hash:
    raise ValueError("archive digest mismatch")
raw.seek(0)
bundle = zipfile.ZipFile(raw) if archive.endswith(".zip") else tarfile.open(fileobj=raw, mode="r:gz")
is_zip = isinstance(bundle, zipfile.ZipFile)
entries = bundle.infolist() if is_zip else bundle.getmembers()
if len(entries) > 20000:
    raise ValueError("archive member count exceeds bound")
files, directories, seen, total = {}, set(), set(), 0
for entry in entries:
    name = entry.filename if is_zip else entry.name
    if name.startswith("./"):
        name = name[2:]
    parts = name.rstrip("/").split("/")
    if not parts or parts[0] != prefix or any(p in ("", ".", "..") or "\\" in p or any(ord(c) < 32 for c in p) for p in parts):
        raise ValueError("unsafe archive member path")
    mode = (entry.external_attr >> 16) if is_zip else entry.mode
    directory = entry.is_dir() if is_zip else entry.isdir()
    regular = stat.S_IFMT(mode) in (0, stat.S_IFREG) if is_zip else entry.isfile()
    if (directory and is_zip and stat.S_IFMT(mode) not in (0, stat.S_IFDIR)) or (not directory and not regular):
        raise ValueError("links or special files are forbidden")
    relative = "/".join(parts[1:])
    if not relative:
        if not directory:
            raise ValueError("archive root must be a directory")
        continue
    if relative in seen:
        raise ValueError("duplicate archive member")
    seen.add(relative)
    if directory:
        directories.add(relative)
        directories.update(str(p) for p in pathlib.PurePosixPath(relative).parents if str(p) != ".")
        continue
    size = entry.file_size if is_zip else entry.size
    total += size
    if size < 0 or size > 512 * 1024 * 1024 or total > 1024 * 1024 * 1024:
        raise ValueError("archive decompression exceeds bound")
    files[relative] = (entry, mode, size)
    directories.update(str(p) for p in pathlib.PurePosixPath(relative).parents if str(p) != ".")
if required_binary not in files or any(name in files for name in directories):
    raise ValueError("missing CLI binary or file/directory conflict")
if action not in ("install", "verify", "verify-derived") or (action == "verify-derived" and (not derived_hash or len(derived_hash) != 64 or any(c not in "0123456789abcdef" for c in derived_hash))):
    raise ValueError("unknown archive operation")
if action == "install":
    destination.mkdir(mode=0o700)  # exclusive: never replace or adopt a partial root
    for name in sorted(directories, key=lambda n: (n.count("/"), n)):
        (destination / name).mkdir(mode=0o700)
else:
    root_stat = destination.lstat()
    if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_mode & 0o022 or root_stat.st_uid != os.getuid():
        raise ValueError("unsafe installed connector root")
    actual = set()
    for current, dirnames, filenames in os.walk(destination, followlinks=False):
        for name in dirnames + filenames:
            item = pathlib.Path(current) / name
            info = item.lstat()
            if info.st_uid != os.getuid() or info.st_mode & 0o022 or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("unsafe installed connector member")
            actual.add(item.relative_to(destination).as_posix())
    if actual != set(files) | directories:
        raise ValueError("installed connector tree differs from reviewed archive")
for name, (entry, mode, size) in files.items():
    source = bundle.open(entry) if is_zip else bundle.extractfile(entry)
    target = destination / name
    output = None
    if action == "install":
        output = target.open("xb")
        os.fchmod(output.fileno(), 0o700 if mode & 0o111 or name == required_binary else 0o600)
    else:
        target_fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        target_stat = os.fstat(target_fd)
        transformed = action == "verify-derived" and name == required_binary
        if not stat.S_ISREG(target_stat.st_mode) or target_stat.st_nlink != 1 or target_stat.st_size > 512 * 1024 * 1024 or (not transformed and target_stat.st_size != size) or bool(target_stat.st_mode & 0o111) != bool(mode & 0o111 or name == required_binary):
            raise ValueError("installed connector file metadata differs")
        output = os.fdopen(target_fd, "rb")
        if transformed:
            if hashlib.file_digest(output, "sha256").hexdigest() != derived_hash:
                raise ValueError("derived connector digest differs")
            output.close(); source.close()
            continue
    read = 0
    while True:
        chunk = source.read(65536)
        if not chunk:
            break
        read += len(chunk)
        if read > size:
            raise ValueError("archive member exceeds declared size")
        if action == "install":
            output.write(chunk)
        elif output.read(len(chunk)) != chunk:
            raise ValueError("installed connector bytes differ")
    if read != size:
        raise ValueError("truncated archive member")
    source.close()
    output.close()
bundle.close()
raw.close()
print(json.dumps({"files": len(files), "verified_bytes": total, "operation": action}))
`;

async function archiveOperation(ctx, definition, run, action, derivedHash) {
  await safe(ctx, definition.cached);
  await safe(ctx, definition.destination);
  return run(runtimePaths(ctx).python, ['-I', '-c', CONNECTOR_ARCHIVE_SCRIPT, definition.cached, definition.destination, definition.prefix, definition.binary, definition.sha256, action, ...(derivedHash ? [derivedHash] : [])], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 120000 });
}

function versionMatches(definition, response) {
  const escaped = definition.version.replaceAll('.', '\\.');
  const expected = definition.id === 'github' ? new RegExp(`^gh version ${escaped}(?:\\s|$)`, 'm') : new RegExp(`(?:^|\\s)(?:v)?${escaped}(?:\\s|$)`, 'm');
  return response.code === 0 && expected.test(`${response.stdout}\n${response.stderr}`);
}

async function versionProbe(ctx, definition, binary, run) {
  const probes = path.join(ctx.cache, 'connector-probes');
  await mkdir(ctx, probes);
  const probe = await fs.mkdtemp(path.join(probes, `${definition.id}-`));
  const probeCtx = { ...ctx, home: path.join(probe, 'home'), cache: path.join(probe, 'cache'), hermesHome: path.join(probe, 'home', '.hermes') };
  for (const directory of [probeCtx.home, probeCtx.cache, path.join(probeCtx.cache, 'tmp')]) await mkdir(ctx, directory);
  try {
    return await run(binary, ['--version'], { env: privateEnv(probeCtx, { GH_NO_UPDATE_NOTIFIER: '1', GH_NO_EXTENSION_UPDATE_NOTIFIER: '1', DO_NOT_TRACK: '1' }), cwd: probeCtx.home, timeoutMs: 30000, allowFailure: true });
  } finally {
    await safe(ctx, probe);
    await fs.rm(probe, { recursive: true, force: false });
  }
}

async function verifySigningRepair(ctx, definition, repair, run) {
  await safe(ctx, repair.receipt);
  const stat = await fs.lstat(repair.receipt);
  if (!stat.isFile() || stat.nlink !== 1 || stat.size > 16384 || stat.mode & 0o077) throw new Error('Unsafe local signing receipt.');
  const record = JSON.parse(await readSmall(ctx, repair.receipt, 16384));
  const original = path.join(definition.destination, definition.binary);
  if (record.schema !== 1 || record.transformation !== 'macos-adhoc-v1' || record.version !== '0.4.0' || record.platform !== 'darwin-arm64' || record.archive_sha256 !== definition.sha256 || record.source_sha256 !== await hashFile(ctx, original) || !/^[a-f0-9]{64}$/.test(record.derived_sha256 || '') || record.tool?.path !== '/usr/bin/codesign' || !/^[a-f0-9]{64}$/.test(record.tool?.sha256 || '') || !/^[A-Za-z0-9]{3,32}$/.test(record.tool?.macos_build || '') || JSON.stringify(record.command) !== JSON.stringify(['--force', '--sign', '-', '--timestamp=none'])) throw new Error('Local signing receipt does not match the reviewed original and exact transformation.');
  await archiveOperation(ctx, repair, run, 'verify-derived', record.derived_sha256);
  const binary = path.join(repair.destination, repair.binary);
  await run('/usr/bin/codesign', ['--verify', '--strict', binary], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 15000 });
  return binary;
}

async function signingRepair(ctx, definition, run, emit) {
  const repair = signingRepairDefinition(ctx, definition);
  const original = path.join(definition.destination, definition.binary);
  if (!repair) return original;
  let exists = false;
  try { await fs.lstat(repair.destination); exists = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (exists) return verifySigningRepair(ctx, definition, repair, run);
  const signature = await run('/usr/bin/codesign', ['--verify', '--strict', original], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 15000, allowFailure: true });
  if (signature.code === 0) return original;
  // This is a reviewed local packaging transformation, not publisher identity.
  // The original archive/bundle remain unchanged and are checked on every verify.
  emit({ phase: 'connector:composio', status: 'running', message: 'Repairing the known Composio macOS arm64 ad-hoc signature in a separate derived bundle; publisher trust is not implied' });
  const identity = await run('/usr/bin/codesign', ['-d', '--verbose=2', original], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 15000, allowFailure: true });
  if (!`${identity.stdout}\n${identity.stderr}`.includes('Signature=adhoc')) throw new Error('Signing repair refuses a non-ad-hoc or unrecognized original signature.');
  await archiveOperation(ctx, repair, run, 'install');
  const binary = path.join(repair.destination, repair.binary);
  await run('/usr/bin/codesign', ['--force', '--sign', '-', '--timestamp=none', binary], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 60000 });
  await run('/usr/bin/codesign', ['--verify', '--strict', binary], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 15000 });
  if (!versionMatches(definition, await versionProbe(ctx, definition, binary, run))) throw new Error('Derived Composio failed its native version check; preserve both bundles for explicit repair.');
  const build = await run('/usr/bin/sw_vers', ['-buildVersion'], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 15000 });
  const record = {
    schema: 1, transformation: 'macos-adhoc-v1', version: '0.4.0', platform: 'darwin-arm64',
    archive_sha256: definition.sha256, source_sha256: await hashFile(ctx, original), derived_sha256: await hashFile(ctx, binary),
    tool: { path: '/usr/bin/codesign', sha256: createHash('sha256').update(await fs.readFile('/usr/bin/codesign')).digest('hex'), macos_build: build.stdout.trim() },
    command: ['--force', '--sign', '-', '--timestamp=none'],
    trust: 'Local ad-hoc packaging only; not Apple notarization or publisher identity.',
  };
  await writeNew(ctx, repair.receipt, `${JSON.stringify(record, null, 2)}\n`);
  await verifySigningRepair(ctx, definition, repair, run);
  return binary;
}

async function download(ctx, definition, run, curl) {
  await mkdir(ctx, path.dirname(definition.cached));
  let exists = false;
  try { await fs.lstat(definition.cached); exists = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (!exists) {
    const temporary = `${definition.cached}.${randomUUID()}.partial`;
    const handle = await fs.open(temporary, 'wx', 0o600);
    await handle.close();
    // Failed downloads remain named partial artifacts; no ambiguous overwrite.
    await run(curl, ['--fail', '--silent', '--show-error', '--location', '--proto', '=https', '--proto-redir', '=https', '--max-filesize', String(256 * 1024 * 1024), '--output', temporary, definition.url], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 600000 });
    if (await hashFile(ctx, temporary) !== definition.sha256) throw new Error('Connector archive checksum mismatch; preserve the partial download for review.');
    await fs.link(temporary, definition.cached);
    await fs.unlink(temporary);
  }
  if (await hashFile(ctx, definition.cached) !== definition.sha256) throw new Error('Cached connector archive changed; inspect it before explicit repair.');
}

export async function provisionConnectors(ctx, { run, emit = () => {}, found = {} } = {}) {
  const definitions = connectorDefinitions(ctx);
  if (typeof run !== 'function') throw new Error('A bounded private command runner is required.');
  const curl = found.curl || '/usr/bin/curl';
  if (!path.isAbsolute(curl)) throw new Error('Connector downloader must be an explicitly resolved executable.');
  for (const definition of definitions) {
    emit({ phase: `connector:${definition.id}`, status: 'running', message: `Installing reviewed ${definition.command} ${definition.version}; account enrollment remains separate` });
    await download(ctx, definition, run, curl);
    await mkdir(ctx, path.dirname(definition.destination));
    let present = false;
    try { await fs.lstat(definition.destination); present = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
    await archiveOperation(ctx, definition, run, present ? 'verify' : 'install');
    await archiveOperation(ctx, definition, run, 'verify');
    const binary = await signingRepair(ctx, definition, run, emit);
    await connectorLauncher(ctx, definition, binary);
    emit({ phase: `connector:${definition.id}`, status: 'prepared', message: `${definition.command} archive and installed files verified; no account was enrolled` });
  }
}

export async function verifyConnectors(ctx, { run, emit = () => {} } = {}) {
  const checks = [];
  for (const definition of connectorDefinitions(ctx)) {
    try {
      if (await hashFile(ctx, definition.cached) !== definition.sha256) throw new Error('archive changed');
      await archiveOperation(ctx, definition, run, 'verify');
      const wrapper = path.join(ctx.bin, definition.command);
      const repair = signingRepairDefinition(ctx, definition);
      let binary = path.join(definition.destination, definition.binary);
      if (repair) {
        let exists = false;
        try { await fs.lstat(repair.destination); exists = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
        if (exists) binary = await verifySigningRepair(ctx, definition, repair, run);
      }
      await safe(ctx, wrapper);
      if (await readSmall(ctx, wrapper) !== launcher(ctx, binary)) throw new Error('launcher changed');
      // Do not execute the wrapper here: it intentionally selects the real private
      // account HOME. Version probes instead get a fresh, disposable namespace.
      const response = await versionProbe(ctx, definition, binary, run);
      const okay = versionMatches(definition, response);
      const transformed = binary !== path.join(definition.destination, definition.binary);
      let detail = okay ? `Pinned ${definition.command} ${definition.version} and complete bundle verified${transformed ? ' with recorded local ad-hoc signing (not publisher identity)' : ''}; account and live capability NOT_CHECKED` : 'Native version probe failed; preserve files and inspect explicit repair.';
      if (!okay && ctx.platform === 'darwin') {
        const signature = await run('/usr/bin/codesign', ['--verify', binary], { env: privateEnv(ctx), cwd: ctx.root, timeoutMs: 15000, allowFailure: true });
        if (signature.code !== 0) detail = 'Reviewed upstream macOS binary has an invalid code signature and cannot run on this Mac. Preserve the original bundle; an explicitly reviewed signing repair or corrected upstream release is required. No signature/security bypass was applied. Account NOT_CHECKED.';
      }
      checks.push({ id: `cli:${definition.command}`, status: okay ? 'verified' : 'failed', required: true, detail });
    } catch {
      checks.push({ id: `cli:${definition.command}`, status: 'failed', required: true, detail: 'Pinned connector archive, installed bundle, launcher or native probe failed; inspect explicit repair. Account NOT_CHECKED.' });
    }
    emit({ phase: 'verify', status: checks.at(-1).status, message: `cli:${definition.command}` });
  }
  return checks;
}
