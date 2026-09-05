/** Explicit native acceptance. Downloads/builds software; never enrolls accounts.
 * Keeps the exact generated test directory and receipts for reviewed cleanup.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {run} from '../process.mjs';
import {atomicJSON,createContext} from '../state.mjs';
import {installationDiagnostics} from '../cli.mjs';

const sourceRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
if(process.getuid()===0) throw new Error('Native Workstation acceptance must run without sudo.');
const base=await fs.realpath(await fs.mkdtemp(path.join(process.platform==='darwin'?'/private/tmp':'/tmp','stnf.')));
const root=path.join(base,'station'), account=os.userInfo().homedir;
const protectedFiles=['.zprofile','.zshrc','.profile','.npmrc','.hermes/.env','.hermes/config.yaml','.codex/config.toml','.codex/auth.json','.codex/AGENTS.md','.claude/CLAUDE.md','.config/rmux/rmux.conf','.rustup/settings.toml','.chatbotX/config.json','.chatbotX/openapi-cache.json'];
async function fingerprint() {
  const result={};
  for(const name of protectedFiles) {
    try { const s=await fs.lstat(path.join(account,name)); result[name]=s.isFile()?createHash('sha256').update(await fs.readFile(path.join(account,name))).digest('hex'):'nonregular'; }
    catch(error) { if(error.code==='ENOENT') result[name]=null; else throw error; }
  }
  return result;
}
const before=await fingerprint();
const env={HOME:base,PATH:process.env.PATH || '/usr/bin:/bin',npm_config_cache:path.join(base,'npm-cache'),npm_config_userconfig:path.join(base,'npmrc'),npm_config_globalconfig:path.join(base,'globalrc'),NO_COLOR:'1',CI:'true'};
const result={root,scope:'native software and synthetic acceptance only',operational:false};
console.log(`NATIVE_ACCEPTANCE_ROOT=${root}`);
try {
  console.log('Packing and installing the consumer CLI...');
  const pack=JSON.parse((await run('npm',['pack','--ignore-scripts','--pack-destination',base,'--json'],{cwd:sourceRoot,env})).stdout)[0];
  result.package={id:pack.id,integrity:pack.integrity,files:pack.entryCount};
  const prefix=path.join(base,'consumer');
  await run('npm',['install','--offline','--ignore-scripts','--no-audit','--no-fund','--prefix',prefix,path.join(base,pack.filename)],{cwd:base,env});
  const packaged=path.join(prefix,'node_modules/@agentik-os/station');
  const cli=path.join(prefix,'node_modules/.bin/agentik-station');
  console.log('Installing the complete default Workstation; no accounts or gateway activation...');
  const installed=await run(cli,['install','--root',root,'--yes','--json'],{cwd:base,env:{PATH:env.PATH,HOME:account,TERM:'dumb'},timeoutMs:45*60_000,allowFailure:true});
  result.installExitCode=installed.code;
  let report;
  try {report=JSON.parse(installed.stdout);} catch {throw new Error('Native installer did not return a structured report.');}
  result.install=report;
  assert.equal(installed.code,0,'Native software install failed; inspect the retained installation receipt.');
  assert.equal(report.status,'ready-for-setup');
  assert.ok(report.checks.filter(c=>c.required===true).every(c=>c.status==='verified'));
  console.log('Verifying native service templates without creating/starting a service...');
  const ctx=await createContext({root,sourceRoot:packaged});
  const {prepareGatewayService}=await import(pathToFileURL(path.join(packaged,'installer/npm/gateway.mjs')));
  const target=process.platform==='darwin'?path.join(account,'Library/LaunchAgents',`ai.hermes.gateway-${ctx.profile}.plist`):path.join(account,'.config/systemd/user',`hermes-gateway-${ctx.profile}.service`);
  await assert.rejects(fs.lstat(target),{code:'ENOENT'});
  const definition=await prepareGatewayService(ctx,{run});
  assert.ok(definition.includes(ctx.home) && definition.includes(ctx.profile) && definition.includes('/usr/bin/env'));
  await assert.rejects(fs.lstat(target),{code:'ENOENT'});
  result.serviceTemplate='verified-without-activation';
  console.log('Checking native Hermes MCP template with synthetic tools and no network...');
  const chatbotx=await run(path.join(root,'tools/hermes/venv/bin/python'),['-I','-B',path.join(sourceRoot,'installer/npm/test/native-chatbotx-smoke.py'),root],{env:{PATH:env.PATH,HOME:base,PYTHONDONTWRITEBYTECODE:'1'},cwd:base,timeoutMs:60000});
  result.chatbotxNativeTemplate=JSON.parse(chatbotx.stdout);
  console.log('Verifying the managed update predecessor inventory...');
  const update=await import(pathToFileURL(path.join(packaged,'installer/npm/update.mjs')));
  const plan=await update.updatePlan(ctx);
  assert.equal(plan.from,ctx.release);
  result.updateBaseline='native-software-inventory-verified';
  for(const name of ['native-tui-smoke.py','native-session-smoke.py']) {
    console.log(`Running ${name} (synthetic; no models)...`);
    const native=await run(path.join(root,'tools/agk-terminal/venv/bin/python'),[path.join(sourceRoot,'installer/npm/test',name),root],{env:{PATH:env.PATH,HOME:account,PYTHONDONTWRITEBYTECODE:'1'},cwd:base,timeoutMs:180000});
    result[name]=JSON.parse(native.stdout);
  }
  result.status='verified';
} catch(error) { result.status='failed'; result.error=error.message; process.exitCode=1; }
finally {
  const after=await fingerprint();
  result.changedProtectedFiles=protectedFiles.filter(name=>before[name]!==after[name]);
  result.protectedFileCount=protectedFiles.length;
  if(result.changedProtectedFiles.length) {result.status='failed';process.exitCode=1;}
  await atomicJSON(path.join(base,'native-acceptance.json'),result,{exclusive:true});
  // CI logs need actionable bounded identifiers even when provisioning aborts
  // before verification. Full details remain in private retained evidence;
  // never print arbitrary report details, exception text or native output.
  console.log(JSON.stringify({status:result.status,root,evidence:path.join(base,'native-acceptance.json'),...installationDiagnostics(result.install,result.installExitCode),changedProtectedFiles:result.changedProtectedFiles,error:result.error?'Native acceptance failed; inspect the bounded diagnostics and retained private evidence.':undefined},null,2));
}
if (result.status === 'verified' && process.argv.includes('--update-lifecycle')) {
  console.log('Testing native update lifecycle with the same reviewed upstream versions...');
  const update = await run(process.execPath, [path.join(sourceRoot, 'installer/npm/test/native-update.mjs'), root],
    { env: { PATH: env.PATH, HOME: account, PYTHONDONTWRITEBYTECODE: '1' }, cwd: sourceRoot,
      timeoutMs: 45 * 60_000, allowFailure: true });
  if (update.code !== 0) { process.exitCode = 1; console.error('Native update lifecycle failed; preserve the private transaction evidence.'); }
  else console.log('Native update lifecycle passed; synthetic successor label, no service activation or account migration.');
}
