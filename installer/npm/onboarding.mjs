/** Optional, explicitly reviewed private setup after core software verification. */
import { gateway } from './gateway.mjs';

const CORE = [
  'hermes:revision', 'hermes:tracked-source', 'hermes:imports',
  'agk:controller', 'hermes:plugin-discovery',
];
const STOP = new Set(['cancelled', 'failed', 'blocked']);

function coreVerified(checks) {
  if (!Array.isArray(checks) || !checks.length) return false;
  const byId = new Map();
  for (const check of checks) {
    if (!check || typeof check.id !== 'string' || !check.id || typeof check.status !== 'string'
      || (check.required !== undefined && typeof check.required !== 'boolean') || byId.has(check.id)) return false;
    if (check.required === true && check.status !== 'verified') return false;
    byId.set(check.id, check);
  }
  return CORE.every(id => byId.get(id)?.status === 'verified');
}

function failure(action) {
  return {
    action, status: 'failed',
    checks: [{ id: `onboarding:${action}`, status: 'failed', detail: action === 'activate'
      ? 'Activation did not complete. A namespaced service may exist; preserve its definition and inspect it before reviewed recovery. No native output or credentials were recorded.'
      : 'Private enrollment did not complete. Preserve this profile and inspect its state before retrying. No native output or credentials were recorded.' }],
  };
}

function stageReport(action, value) {
  const expected = action === 'activate' ? 'observed' : 'prepared';
  if (!value || typeof value !== 'object' || !Array.isArray(value.checks)
    || ![expected, ...STOP].includes(value.status)
    || value.checks.some(check => !check || typeof check.id !== 'string' || typeof check.status !== 'string')) return failure(action);
  // The gateway owns these secret-free reports. Do not copy arbitrary adapter
  // fields (including prompt responses) into the caller's future receipts.
  const result = { action, status: value.status, checks: value.checks.map(check => ({
    id: check.id, status: check.status,
    ...(typeof check.detail === 'string' ? { detail: check.detail } : {}),
    ...(typeof check.required === 'boolean' ? { required: check.required } : {}),
  })) };
  if (Array.isArray(value.next) && value.next.every(item => typeof item === 'string')) result.next = [...value.next];
  if (typeof value.inviteUrl === 'string') result.inviteUrl = value.inviteUrl;
  if (!STOP.has(result.status) && result.checks.some(check => ['failed', 'error', 'blocked'].includes(check.status)
    || (check.required === true && check.status !== 'verified'))) result.status = 'failed';
  return result;
}

export async function onboarding(ctx, { checks, run, interactive = false, invoke = gateway, emit = () => {} } = {}) {
  if (!interactive || typeof interactive.confirm !== 'function' || typeof interactive.prompt !== 'function') return [];
  const event = (status, message, phase = 'onboarding') => {
    // Presentation must neither authorize a step nor mask a setup result.
    try { emit({ phase, status, message }); } catch { /* no native error/secret logging */ }
  };
  if (!coreVerified(checks)) {
    event('blocked', 'Core software verification must pass before private enrollment is offered.');
    return [];
  }
  if (typeof run !== 'function' || typeof invoke !== 'function') throw new TypeError('A scoped command runner and gateway adapter are required.');
  const confirm = async message => {
    try { return await interactive.confirm({ message }) === true; }
    catch { event('cancelled', 'Optional setup was interrupted; no further step will be started.'); return false; }
  };
  if (!await confirm('Continue now with private model and Discord enrollment for this Station profile? This opens the native model wizard and a masked Discord form. Enrollment does not start a gateway service or adopt existing personal accounts.')) return [];

  const reports = [];
  const step = async action => {
    // Never animate over a native wizard or secret-entry terminal prompt.
    event('awaiting-input', action === 'activate'
      ? 'Review the adapter’s separate service, network and tool-authority confirmation.'
      : `Opening private ${action === 'model' ? 'model' : 'Discord'} enrollment; no gateway service is started.`, `onboarding:${action}`);
    let report;
    try { report = stageReport(action, await invoke(ctx, action, { run, interactive })); }
    catch { report = failure(action); }
    reports.push(report);
    event(report.status, STOP.has(report.status)
      ? 'This step did not complete; no later onboarding step will be started.'
      : 'Step returned its scoped checks; account and live-service acceptance remain separate.', `onboarding:${action}`);
    return !STOP.has(report.status);
  };

  if (!await step('model') || !await step('configure')) return reports;
  if (!await confirm('Review gateway activation now? The next step separately explains and confirms the exact service, network access and account-level tool authority. Declining will not start a gateway from this onboarding flow; account and live-chat acceptance are still separate.')) return reports;
  await step('activate'); // The adapter retains its own mandatory detailed confirmation.
  return reports;
}
