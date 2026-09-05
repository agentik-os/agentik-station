// Explicit package-consumer smoke, not an npm lifecycle hook or network install.
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {run} from '../process.mjs';

const sourceRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const temp=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'stnp-')));
const env={HOME:temp,PATH:process.env.PATH || '/usr/bin:/bin',npm_config_cache:path.join(temp,'cache'),npm_config_userconfig:path.join(temp,'npmrc'),npm_config_globalconfig:path.join(temp,'globalrc'),NO_COLOR:'1',CI:'true'};
try {
  const packed=await run('npm',['pack','--ignore-scripts','--pack-destination',temp,'--json'],{cwd:sourceRoot,env,timeoutMs:120000});
  const info=JSON.parse(packed.stdout)[0], names=new Set(info.files.map(f=>f.path));
  for(const required of ['installer/npm/cli.mjs','installer/npm/supervisor.mjs','installer/npm/runtime.mjs','installer/npm/gateway.mjs','installer/npm/web.mjs','config/versions.lock','components/agk-tui/apps/agk-tui/Cargo.lock','components/agk-tui/scripts/sync-rules.py','components/agk-tui/hermes/dashboard-themes/agentik-shadcn.yaml','components/agk-tui/hermes/dashboard-themes/agentik-shadcn-light.yaml','components/agk-tui/hermes/plugins/agentik_os/dashboard/dist/index.js','components/agk-tui/hermes/plugins/agentik_os/dashboard/dist/style.css']) assert.ok(names.has(required),`Missing package runtime asset: ${required}`);
  for(const name of names) assert.ok(!/(^|\/)(\.env(?:$|\.(?!example$))|\.npmrc$|\.git\/|node_modules\/|__pycache__\/|target\/)|\.py[co]$/.test(name),`Unwanted package artifact: ${name}`);
  for(const name of ['RESOURCE.json','README.md','hermes-mcp.example.yaml','LICENSE.upstream']) assert.ok(names.has('resources/chatbotx/'+name),`Missing ChatbotX resource: ${name}`);
  const prefix=path.join(temp,'consumer');
  await run('npm',['install','--offline','--ignore-scripts','--no-audit','--no-fund','--prefix',prefix,path.join(temp,info.filename)],{cwd:temp,env,timeoutMs:120000});
  const cli=path.join(prefix,'node_modules/@agentik-os/station/installer/npm/cli.mjs');
  const root=path.join(temp,'station');
  const output=await run(process.execPath,[cli,'plan','--root',root,'--json'],{cwd:temp,env});
  assert.equal(JSON.parse(output.stdout).root,root);
  await assert.rejects(fs.stat(root),{code:'ENOENT'});
  const help=await run(path.join(prefix,'node_modules/.bin/agentik-station'),['--help'],{cwd:temp,env});
  assert.match(help.stdout,/Chief AI Officer/);
  console.log(JSON.stringify({status:'verified',package:info.id,files:info.entryCount,packedBytes:info.size,integrity:info.integrity,claims:['packed-runtime-assets','offline-consumer-install','bin-launcher','read-only-plan','no-lifecycle-hooks']},null,2));
} finally {
  // Exact newly created disposable consumer only, never an installation root.
  await fs.rm(temp,{recursive:true,force:true});
}
