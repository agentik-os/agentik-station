/** Shared native web workers, installed in the declared personal namespace. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { assertSafePath, atomicJSON, readJSON } from './state.mjs';

export function webPaths(ctx, component) {
  const key = { crawl4ai: 'CRAWL4AI_PYTHON_VERSION', scrapegraphai: 'SCRAPEGRAPHAI_VERSION' }[component];
  if (!key) throw new Error('Unknown web component.');
  const values = [ctx.pins[key],ctx.pins.AI_PYTHON_VERSION,ctx.pins.PLAYWRIGHT_VERSION];
  if (values.some(v => typeof v !== 'string' || !/^\d+\.\d+\.\d+$/.test(v))) throw new Error('Invalid web runtime pins.');
  const root = path.join(ctx.tools,'web',`${component}-${values[0]}-py${values[1]}-pw${values[2]}`);
  return { root, python:path.join(root,'venv/bin/python'), browsers:path.join(root,'browsers'), tokenizers:path.join(root,'tokenizers'), version:values[0] };
}
function environment(ctx, base, paths) {
  return {...base, STATION_WORKSTATION_ROOT:ctx.root, PLAYWRIGHT_BROWSERS_PATH:paths.browsers,
    TIKTOKEN_CACHE_DIR:paths.tokenizers, SCRAPEGRAPHAI_TELEMETRY_ENABLED:'false'};
}
export async function provisionWeb(ctx,{run,emit=()=>{},uv,env}) {
  for (const component of ['crawl4ai','scrapegraphai']) {
    const p=webPaths(ctx,component), marker=path.join(p.root,'.station-web-runtime.json');
    await assertSafePath(p.root);
    let existing=false;
    try { await fs.lstat(p.root); existing=true; } catch(error) { if(error.code!=='ENOENT') throw error; }
    const record={schema:1,root:ctx.root,component,version:p.version,python:ctx.pins.AI_PYTHON_VERSION,playwright:ctx.pins.PLAYWRIGHT_VERSION};
    if(existing) {
      if(JSON.stringify(await readJSON(marker))!==JSON.stringify(record)) throw new Error('Existing web runtime is not the exact owned deployment; review before repair.');
    } else {
      await fs.mkdir(p.root,{recursive:true,mode:0o700});
      await atomicJSON(marker,record,{exclusive:true});
    }
    const scoped=environment(ctx,env,p);
    emit({phase:component,status:'running',message:'Installing pinned Python library and private Chromium; no provider requests'});
    for(const dir of [p.browsers,p.tokenizers]) { await assertSafePath(dir); await fs.mkdir(dir,{recursive:true,mode:0o700}); }
    await assertSafePath(path.join(p.root,'venv'));
    await run(uv,['venv','--allow-existing','--python',ctx.pins.AI_PYTHON_VERSION,path.join(p.root,'venv')],{env:scoped,timeoutMs:300000});
    await run(uv,['pip','install','--python',p.python,`${component}==${p.version}`,`playwright==${ctx.pins.PLAYWRIGHT_VERSION}`],{env:scoped,timeoutMs:1200000});
    await run(p.python,['-m','playwright','install','chromium'],{env:scoped,timeoutMs:600000});
    if(component==='scrapegraphai') await run(p.python,['-c',"import tiktoken; tiktoken.get_encoding('o200k_base'); tiktoken.get_encoding('cl100k_base')"],{env:scoped,timeoutMs:180000});
    emit({phase:component,status:'prepared',message:'Private worker installed; real import/browser checks follow'});
  }
}
export async function verifyWeb(ctx,{run,emit=()=>{},env}) {
  const checks=[];
  const runnerDir=path.join(ctx.tools,'agk-terminal/hermes/plugins/agentik_os');
  for(const component of ['crawl4ai','scrapegraphai']) {
    const p=webPaths(ctx,component);
    let success=false;
    try {
      // Execute the exact shipped health contract: real imports + a real browser
      // launch. No page navigation, LLM request, or inherited credentials.
      const code="import json,sys; sys.path.insert(0,sys.argv[1]); from scrapegraph_runner import extract; result=extract({'component':sys.argv[2],'health':True}); print('STATION_WEB_HEALTH='+json.dumps(result))";
      const result=await run(p.python,['-I','-B','-c',code,runnerDir,component],{env:environment(ctx,env,p),cwd:ctx.projects,timeoutMs:180000,allowFailure:true});
      const line=result.stdout.split('\n').find(l=>l.startsWith('STATION_WEB_HEALTH='));
      const payload=line && JSON.parse(line.slice('STATION_WEB_HEALTH='.length));
      success=result.code===0 && payload?.success===true && payload?.component===component && payload?.browser==='launch-passed';
    } catch { /* Return a failing gate, never manufacture installation readiness. */ }
    checks.push({id:`web:${component}`,required:true,status:success?'verified':'failed',detail:success?'Pinned library imports and private Chromium launch passed; external extraction/account acceptance remains separate.':'Worker/browser health failed. Repair this owned runtime; on Linux inspect missing Chromium system libraries (no automatic sudo).'});
    emit({phase:'verify',status:checks.at(-1).status,message:`web:${component}`});
  }
  return checks;
}
