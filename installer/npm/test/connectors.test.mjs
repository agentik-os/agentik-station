import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { connectorDefinitions, signingRepairDefinition, provisionConnectors, verifyConnectors, CONNECTOR_ARCHIVE_SCRIPT } from '../connectors.mjs';

const pins = { GITHUB_CLI_VERSION: '2.100.0', COMPOSIO_CLI_VERSION: '0.4.0' };
async function fixture(t) {
  const scratch = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'station-connectors-'));
  t.after(() => fs.rm(scratch, { recursive: true, force: true }));
  const root = path.join(scratch, 'station');
  const ctx = { root, sourceRoot: root, accountHome: scratch, home: path.join(root, 'personal/home'), tools: path.join(root, 'tools'), bin: path.join(root, 'bin'), cache: path.join(root, 'cache'), evidence: path.join(root, 'evidence'), resources: path.join(root, 'resources'), projects: path.join(root, 'projects'), profile: 'station-0123456789ab', platform: 'darwin', arch: 'arm64', pins };
  ctx.hermesHome = path.join(ctx.home, '.hermes');
  for (const directory of [ctx.home, ctx.tools, ctx.bin, ctx.cache, ctx.resources, ctx.projects]) await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  return { ctx, scratch };
}

const MAKE_ARCHIVE = String.raw`
import io,json,pathlib,stat,sys,tarfile,zipfile
entries=json.loads(sys.argv[2]); archive=sys.argv[1]
if archive.endswith(".zip"):
    with zipfile.ZipFile(archive,"w") as z:
        for row in entries:
            info=zipfile.ZipInfo(row["name"])
            info.external_attr=(row.get("mode",stat.S_IFREG|0o755))<<16
            z.writestr(info,row.get("body","synthetic"))
else:
    with tarfile.open(archive,"w:gz") as t:
        for row in entries:
            info=tarfile.TarInfo(row["name"]); info.mode=0o755
            body=row.get("body","synthetic").encode(); info.size=len(body)
            if row.get("link"):
                info.type=tarfile.SYMTYPE; info.linkname=row["link"]; info.size=0
            if row.get("hardlink"):
                info.type=tarfile.LNKTYPE; info.linkname=row["hardlink"]; info.size=0
            t.addfile(info,io.BytesIO(body))
`;

async function pythonBinary() {
  for (const directory of (process.env.PATH || '').split(path.delimiter)) {
    if (!path.isAbsolute(directory)) continue;
    const candidate = path.join(directory, 'python3');
    try {
      await fs.access(candidate, fs.constants.X_OK);
      const version = execFileSync(candidate, ['-I', '-c', 'import sys;print(sys.version_info >= (3,11))'], { encoding: 'utf8' }).trim();
      if (version === 'True') return candidate;
    } catch { /* next available Python */ }
  }
  return null;
}

async function archiveFixture(t, entries, suffix = '.zip') {
  const { ctx, scratch } = await fixture(t);
  const python = await pythonBinary();
  if (!python) { t.skip('Archive tests require existing Python >=3.11 (same as portable Hermes).'); return null; }
  const archive = path.join(scratch, `synthetic${suffix}`);
  const environment = { HOME: ctx.home, PATH: '/usr/bin:/bin', PYTHONDONTWRITEBYTECODE: '1' };
  execFileSync(python, ['-I', '-c', MAKE_ARCHIVE, archive, JSON.stringify(entries)], { env: environment, stdio: 'pipe' });
  const digest = createHash('sha256').update(await fs.readFile(archive)).digest('hex');
  const destination = path.join(ctx.tools, 'bundle');
  const operate = (action = 'install', checksum = digest, derivedHash) => execFileSync(python, ['-I', '-c', CONNECTOR_ARCHIVE_SCRIPT, archive, destination, 'reviewed', 'bin/tool', checksum, action, ...(derivedHash ? [derivedHash] : [])], { env: environment, encoding: 'utf8', stdio: 'pipe' });
  return { ctx, scratch, archive, destination, operate };
}

test('all four native platforms map to exact officially reviewed release hashes', () => {
  const hashes = new Set();
  for (const platform of ['darwin', 'linux']) for (const arch of ['arm64', 'x64']) {
    const definitions = connectorDefinitions({ platform, arch, pins, tools: '/station/tools', cache: '/station/cache' });
    assert.equal(definitions.length, 2);
    for (const definition of definitions) {
      assert.match(definition.sha256, /^[a-f0-9]{64}$/);
      assert.match(definition.url, /^https:\/\/github.com\/(cli\/cli|ComposioHQ\/composio)\/releases\/download\//);
      assert.equal(definition.url.includes('latest'), false);
      hashes.add(definition.sha256);
    }
  }
  assert.equal(hashes.size, 8);
});

test('unreviewed releases and unsupported architectures fail closed', () => {
  const ctx = { platform: 'linux', arch: 'x64', tools: '/station/tools', cache: '/station/cache', pins };
  assert.throws(() => connectorDefinitions({ ...ctx, pins: { ...pins, COMPOSIO_CLI_VERSION: '9.0.0' } }), /pins changed/);
  assert.throws(() => connectorDefinitions({ ...ctx, platform: 'win32' }), /support/);
});

test('ad-hoc signing is restricted to one exact reviewed platform, version and source digest', async t => {
  const { ctx } = await fixture(t);
  const definition = connectorDefinitions(ctx)[1];
  const repair = signingRepairDefinition(ctx, definition);
  assert.notEqual(repair.destination, definition.destination);
  assert.ok(repair.destination.startsWith(`${ctx.tools}/`));
  for (const changed of [{ sha256: '0'.repeat(64) }, { version: '0.5.0' }, { binary: 'other' }, { prefix: '../escape' }]) assert.throws(() => signingRepairDefinition(ctx, { ...definition, ...changed }), /exact reviewed/);
  assert.throws(() => signingRepairDefinition({ ...ctx, pins: { ...pins, COMPOSIO_CLI_VERSION: '0.5.0' } }, definition), /exact reviewed/);
  assert.equal(signingRepairDefinition({ ...ctx, arch: 'x64' }, definition), null);
  assert.equal(signingRepairDefinition({ ...ctx, platform: 'linux' }, definition), null);
  assert.equal(signingRepairDefinition(ctx, connectorDefinitions(ctx)[0]), null);
});

test('archive digest mismatch fails before creating an installation root', async t => {
  const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }]);
  if (!f) return;
  assert.throws(() => f.operate('install', '0'.repeat(64)), /digest mismatch/);
  await assert.rejects(fs.access(f.destination), { code: 'ENOENT' });
});

test('complete bundle files and support resources survive extraction and verification', async t => {
  const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }, { name: 'reviewed/support/index.js', body: 'support fixture' }, { name: 'reviewed/LICENSE', body: 'license fixture' }]);
  if (!f) return;
  assert.equal(JSON.parse(f.operate()).files, 3);
  assert.equal(await fs.readFile(path.join(f.destination, 'support/index.js'), 'utf8'), 'support fixture');
  assert.equal(JSON.parse(f.operate('verify')).operation, 'verify');
});

test('TAR extraction handles complete regular bundles without extractall', async t => {
  const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }, { name: 'reviewed/share/manual.txt', body: 'manual' }], '.tar.gz');
  if (!f) return;
  f.operate();
  assert.equal(JSON.parse(f.operate('verify')).files, 2);
});

for (const [label, entry] of [
  ['parent traversal', { name: 'reviewed/../outside' }],
  ['absolute path', { name: '/outside' }],
  ['wrong archive root', { name: 'other/bin/tool' }],
  ['ZIP symlink', { name: 'reviewed/link', mode: 0o120777, body: '/outside' }],
  ['ZIP special file', { name: 'reviewed/fifo', mode: 0o010600 }],
  ['ZIP directory-shaped symlink', { name: 'reviewed/link/', mode: 0o120777 }],
]) test(`${label} is rejected before any installation write`, async t => {
  const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }, entry]);
  if (!f) return;
  assert.throws(() => f.operate(), /unsafe archive|links or special/);
  await assert.rejects(fs.access(f.destination), { code: 'ENOENT' });
});

test('duplicate archive entries and file/directory collisions fail closed', async t => {
  for (const entries of [
    [{ name: 'reviewed/bin/tool' }, { name: 'reviewed/bin/tool' }],
    [{ name: 'reviewed/bin/tool' }, { name: 'reviewed/bin' }],
  ]) {
    const f = await archiveFixture(t, entries);
    if (!f) return;
    assert.throws(() => f.operate(), /duplicate archive|file\/directory conflict/);
    await assert.rejects(fs.access(f.destination), { code: 'ENOENT' });
  }
});

test('TAR symbolic and hard links are rejected', async t => {
  for (const link of [{ link: '/outside' }, { hardlink: 'reviewed/bin/tool' }]) {
    const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }, { name: 'reviewed/link', ...link }], '.tar.gz');
    if (!f) return;
    assert.throws(() => f.operate(), /links or special/);
  }
});

test('occupied install directories are preserved, never adopted or overwritten', async t => {
  const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }]);
  if (!f) return;
  await fs.mkdir(f.destination);
  await fs.writeFile(path.join(f.destination, 'keep'), 'existing operator data');
  assert.throws(() => f.operate(), /FileExistsError/);
  assert.equal(await fs.readFile(path.join(f.destination, 'keep'), 'utf8'), 'existing operator data');
});

test('verification detects modified bytes and additional files', async t => {
  const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }]);
  if (!f) return;
  f.operate();
  await fs.writeFile(path.join(f.destination, 'bin/tool'), 'tampered!');
  assert.throws(() => f.operate('verify'), /bytes differ/);
  await fs.writeFile(path.join(f.destination, 'extra'), 'not reviewed');
  assert.throws(() => f.operate('verify'), /tree differs/);
});

test('verification detects symlink and hardlink substitutions', async t => {
  for (const kind of ['symlink', 'hardlink']) {
    const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }]);
    if (!f) return;
    f.operate();
    const binary = path.join(f.destination, 'bin/tool');
    if (kind === 'symlink') { await fs.unlink(binary); await fs.symlink('/outside', binary); }
    else await fs.link(binary, path.join(f.scratch, 'binary-alias'));
    assert.throws(() => f.operate('verify'), /unsafe installed/);
  }
});

test('derived verification permits only the recorded binary digest while checking every support file', async t => {
  const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }, { name: 'reviewed/support.txt', body: 'support' }]);
  if (!f) return;
  f.operate();
  const binary = path.join(f.destination, 'bin/tool');
  await fs.writeFile(binary, 'synthetic signed executable');
  const derived = createHash('sha256').update(await fs.readFile(binary)).digest('hex');
  assert.equal(JSON.parse(f.operate('verify-derived', undefined, derived)).operation, 'verify-derived');
  assert.throws(() => f.operate('verify-derived', undefined, '0'.repeat(64)), /derived connector digest/);
  await fs.writeFile(path.join(f.destination, 'support.txt'), 'changed');
  assert.throws(() => f.operate('verify-derived', undefined, derived), /bytes differ/);
});

test('derived verification rejects missing or malformed digest approval', async t => {
  const f = await archiveFixture(t, [{ name: 'reviewed/bin/tool' }]);
  if (!f) return;
  f.operate();
  assert.throws(() => f.operate('verify-derived'), /unknown archive operation/);
  assert.throws(() => f.operate('verify-derived', undefined, '*'), /unknown archive operation/);
});

test('download uses explicit HTTPS arguments and rejects bytes before extraction', async t => {
  const { ctx } = await fixture(t);
  const calls = [];
  const run = async (executable, argv, options) => {
    calls.push({ executable, argv, options });
    await fs.writeFile(argv[argv.indexOf('--output') + 1], 'not an official archive');
    return { code: 0, stdout: '', stderr: '' };
  };
  await assert.rejects(provisionConnectors(ctx, { run }), /checksum mismatch/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].executable, '/usr/bin/curl');
  assert.equal(calls[0].options.env.HOME, ctx.home);
  assert.equal(Object.hasOwn(calls[0].options.env, 'GH_TOKEN'), false);
  assert.equal(calls[0].argv[calls[0].argv.indexOf('--proto-redir') + 1], '=https');
  assert.equal(calls[0].argv.some(value => value.includes('install.sh')), false);
});

test('symlinked cache paths fail before download', async t => {
  const { ctx, scratch } = await fixture(t);
  const outside = path.join(scratch, 'outside');
  await fs.mkdir(outside);
  await fs.symlink(outside, path.join(ctx.cache, 'connectors'));
  let called = false;
  await assert.rejects(provisionConnectors(ctx, { run: async () => { called = true; } }), /Unsafe/);
  assert.equal(called, false);
});

test('missing connector software is a required failed check, never an account-ready claim', async t => {
  const { ctx } = await fixture(t);
  const checks = await verifyConnectors(ctx, { run: async () => { throw new Error('must not execute absent software'); } });
  assert.equal(checks.length, 2);
  assert.ok(checks.every(check => check.status === 'failed' && check.required === true && check.detail.includes('Account NOT_CHECKED')));
});
