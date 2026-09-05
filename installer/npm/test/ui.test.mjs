import assert from 'node:assert/strict';
import test from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';
import { createUI } from '../ui.mjs';

function stream({ tty = false, columns = 100 } = {}) {
  return { isTTY: tty, columns, output: '', write(value) { this.output += value; return true; } };
}

function fixture(options = {}, env = {}) {
  const stdout = stream(options);
  const stderr = stream(options);
  return { stdout, stderr, ui: createUI({ stdout, stderr, env }) };
}

const plan = {
  mode: 'workstation', root: '/station', platform: 'linux', arch: 'x64',
  profile: 'personal', steps: ['Prepare directories', 'Verify pinned runtimes'],
  warnings: ['Accounts are not configured.'],
};

function stripColors(value) { return value.replace(/\u001b\[[0-9;]*m/g, ''); }

test('plain output shows actual plan and statuses without ANSI or invented completion', () => {
  const { ui, stdout, stderr } = fixture();
  ui.banner();
  ui.plan(plan);
  ui.event({ phase: 'runtime', status: 'running', message: 'Checking local binaries' });
  ui.event({ phase: 'account', status: 'not-configured', message: 'Explicit login required' });
  ui.summary({ status: 'prepared', checks: [{ id: 'Hermes', status: 'verified', detail: 'Revision matches' },
    { id: 'Discord', status: 'not-configured', detail: 'No bot connected' }],
    next: ['Review the configuration'], receipt: '/station/evidence/check.json' });
  ui.close();
  assert.match(stdout.output, /A G E N T I K/);
  assert.match(stdout.output, /Chief AI Officer installer/);
  assert.match(stdout.output, /01  Prepare directories/);
  assert.match(stdout.output, /\[RUNNING\] runtime/);
  assert.match(stdout.output, /\[NOT-CONFIGURED\] Discord/);
  assert.match(stdout.output, /RESULT \/ PREPARED/);
  assert.match(stdout.output, /Receipt: \/station\/evidence\/check.json/);
  assert.doesNotMatch(stdout.output + stderr.output, /\u001b|\r|100%|\[READY\]/);
});

test('TTY branding uses a code-native gradient and balanced color resets', () => {
  const { ui, stdout } = fixture({ tty: true }, { STATION_NO_ANIMATION: '1' });
  ui.banner();
  assert.match(stdout.output, /\u001b\[38;2;82;214;220m/);
  assert.match(stdout.output, /\u001b\[38;2;179;141;250m/);
  assert.match(stripColors(stdout.output), /S T A T I O N/);
  assert.ok(stdout.output.endsWith('\u001b[0m\n'));
  ui.close();
});

for (const env of [{ NO_COLOR: '' }, { FORCE_COLOR: '0' }, { CI: 'true' }, { TERM: 'dumb' }]) {
  test(`accessibility controls disable colors and cursor animation: ${JSON.stringify(env)}`, async () => {
    const { ui, stdout } = fixture({ tty: true }, env);
    ui.banner();
    ui.event({ phase: 'runtime', status: 'running', message: 'Verifying' });
    const before = stdout.output;
    await delay(110);
    ui.close();
    assert.equal(stdout.output, before);
    assert.doesNotMatch(stdout.output, /\u001b|\r/);
  });
}

test('FORCE_COLOR does not add escape codes to redirected output', () => {
  const { ui, stdout } = fixture({}, { FORCE_COLOR: '1' });
  ui.banner();
  ui.event({ status: 'running' });
  ui.close();
  assert.doesNotMatch(stdout.output, /\u001b|\r/);
});

test('STATION_NO_ANIMATION preserves TTY color but never rewrites a line', async () => {
  const { ui, stdout } = fixture({ tty: true }, { STATION_NO_ANIMATION: '1' });
  ui.event({ phase: 'runtime', status: 'running' });
  const before = stdout.output;
  await delay(110);
  ui.close();
  assert.equal(stdout.output, before);
  assert.match(stdout.output, /\u001b\[38;2;/);
  assert.doesNotMatch(stdout.output, /\r|\u001b\[2K/);
});

test('narrow terminals have compact branding and bounded lines', () => {
  const { ui, stdout } = fixture({ tty: true, columns: 24 }, { NO_COLOR: '' });
  ui.banner();
  ui.plan({ ...plan, root: '/station/' + 'very-long-directory/'.repeat(30) });
  ui.event({ phase: 'long verification phase', status: 'running', message: 'x'.repeat(5000) });
  ui.summary({ status: 'prepared', checks: [{ id: 'c'.repeat(100), status: 'not-configured' }], next: ['n'.repeat(100)] });
  ui.close();
  assert.match(stdout.output, /AGENTIK\nSTATION\n/);
  assert.ok(stdout.output.split('\n').every((line) => Array.from(line).length <= 24));
});

test('wide CJK text does not overflow a narrow terminal', () => {
  const { ui, stdout } = fixture({ tty: true, columns: 20 }, { NO_COLOR: '' });
  ui.plan({ root: '界'.repeat(50), steps: [] });
  ui.close();
  for (const line of stdout.output.split('\n')) {
    const width = Array.from(line).reduce((sum, character) => sum + (character === '界' ? 2 : 1), 0);
    assert.ok(width <= 20, line);
  }
});

test('nonTTY output preserves long paths and repair instructions for copying', () => {
  const { ui, stdout } = fixture();
  const path = '/station/' + 'nested/'.repeat(35) + 'receipt.json';
  const instruction = 'Review ' + 'the actual report and its checks '.repeat(8);
  ui.plan({ ...plan, root: path });
  ui.summary({ status: 'blocked', receipt: path, next: [instruction] });
  ui.close();
  assert.ok(stdout.output.includes(`Root: ${path}\n`));
  assert.ok(stdout.output.includes(`Receipt: ${path}\n`));
  assert.ok(stdout.output.includes(`1. ${instruction.trim()}\n`));
});

test('TTY wraps rather than loses the receipt path and next instruction', () => {
  const { ui, stdout } = fixture({ tty: true, columns: 20 }, { NO_COLOR: '' });
  const path = '/station/reports/long-report/receipt.json';
  ui.summary({ status: 'blocked', receipt: path, next: ['Review the report before retrying.'] });
  ui.close();
  assert.ok(stdout.output.replaceAll('\n', '').includes(`Receipt: ${path}`));
  assert.ok(stdout.output.replaceAll('\n', '').includes('1. Review the report before retrying.'));
});

test('all dynamic surfaces remove terminal commands, forged lines, and bidi controls', () => {
  const payload = '\u001b]52;c;STOLEN\u0007\u001b[2J\u001b[?25l\u202eunsafe\r\nFORGED\u009b31m';
  const { ui, stdout, stderr } = fixture();
  ui.plan({ mode: payload, root: payload, platform: payload, arch: payload,
    profile: payload, steps: [payload], warnings: [payload] });
  ui.event({ phase: payload, status: payload, message: payload });
  ui.event({ phase: payload, status: 'failed', message: payload });
  ui.summary({ status: payload, checks: [{ id: payload, status: payload, detail: payload }],
    next: [payload], receipt: payload });
  ui.close();
  const output = stdout.output + stderr.output;
  assert.doesNotMatch(output, /\u001b|[\u0000-\u0009\u000b-\u001f\u007f-\u009f\u202e]|STOLEN/);
  assert.doesNotMatch(output, /^FORGED/m);
  assert.match(output, /unsafe FORGED/);
});

for (const payload of ['\u001b]52;secret', '\u001bPsecret', '\u009d52;secret', '\u0090secret']) {
  test(`unterminated terminal sequence is discarded: ${JSON.stringify(payload)}`, () => {
    const { ui, stdout } = fixture();
    ui.event({ phase: 'safe', status: 'pending', message: payload });
    ui.close();
    assert.doesNotMatch(stdout.output, /secret|\u001b|\u0090|\u009d/);
  });
}

test('failed and blocked events use stderr, never a successful summary headline', () => {
  const { ui, stdout, stderr } = fixture();
  ui.event({ phase: 'runtime', status: 'failed', message: 'Missing dependency' });
  ui.event({ phase: 'account', status: 'blocked', message: 'Login required' });
  ui.summary({ status: 'verified', checks: [{ id: 'runtime', status: 'failed' }] });
  assert.match(stderr.output, /\[FAILED\] runtime/);
  assert.match(stderr.output, /\[BLOCKED\] account/);
  assert.match(stdout.output, /RESULT \/ FAILED/);
  assert.doesNotMatch(stdout.output, /RESULT \/ VERIFIED/);
  ui.close();
});

test('spinner tracks only a running event and close is idempotent with safe cursor cleanup', async () => {
  const { ui, stdout } = fixture({ tty: true });
  const listenerCount = process.listenerCount('SIGINT');
  ui.event({ phase: 'runtime', status: 'running', message: 'Actual operation pending' });
  await delay(120);
  assert.match(stdout.output, /\r\u001b\[2K/);
  ui.close();
  const final = stdout.output;
  assert.ok(final.endsWith('\n'));
  assert.doesNotMatch(final, /\u001b\[\?25[lh]|VERIFIED|COMPLETE/);
  assert.equal(process.listenerCount('SIGINT'), listenerCount);
  ui.close();
  ui.banner();
  ui.event({ status: 'verified' });
  await delay(120);
  assert.equal(stdout.output, final);
});

test('completed events stop animation without pretending a skipped step succeeded', async () => {
  const { ui, stdout } = fixture({ tty: true });
  ui.event({ phase: 'optional', status: 'running' });
  ui.event({ phase: 'optional', status: 'skipped', message: 'Unsupported platform' });
  const before = stdout.output;
  await delay(120);
  assert.equal(stdout.output, before);
  assert.match(stripColors(stdout.output), /\[SKIPPED\] optional/);
  assert.doesNotMatch(stripColors(stdout.output), /VERIFIED|READY/);
  ui.close();
});

test('output failure disables presentation and its timer without throwing', async () => {
  let attempts = 0;
  const stdout = { isTTY: true, columns: 80, write() { attempts++; throw new Error('EPIPE'); } };
  const ui = createUI({ stdout, stderr: stream(), env: {} });
  assert.doesNotThrow(() => ui.event({ status: 'running' }));
  await delay(120);
  ui.close();
  assert.equal(attempts, 1);
});

test('backpressure pauses animation instead of buffering an unbounded spinner', async () => {
  let attempts = 0;
  const stdout = { isTTY: true, columns: 80, write() { attempts++; return false; } };
  const ui = createUI({ stdout, stderr: stream(), env: {} });
  ui.event({ status: 'running' });
  await delay(120);
  assert.equal(attempts, 1);
  ui.close();
  assert.equal(attempts, 2);
});
