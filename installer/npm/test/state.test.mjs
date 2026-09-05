import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createContext, initialize, inspectInstallation, acquireLock, receipt, atomicJSON, assertSafePath } from '../state.mjs';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
async function fixture(t) {
  const parent = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'station-npm-state-')));
  t.after(() => fs.rm(parent, { recursive: true, force: true }));
  const ctx = await createContext({ root: path.join(parent, 'station with spaces'), sourceRoot });
  return { ctx, parent };
}
test('plan/context is read-only, deterministic, and supports spaces', async t => {
  const { ctx } = await fixture(t);
  await assert.rejects(fs.stat(ctx.root), { code:'ENOENT' });
  assert.match(ctx.profile, /^station-[a-f0-9]{12}$/);
  assert.equal(ctx.profile, (await createContext({root:ctx.root,sourceRoot})).profile);
  assert.equal(ctx.home, path.join(ctx.root, 'personal/home'));
  assert.match(ctx.pins.HERMES_COMMIT, /^[a-f0-9]{40}$/);
});
test('reject broad roots and unsupported platforms', async () => {
  for (const root of ['/',os.userInfo().homedir,sourceRoot,path.dirname(sourceRoot)]) await assert.rejects(createContext({root,sourceRoot}));
  await assert.rejects(createContext({root:'/nonexistent/station',sourceRoot,platform:'win32'}));
});
test('never adopt even an empty unmarked directory', async t => {
  const {ctx} = await fixture(t);
  await fs.mkdir(ctx.root,{mode:0o700});
  await assert.rejects(inspectInstallation(ctx), /not a recognized/);
  await assert.rejects(initialize(ctx));
  assert.deepEqual(await fs.readdir(ctx.root), []);
});
test('private install, immutable evidence names and concurrent operation refusal', {skip:process.getuid()===0}, async t => {
  const {ctx} = await fixture(t);
  await initialize(ctx);
  assert.equal((await fs.stat(ctx.root)).mode & 0o777,0o700);
  assert.equal((await inspectInstallation(ctx)).mode,'workstation');
  await assert.rejects(initialize(ctx), /Already installed/);
  const unlock = await acquireLock(ctx);
  await assert.rejects(acquireLock(ctx), /Another operation/);
  await unlock();
  const one=await receipt(ctx,'verify',{status:'failed'}), two=await receipt(ctx,'verify',{status:'verified'});
  assert.notEqual(one,two);
  assert.equal(JSON.parse(await fs.readFile(one,'utf8')).status,'failed');
  assert.equal((await fs.stat(one)).mode & 0o777,0o600);
});
test('reject linked roots, linked parents, hardlinks and managed directory tampering', {skip:process.getuid()===0}, async t => {
  const {ctx,parent}=await fixture(t);
  const real=path.join(parent,'real'); await fs.mkdir(real);
  await fs.symlink(real,ctx.root);
  await assert.rejects(initialize(ctx),/Unsafe path/);
  await assert.rejects(assertSafePath(path.join(ctx.root,'child')),/Unsafe path/);
  await fs.unlink(ctx.root); await initialize(ctx);
  const sentinel=path.join(real,'sentinel'); await fs.writeFile(sentinel,'untouched');
  const alias=path.join(ctx.root,'alias'); await fs.link(sentinel,alias);
  await assert.rejects(atomicJSON(alias,{bad:true}),/Hard-linked/);
  assert.equal(await fs.readFile(sentinel,'utf8'),'untouched');
  await fs.rmdir(ctx.tools); await fs.symlink(real,ctx.tools);
  await assert.rejects(inspectInstallation(ctx),/Unsafe path/);
});
test('refuse replaced context marker and broadened root permissions', {skip:process.getuid()===0}, async t => {
  const {ctx}=await fixture(t); await initialize(ctx);
  await fs.chmod(ctx.root,0o755); await assert.rejects(inspectInstallation(ctx),/private directory/);
  await fs.chmod(ctx.root,0o700);
  await atomicJSON(path.join(ctx.root,'.station-workstation.json'),{schema:1,mode:'workstation',root:ctx.root,uid:process.getuid(),profile:'default'});
  await assert.rejects(inspectInstallation(ctx),/mismatch/);
});
test('refuse a regular file substituted for a managed directory', {skip:process.getuid()===0}, async t => {
  const {ctx}=await fixture(t); await initialize(ctx);
  await fs.rmdir(ctx.tools); await fs.writeFile(ctx.tools,'not a directory');
  await assert.rejects(inspectInstallation(ctx),/private directory/);
});
test('failed serialization leaves no temporary file', async t => {
  const {parent}=await fixture(t), circular={}; circular.self=circular;
  await assert.rejects(atomicJSON(path.join(parent,'record.json'),circular));
  assert.deepEqual(await fs.readdir(parent),[]);
});
