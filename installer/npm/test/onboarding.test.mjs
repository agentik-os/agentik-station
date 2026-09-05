import test from 'node:test';
import assert from 'node:assert/strict';
import { onboarding } from '../onboarding.mjs';

const ids = ['hermes:revision', 'hermes:tracked-source', 'hermes:imports', 'agk:controller', 'hermes:plugin-discovery'];
const core = () => ids.map(id => ({ id, status: 'verified', required: true }));
const ctx = Object.freeze({ root: '/declared/station', profile: 'station-123456789abc' });
const run = () => { throw new Error('No native command may run in these mocked onboarding tests'); };

function fixture({ answers = [true, true], results = {}, checks = core(), confirmationError = false } = {}) {
  const confirmations = [], calls = [], events = [];
  const interactive = {
    async confirm(question) {
      confirmations.push(question.message);
      if (confirmationError) throw new Error('SYNTHETIC_SECRET_FROM_PROMPT');
      return answers.shift() ?? false;
    },
    async prompt() { throw new Error('The wrapper must not collect any token or model secret'); },
  };
  const invoke = async (context, action, options) => {
    assert.equal(context, ctx);
    assert.equal(options.run, run);
    assert.equal(options.interactive, interactive);
    assert.deepEqual(Object.keys(options).sort(), ['interactive', 'run']);
    calls.push(action);
    if (results[action] instanceof Error) throw results[action];
    if (Object.hasOwn(results, action)) return results[action];
    return { action, status: action === 'activate' ? 'observed' : 'prepared', checks: [{ id: `${action}:live`, status: 'not-configured', detail: 'No live acceptance claim.' }] };
  };
  return { confirmations, calls, events, interactive, invoke, options: { checks, run, interactive, invoke, emit: event => events.push(event) } };
}

test('noninteractive and incomplete terminal adapters never prompt or invoke native setup', async () => {
  for (const interactive of [false, null, {}, { confirm() { assert.fail('must not confirm'); } }]) {
    const f = fixture();
    assert.deepEqual(await onboarding(ctx, { ...f.options, interactive }), []);
    assert.deepEqual(f.calls, []);
    assert.deepEqual(f.confirmations, []);
  }
});

for (const missing of ids) {
  test(`missing core check blocks onboarding: ${missing}`, async () => {
    const f = fixture({ checks: core().filter(check => check.id !== missing) });
    assert.deepEqual(await onboarding(ctx, f.options), []);
    assert.deepEqual(f.calls, []);
    assert.deepEqual(f.confirmations, []);
    assert.equal(f.events[0].status, 'blocked');
  });
}

for (const status of ['failed', 'blocked', 'not-configured', 'observed', 'unknown']) {
  test(`an unverified required check cannot authorize onboarding: ${status}`, async () => {
    const f = fixture({ checks: [...core(), { id: 'additional-software', required: true, status }] });
    assert.deepEqual(await onboarding(ctx, f.options), []);
    assert.deepEqual(f.calls, []);
  });
}

test('malformed, duplicate or contradictory checks fail closed', async () => {
  for (const checks of [null, {}, [], [null], [...core(), { id: ids[0], status: 'failed' }], [...core(), { id: 'extra', status: 'verified', required: 'true' }]]) {
    const f = fixture({ checks });
    assert.deepEqual(await onboarding(ctx, f.options), []);
    assert.deepEqual(f.confirmations, []);
  }
  const checks = core(); checks[0] = { id: ids[0], status: 'not-configured', required: false };
  assert.deepEqual(await onboarding(ctx, fixture({ checks }).options), []);
});

test('optional blocked capabilities remain visible without blocking verified core or being relabeled', async () => {
  const checks = [...core(), { id: 'ponytail', status: 'blocked', required: false }, { id: 'accounts', status: 'not-configured', required: false }];
  const before = structuredClone(checks);
  const f = fixture({ checks });
  const reports = await onboarding(ctx, f.options);
  assert.deepEqual(f.calls, ['model', 'configure', 'activate']);
  assert.deepEqual(reports.map(report => report.status), ['prepared', 'prepared', 'observed']);
  assert.deepEqual(checks, before);
  assert.equal(f.confirmations.length, 2);
  assert.match(f.confirmations[0], /does not start a gateway service/);
  assert.match(f.confirmations[1], /separately explains and confirms/);
  assert.equal(f.events.some(event => ['running', 'checking'].includes(event.status)), false);
});

test('declining the initial invitation returns no reports and makes no changes', async () => {
  const f = fixture({ answers: [false] });
  assert.deepEqual(await onboarding(ctx, f.options), []);
  assert.deepEqual(f.calls, []);
  assert.equal(f.confirmations.length, 1);
});

test('truthy nonboolean confirmation is not consent', async () => {
  const f = fixture({ answers: ['yes'] });
  assert.deepEqual(await onboarding(ctx, f.options), []);
  assert.deepEqual(f.calls, []);
});

test('declining activation preserves both enrollment reports without invoking a service', async () => {
  const f = fixture({ answers: [true, false] });
  const reports = await onboarding(ctx, f.options);
  assert.deepEqual(f.calls, ['model', 'configure']);
  assert.deepEqual(reports.map(report => report.action), ['model', 'configure']);
});

for (const action of ['model', 'configure']) {
  for (const status of ['cancelled', 'failed', 'blocked']) {
    test(`${action} ${status} stops all later stages and preserves its report`, async () => {
      const f = fixture({ results: { [action]: { status, checks: [] } } });
      const reports = await onboarding(ctx, f.options);
      assert.deepEqual(f.calls, action === 'model' ? ['model'] : ['model', 'configure']);
      assert.equal(reports.at(-1).action, action);
      assert.equal(reports.at(-1).status, status);
      assert.equal(f.confirmations.length, 1);
    });
  }
}

test('adapter retains its own detailed activation confirmation and may cancel it', async () => {
  const f = fixture({ answers: [true, true, false] });
  const original = f.invoke;
  f.options.invoke = async (context, action, options) => {
    if (action !== 'activate') return original(context, action, options);
    f.calls.push(action);
    assert.equal(options.interactive, f.interactive);
    const approved = await options.interactive.confirm({ message: 'Synthetic exact service/network/tool-authority review' });
    return { action, status: approved ? 'observed' : 'cancelled', checks: [] };
  };
  const reports = await onboarding(ctx, f.options);
  assert.equal(f.confirmations.length, 3);
  assert.equal(reports.at(-1).status, 'cancelled');
});

test('thrown setup errors are redacted and retain earlier stage reports', async () => {
  const secret = 'SYNTHETIC_SECRET_FROM_NATIVE_ERROR';
  for (const action of ['model', 'configure', 'activate']) {
    const f = fixture({ results: { [action]: new Error(secret) } });
    const reports = await onboarding(ctx, f.options);
    assert.equal(reports.at(-1).action, action);
    assert.equal(reports.at(-1).status, 'failed');
    assert.equal(JSON.stringify({ reports, events: f.events }).includes(secret), false);
    assert.equal(reports.length, ['model', 'configure', 'activate'].indexOf(action) + 1);
    if (action === 'activate') assert.match(reports.at(-1).checks[0].detail, /service may exist/);
  }
});

test('invalid and contradictory prepared reports never advance setup', async () => {
  for (const value of [null, {}, { status: 'ready', checks: [] }, { status: 'prepared', checks: [null] }, { status: 'prepared', checks: [{ id: 'policy', status: 'failed' }] }, { status: 'prepared', checks: [{ id: 'policy', status: 'not-configured', required: true }] }]) {
    const f = fixture({ results: { model: value } });
    const reports = await onboarding(ctx, f.options);
    assert.deepEqual(f.calls, ['model']);
    assert.equal(reports[0].status, 'failed');
  }
});

test('only declared secret-free report fields are forwarded to receipt caller', async () => {
  const f = fixture({ answers: [true, false], results: { configure: {
    action: '../../not-an-action', status: 'prepared', token: 'DO_NOT_RECORD',
    checks: [{ id: 'policy', status: 'verified', detail: 'Prepared policy.', token: 'DO_NOT_RECORD' }],
    inviteUrl: 'https://discord.com/oauth2/authorize?client_id=123', next: ['Review live acceptance.'],
  } } });
  const reports = await onboarding(ctx, f.options);
  assert.equal(reports[1].action, 'configure');
  assert.equal(JSON.stringify(reports).includes('DO_NOT_RECORD'), false);
  assert.equal(reports[1].inviteUrl, 'https://discord.com/oauth2/authorize?client_id=123');
  assert.deepEqual(reports[1].next, ['Review live acceptance.']);
});

test('confirmation interruption stops safely without recording exception text', async () => {
  const f = fixture({ confirmationError: true });
  assert.deepEqual(await onboarding(ctx, f.options), []);
  assert.deepEqual(f.calls, []);
  assert.equal(JSON.stringify(f.events).includes('SYNTHETIC_SECRET'), false);
});

test('presentation errors cannot authorize or prevent explicitly confirmed native stages', async () => {
  const f = fixture();
  const reports = await onboarding(ctx, { ...f.options, emit() { throw new Error('synthetic renderer failure'); } });
  assert.equal(reports.length, 3);
  assert.deepEqual(f.calls, ['model', 'configure', 'activate']);
});

test('missing scoped runner or adapter fails before confirmation', async () => {
  for (const override of [{ run: null }, { invoke: null }]) {
    const f = fixture();
    await assert.rejects(onboarding(ctx, { ...f.options, ...override }), /scoped command runner/);
    assert.deepEqual(f.confirmations, []);
  }
});
