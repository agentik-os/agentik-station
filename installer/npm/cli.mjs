#!/usr/bin/env node
import path from 'node:path';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createUI } from './ui.mjs';
import { createContext, initialize, inspectInstallation, acquireLock, receipt } from './state.mjs';
import { run } from './process.mjs';
import { provision, verify, prerequisites } from './runtime.mjs';
import { gateway } from './gateway.mjs';
import { terminalPrompts } from './prompts.mjs';
import { onboarding } from './onboarding.mjs';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const shellQuote = value => `'${String(value).replaceAll("'", "'\\''")}'`;
export function softwareStatus(checks) {
  if (!Array.isArray(checks) || !checks.some(c=>c.required===true)) return 'failed';
  if (checks.some(c=>c.status==='failed')) return 'failed';
  if (checks.some(c=>c.required===true && c.status!=='verified')) return 'blocked';
  return 'ready-for-setup';
}
const help = `Agentik Station · Chief AI Officer workstation

  agentik-station plan [--root /absolute/path/station]
  agentik-station install [--root PATH] [--yes]
  agentik-station verify [--root PATH]
  agentik-station repair [--root PATH] --yes
  agentik-station discord [--root PATH]
  agentik-station model [--root PATH]
  agentik-station activate [--root PATH]
  agentik-station status [--root PATH]
  agentik-station tui [--root PATH]
  agentik-station plan --mode host

Workstation: personal macOS/Linux namespace, no sudo, no resets, no shared auth.
Host: existing Linux/systemd/apt installation guide with independent-UID Zones.
No service starts during npm install or software installation. Activation is explicit.
Use --json for machine-readable plans/checks; never pass tokens as arguments.
`;
export function parseArgs(args) {
  const result = { command: 'install', mode: 'workstation', yes: false, json: false };
  if (args[0] && !args[0].startsWith('-')) result.command = args.shift();
  while (args.length) {
    const arg = args.shift();
    if (arg === '--help' || arg === '-h') result.command = 'help';
    else if (arg === '--yes') result.yes = true;
    else if (arg === '--json') result.json = true;
    else if (arg === '--root' || arg === '--mode') {
      const value = args.shift();
      if (!value || value.startsWith('-')) throw new Error(`${arg} requires a value.`);
      result[arg.slice(2)] = value;
    } else throw new Error('Unknown option; use --help. No argument value was recorded.');
  }
  if (!['install','plan','verify','repair','discord','model','activate','status','tui','help'].includes(result.command)) throw new Error('Unknown command; use --help.');
  if (!['host','workstation'].includes(result.mode)) throw new Error('Mode must be workstation or host.');
  if (result.root && !path.isAbsolute(result.root)) throw new Error('--root must be absolute.');
  return result;
}
export async function main(args = process.argv.slice(2)) {
  let ui, unlock, ctx;
  let action;
  let machine = args.includes('--json');
  try {
    const opts = parseArgs([...args]); action = opts.command; machine = opts.json;
    if (action === 'help') { process.stdout.write(opts.json ? `${JSON.stringify({help})}\n` : help); return 0; }
    if (action === 'tui' && opts.json) throw new Error('TUI requires an interactive terminal and does not support --json.');
    if (opts.mode === 'host') {
      const report = { mode: 'host', status: 'review-required', steps: [
        'Use the official Git checkout on a supported Linux/systemd/apt Host.',
        './bootstrap.sh --mode full --plan',
        'Review the plan; sudo ./bootstrap.sh --mode full',
        'Existing Host: station doctor / reviewed repair; do not rerun bootstrap blindly.',
      ], docs: 'https://github.com/agentik-os/agentik-station/blob/main/INSTALL.md' };
      process.stdout.write(opts.json ? `${JSON.stringify(report,null,2)}\n` : `${report.steps.join('\n')}\n${report.docs}\n`);
      return action === 'plan' ? 0 : 2;
    }
    ctx = await createContext({ root: opts.root, sourceRoot });
    const plan = { mode: 'workstation', root: ctx.root, platform: ctx.platform, arch: ctx.arch, profile: ctx.profile,
      steps: ['Check prerequisites and private destination', 'Install pinned Hermes, AGK and reusable tools', 'Verify native binaries, imports and plugin discovery', 'Enroll model and Discord privately (optional)', 'Review and explicitly activate the gateway'],
      warnings: ['Personal same-user namespace; not a Zone or client security boundary.', 'No existing Hermes, CLI auth, shell profile or system service is adopted.', 'Native service activation may create an account-level launchd/systemd unit; never automatic.', 'Linux Host services and external accounts have separate acceptance gates.', ...(ctx.platform==='darwin' && ctx.arch==='arm64' ? ['Known Composio 0.4.0 Mac artifact: if its signature is invalid, locally ad-hoc sign a separate verified copy; preserve upstream bytes and a transformation receipt. No Gatekeeper/security-setting changes.'] : [])] };
    if (action === 'plan' && opts.json) { process.stdout.write(`${JSON.stringify(plan,null,2)}\n`); return 0; }
    ui = opts.json ? null : createUI(); ui?.banner();
    const interactive = opts.json ? false : terminalPrompts();
    if (action === 'plan' || action === 'install' || action === 'repair') ui?.plan(plan);
    if (action === 'plan') return 0;
    if (['install','repair'].includes(action)) {
      if (process.getuid() === 0) throw new Error('Run Workstation as an ordinary user, without sudo.');
      const preflight = await prerequisites(ctx, { run });
      if (preflight.checks.some(c => c.status === 'blocked')) {
        const report = {status:'blocked',checks:preflight.checks,next:['Install the missing prerequisites using your platform package manager, then rerun plan. No installation root was created.']};
        if (opts.json) process.stdout.write(`${JSON.stringify(report,null,2)}\n`); else ui?.summary(report);
        return 1;
      }
      if (!opts.yes && !(interactive && await interactive.confirm({ message: `Install owned software in ${ctx.root}?` }))) throw new Error('No changes made. Review plan, then use --yes or an interactive terminal.');
      if (action === 'install') await initialize(ctx);
      else if (!(await inspectInstallation(ctx))) throw new Error('No recognized installation to repair.');
    } else if (!(await inspectInstallation(ctx))) throw new Error('No recognized installation. Run plan, then install.');
    if (action === 'tui') {
      ui?.close();
      await run(path.join(ctx.bin,'agk'), [], { env: { PATH: process.env.PATH || '/usr/bin:/bin', HOME: ctx.home, TERM: process.env.TERM || 'xterm-256color' }, cwd: ctx.projects, interactive: true, timeoutMs: 24*60*60_000 });
      return 0;
    }
    unlock = await acquireLock(ctx);
    const emit = event => ui?.event(event);
    let report;
    if (['install','repair','verify'].includes(action)) {
      const provisioned = action === 'verify' ? null : await provision(ctx, { run, emit });
      report = await verify(ctx, { run, emit });
      if (Array.isArray(report)) report = { checks: report };
      if (!report?.checks) throw new Error('Verifier did not return checks.');
      if (provisioned?.checks) report.checks = [...provisioned.checks, ...report.checks];
      report.status = softwareStatus(report.checks);
      report.scope = 'required-workstation-software-only';
      report.capabilityStatus = report.checks.every(c=>c.status==='verified') ? 'locally-verified' : 'incomplete';
      report.next = [shellQuote(path.join(ctx.bin,'agk')), ...['model','discord','activate'].map(command=>`agentik-station ${command} --root ${shellQuote(ctx.root)}`)];
      if (action==='install' && !opts.yes && interactive && report.status==='ready-for-setup') {
        ui?.summary(report);
        report.onboarding=await onboarding(ctx,{checks:report.checks,run,interactive,emit});
        for (const stage of report.onboarding) await receipt(ctx,`onboarding-${stage.action}`,stage);
        if (report.onboarding.some(stage=>stage.status==='failed')) report.status='failed';
      }
    } else {
      if (action === 'activate') {
        const health = await verify(ctx, { run, emit });
        const checks = Array.isArray(health) ? health : health.checks;
        const critical=['hermes:revision','hermes:imports','agk:controller','hermes:plugin:agentik_os','hermes:plugin:platforms/discord'];
        if (!Array.isArray(checks) || critical.some(id=>!checks.some(c=>c.id===id && c.status==='verified')) || checks.some(c => c.required === true && c.status !== 'verified')) throw new Error('Required software verification failed or is blocked; repair before activation.');
      }
      report = await gateway(ctx, { discord:'configure',model:'model',activate:'activate',status:'status' }[action], { run, interactive });
    }
    report ||= { status: 'not-configured', checks: [] };
    report.receipt = await receipt(ctx, action, report);
    await unlock(); unlock=null;
    if (opts.json) process.stdout.write(`${JSON.stringify(report,null,2)}\n`); else ui?.summary(report);
    return ['failed','blocked'].includes(report.status) ? 1 : 0;
  } catch (error) {
    const detail = String(error.message || error).replace(/[\x00-\x1f\x7f]/g,' ');
    if (ctx && unlock) await receipt(ctx, action, { status: 'failed', checks: [{id: action,status:'failed',detail}], next: ['Inspect this failure; use explicit repair only after addressing it.'] }).catch(() => {});
    if (machine) process.stdout.write(`${JSON.stringify({status:'failed',checks:[{id:action || 'arguments',status:'failed',detail}]},null,2)}\n`);
    else process.stderr.write(`Station: ${detail}\n`);
    return 1;
  } finally {
    try { if (unlock) await unlock(); }
    catch { process.stderr.write('Station: operation lock cleanup failed; inspect this root before another operation.\n'); }
    finally { ui?.close(); }
  }
}
// npm exposes executables through .bin/global symlinks. Compare real entrypoint
// paths so the distributed command runs, while module imports remain read-only.
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = await main();
