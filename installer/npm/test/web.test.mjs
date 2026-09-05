import test from 'node:test';
import assert from 'node:assert/strict';
import {webPaths,verifyWeb} from '../web.mjs';

const ctx={root:'/owned/station',tools:'/owned/station/tools',projects:'/owned/station/projects',pins:{CRAWL4AI_PYTHON_VERSION:'0.9.3',SCRAPEGRAPHAI_VERSION:'2.2.2',AI_PYTHON_VERSION:'3.13.15',PLAYWRIGHT_VERSION:'1.62.0'}};
test('web worker layout matches the native plugin contract and refuses unknown pins',()=>{
  assert.equal(webPaths(ctx,'crawl4ai').root,'/owned/station/tools/web/crawl4ai-0.9.3-py3.13.15-pw1.62.0');
  assert.throws(()=>webPaths(ctx,'unknown'));
  assert.throws(()=>webPaths({...ctx,pins:{...ctx.pins,AI_PYTHON_VERSION:'../../wrong'}},'crawl4ai'));
});
test('real health protocol required; captured native output is not evidence',async()=>{
  const calls=[];
  const checks=await verifyWeb(ctx,{env:{HOME:'/owned/station/personal/home'},run:async(bin,args,opts)=>{
    calls.push({bin,args,opts});
    return {code:0,stdout:'STATION_WEB_HEALTH='+JSON.stringify({success:true,component:args.at(-1),browser:'launch-passed'}),stderr:'SECRET'};
  }});
  assert.ok(checks.every(c=>c.status==='verified'));
  assert.equal(calls.length,2);
  assert.equal(calls[0].opts.env.STATION_WORKSTATION_ROOT,ctx.root);
  assert.ok(!JSON.stringify(checks).includes('SECRET'));
});
test('a missing browser or malformed response cannot pass verification',async()=>{
  for(const stdout of ['','success','STATION_WEB_HEALTH={"success":true}']) {
    const checks=await verifyWeb(ctx,{env:{},run:async()=>({code:0,stdout,stderr:''})});
    assert.ok(checks.every(c=>c.status==='failed'));
  }
});
