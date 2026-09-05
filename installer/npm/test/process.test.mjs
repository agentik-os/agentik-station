import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { run } from '../process.mjs';

test('argv stays literal; ambient secrets do not enter child environment', async () => {
  process.env.STATION_TEST_PRIVATE = 'do-not-inherit';
  try {
    const result = await run(process.execPath,['-e','console.log(JSON.stringify([process.argv[1],process.env.STATION_TEST_PRIVATE,process.env.HOME]))','$(touch /never-execute)'],{env:{HOME:'/declared/home'}});
    assert.deepEqual(JSON.parse(result.stdout),['$(touch /never-execute)',null,'/declared/home']);
  } finally { delete process.env.STATION_TEST_PRIVATE; }
});
test('failure output and argv never leak into error text', async () => {
  await assert.rejects(run(process.execPath,['-e','console.error("SECRET"); process.exit(7)','TOKEN']),error=> !error.message.includes('SECRET') && !error.message.includes('TOKEN') && error.message.includes('exit 7'));
  const result=await run(process.execPath,['-e','process.exit(7)'],{allowFailure:true}); assert.equal(result.code,7);
});
test('missing binary, timeout, and output overflow fail boundedly', async () => {
  await assert.rejects(run('/no/such/station-binary',[]),/Cannot run/);
  await assert.rejects(run(process.execPath,['-e','setInterval(()=>{},1000)'],{timeoutMs:50}),/timeout/);
  await assert.rejects(run(process.execPath,['-e','process.stdout.write("x".repeat(2*1024*1024))']),/output limit/);
});

// These are our own short-lived fixtures, never a user gateway or RMUX session.
function running(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 1) return false;
  const result = spawnSync('/bin/ps', ['-o', 'stat=', '-p', String(pid)], { encoding: 'utf8' });
  if (result.error) throw result.error;
  return result.status === 0 && Boolean(result.stdout.trim()) && !result.stdout.trim().startsWith('Z');
}

async function eventually(check, message) {
  const deadline = Date.now() + 4000;
  while (Date.now() < deadline) {
    if (await check()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.fail(message);
}

async function treeFixture(t, { linger = false, ignoreTerm = false, ignoreLeaderTerm = false, detached = false } = {}) {
  const directory = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'station-process-tree-')));
  const pidFile = path.join(directory, 'owned-descendant.pid');
  let descendant;
  t.after(async () => {
    if (!descendant) descendant = Number(await fs.readFile(pidFile, 'utf8').catch(() => ''));
    if (running(descendant)) { try { process.kill(descendant, 'SIGKILL'); } catch {} }
    await fs.rm(directory, { recursive: true, force: true });
  });
  const grandchild = `${ignoreTerm ? "process.on('SIGTERM',()=>{});" : ''}require('node:fs').writeFileSync(${JSON.stringify(pidFile)},String(process.pid),{mode:0o600});setInterval(()=>{},1000);`;
  const code = `const {spawn}=require('node:child_process');${ignoreLeaderTerm ? "process.on('SIGTERM',()=>{});" : ''}const child=spawn(process.execPath,['-e',${JSON.stringify(grandchild)}],{stdio:${JSON.stringify(detached ? 'inherit' : 'ignore')},detached:${detached}});child.unref();${linger ? 'setInterval(()=>{},1000);' : `const fs=require('node:fs');const timer=setInterval(()=>{if(fs.existsSync(${JSON.stringify(pidFile)})){clearInterval(timer);console.log(child.pid);}},5);`}`;
  return {
    directory, code,
    async pid() {
      await eventually(async () => {
        descendant = Number(await fs.readFile(pidFile, 'utf8').catch(() => ''));
        return Number.isSafeInteger(descendant) && descendant > 1;
      }, 'synthetic descendant did not initialize');
      return descendant;
    },
  };
}

test('normal success kills owned same-group descendants even with closed stdio', async t => {
  const fixture = await treeFixture(t);
  const result = await run(process.execPath, ['-e', fixture.code], { env: {}, cwd: fixture.directory, timeoutMs: 4000 });
  assert.equal(result.code, 0);
  const pid = await fixture.pid();
  assert.equal(Number(result.stdout.trim()), pid);
  await eventually(() => !running(pid), 'successful run left its synthetic descendant running');
});

test('an escaped session cannot keep capture pipes and stale group timers alive', async t => {
  const fixture = await treeFixture(t, { detached: true });
  const pending = run(process.execPath, ['-e', fixture.code], { env: {}, cwd: fixture.directory, timeoutMs: 4000 });
  // The escaped PID is intentionally beyond process-group containment and is
  // cleaned by this test's owned fixture, not adopted by the runner.
  const pid = await fixture.pid();
  const outcome = await Promise.race([
    pending.then(result => ({ result }), error => ({ error })),
    new Promise(resolve => setTimeout(() => resolve({ stalled: true }), 1000)),
  ]);
  assert.equal(outcome.stalled, undefined, 'run waited on an escaped descendant after its supervisor had exited');
  assert.equal(running(pid), true, 'runner must not claim to contain another session');
});

test('timeout kills TERM-ignoring owned descendants after their leader closes', async t => {
  const fixture = await treeFixture(t, { linger: true, ignoreTerm: true });
  const pending = run(process.execPath, ['-e', fixture.code], { env: {}, cwd: fixture.directory, timeoutMs: 1200 });
  const rejection = assert.rejects(pending, /timeout/);
  const pid = await fixture.pid();
  await rejection;
  await eventually(() => !running(pid), 'timeout left a TERM-ignoring descendant running');
});

test('timeout escalates when both native leader and its descendant ignore TERM', async t => {
  const fixture = await treeFixture(t, { linger: true, ignoreTerm: true, ignoreLeaderTerm: true });
  const pending = run(process.execPath, ['-e', fixture.code], { env: {}, cwd: fixture.directory, timeoutMs: 1200 });
  const rejection = assert.rejects(pending, /timeout/);
  const pid = await fixture.pid();
  await rejection;
  await eventually(() => !running(pid), 'escalation left a TERM-ignoring descendant running');
});

for (const signal of ['SIGINT', 'SIGTERM', 'SIGKILL']) {
  test(`supervised tree is cleaned when its isolated runner receives ${signal}`, async t => {
    const fixture = await treeFixture(t, { linger: true, ignoreTerm: true });
    const moduleURL = new URL('../process.mjs', import.meta.url).href;
    const script = `import {run} from ${JSON.stringify(moduleURL)};try{await run(process.execPath,['-e',${JSON.stringify(fixture.code)}],{env:{},cwd:${JSON.stringify(fixture.directory)},timeoutMs:10000});process.exitCode=2;}catch(error){console.log(error.message);process.exitCode=3;}`;
    const runner = spawn(process.execPath, ['--input-type=module', '-e', script], { env: {}, cwd: fixture.directory, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '';
    runner.stdout.on('data', chunk => { output += chunk.toString(); });
    runner.stderr.resume();
    t.after(() => { if (runner.exitCode === null && runner.signalCode === null) runner.kill('SIGKILL'); });
    const exited = new Promise((resolve, reject) => { runner.once('error', reject); runner.once('close', (code, observedSignal) => resolve({ code, signal: observedSignal })); });
    const pid = await fixture.pid();
    assert.equal(runner.kill(signal), true);
    const result = await exited;
    if (signal === 'SIGKILL') assert.equal(result.signal, 'SIGKILL');
    else { assert.equal(result.code, 3); assert.match(output, /interrupted/); }
    await eventually(() => !running(pid), `${signal} left the owned descendant running`);
  });
}
