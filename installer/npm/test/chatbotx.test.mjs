import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { installCLIs, verifyChatbotX, runtimePaths } from '../runtime.mjs';
import { installationDiagnostics } from '../cli.mjs';
import { run } from '../process.mjs';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const pins = Object.fromEntries((await fs.readFile(path.join(sourceRoot, 'config/versions.lock'), 'utf8')).trim().split('\n').map(line => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]));
const packages = {
  vercel: ['VERCEL_CLI_VERSION', 'VERCEL_CLI_INTEGRITY', 'vercel'],
  '@openai/codex': ['CODEX_CLI_VERSION', 'CODEX_CLI_INTEGRITY', 'codex'],
  shadcn: ['SHADCN_CLI_VERSION', 'SHADCN_CLI_INTEGRITY', 'shadcn'],
  chatbotx: ['CHATBOTX_CLI_VERSION', 'CHATBOTX_CLI_NPM_INTEGRITY', 'chatbotx'],
  'discord.js': ['DISCORD_JS_VERSION', 'DISCORD_JS_INTEGRITY', null],
};

async function fixture(t) {
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'station-chatbotx-test-')));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const ctx = {root,sourceRoot,pins:{...pins},platform:process.platform,arch:process.arch,profile:'station-test',accountHome:path.join(root,'real-account'),
    ...Object.fromEntries(['home','bin','tools','cache','evidence','resources','projects'].map(name=>[name,path.join(root,name)]))};
  ctx.hermesHome = path.join(ctx.home,'.hermes');
  for (const key of ['home','bin','cache','resources','projects','accountHome']) await fs.mkdir(ctx[key],{mode:0o700,recursive:true});
  return ctx;
}

async function installFixture(ctx, {wrongIntegrity=false}={}) {
  const p=runtimePaths(ctx), calls=[];
  const installer=async (bin,args,options)=>{
    calls.push({bin,args,options});
    const manifest=JSON.parse(await fs.readFile(path.join(p.npm,'package.json'),'utf8'));
    assert.equal(manifest.dependencies.chatbotx,pins.CHATBOTX_CLI_VERSION);
    const lock={packages:{}};
    for(const [name,[version,integrity,command]] of Object.entries(packages)) {
      const directory=path.join(p.npm,'node_modules',name);
      await fs.mkdir(path.join(directory,'dist'),{recursive:true,mode:0o700});
      await fs.writeFile(path.join(directory,'package.json'),JSON.stringify({name,version:pins[version],...(command?{bin:{[command]:'./dist/index.cjs'}}:{})}));
      // Deliberately lacks a shebang, just like the exact published ChatbotX CLI.
      await fs.writeFile(path.join(directory,'dist/index.cjs'),`const fs=require('node:fs');const path=require('node:path');const os=require('node:os');
if(process.argv.includes('--version'))console.log(fs.existsSync(path.join(os.homedir(),'.chatbotX/config.json'))?'0.1.0':${JSON.stringify(pins[version])});
else if(process.argv.includes('--help'))console.log('config set: synthetic local help');
else if(process.argv.includes('--fixture-state')){fs.writeFileSync(path.join(os.homedir(),'created.json'),JSON.stringify({home:os.homedir(),ambientToken:!!process.env.CHATBOTX_API_KEY}));}
`);
      if (name==='chatbotx') ctx.pins.CHATBOTX_CLI_ENTRY_SHA256=createHash('sha256').update(await fs.readFile(path.join(directory,'dist/index.cjs'))).digest('hex');
      lock.packages['node_modules/'+name]={version:pins[version],integrity:wrongIntegrity&&name==='chatbotx'?'wrong':pins[integrity]};
    }
    await fs.writeFile(path.join(p.npm,'package-lock.json'),JSON.stringify(lock));
    return {code:0,stdout:'',stderr:''};
  };
  await installCLIs(ctx,{npm:'/synthetic/npm'},installer);
  return calls;
}

test('default CLI install includes pinned ChatbotX, complete resource and explicit Node wrapper without hooks', async t=>{
  const ctx=await fixture(t), calls=await installFixture(ctx);
  assert.equal(calls.length,1);
  assert.ok(calls[0].args.includes('--ignore-scripts'));
  assert.equal(calls[0].options.env.HOME,ctx.home);
  const wrapper=await fs.readFile(path.join(ctx.bin,'chatbotx'),'utf8');
  assert.ok(wrapper.includes(process.execPath));
  assert.ok(wrapper.includes('umask 077'));
  assert.ok(wrapper.includes('/chatbotx/dist/index.cjs'));
  for(const name of ['RESOURCE.json','README.md','hermes-mcp.example.yaml','LICENSE.upstream']) assert.equal(await fs.readFile(path.join(ctx.resources,'chatbotx',name),'utf8'),await fs.readFile(path.join(sourceRoot,'resources/chatbotx',name),'utf8'));
});

test('ChatbotX wrapper supports shebang-free package, private file modes and no ambient credentials', async t=>{
  const ctx=await fixture(t); await installFixture(ctx);
  const result=await run(path.join(ctx.bin,'chatbotx'),['--fixture-state'],{env:{HOME:ctx.accountHome,CHATBOTX_API_KEY:'SYNTHETIC_NOT_REAL',PATH:'/usr/bin:/bin'},cwd:ctx.projects});
  assert.equal(result.code,0);
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(ctx.home,'created.json'),'utf8')),{home:ctx.home,ambientToken:false});
  assert.equal((await fs.stat(path.join(ctx.home,'created.json'))).mode&0o777,0o600);
  assert.deepEqual(await fs.readdir(ctx.accountHome),[]);
});

test('ChatbotX verification bypasses configured account version branch and leaves private config unchanged', async t=>{
  const ctx=await fixture(t); await installFixture(ctx);
  const configDir=path.join(ctx.home,'.chatbotX'); await fs.mkdir(configDir,{mode:0o700});
  const config=path.join(configDir,'config.json'); await fs.writeFile(config,'SYNTHETIC_PRIVATE_SENTINEL',{mode:0o600});
  const calls=[];
  const check=await verifyChatbotX(ctx,{run:async(bin,args,options)=>{calls.push({bin,args,options});return run(bin,args,options);}});
  assert.equal(check.status,'verified');
  assert.equal(check.required,true);
  assert.equal(calls.length,2);
  assert.ok(calls.every(c=>c.bin===process.execPath&&c.options.env.HOME!==ctx.home&&c.options.env.HOME.startsWith(ctx.cache)));
  assert.ok(calls.every(c=>!('CHATBOTX_API_KEY' in c.options.env)&&!('NODE_OPTIONS' in c.options.env)));
  assert.equal(await fs.readFile(config,'utf8'),'SYNTHETIC_PRIVATE_SENTINEL');
  assert.deepEqual(await fs.readdir(ctx.cache),[]);
});

test('ChatbotX package integrity mismatch fails installation before publishing its launcher',async t=>{
  const ctx=await fixture(t);
  await assert.rejects(installFixture(ctx,{wrongIntegrity:true}),/reviewed integrity: chatbotx/);
  await assert.rejects(fs.lstat(path.join(ctx.bin,'chatbotx')),{code:'ENOENT'});
});

test('changed or substituted ChatbotX launcher is failed evidence before a native probe',async t=>{
  const ctx=await fixture(t); await installFixture(ctx);
  const wrapper=path.join(ctx.bin,'chatbotx');
  await fs.writeFile(wrapper,'changed');
  let calls=0;
  assert.equal((await verifyChatbotX(ctx,{run:async()=>{calls++;}})).status,'failed');
  await fs.unlink(wrapper); await fs.symlink('/bin/false',wrapper);
  assert.equal((await verifyChatbotX(ctx,{run:async()=>{calls++;}})).status,'failed');
  assert.equal(calls,0);
});

test('failed ChatbotX native check stays required, redacted and diagnostic-visible',async t=>{
  const ctx=await fixture(t); await installFixture(ctx);
  const check=await verifyChatbotX(ctx,{run:async()=>({code:1,stdout:'SYNTHETIC_SECRET',stderr:'SYNTHETIC_SECRET'})});
  assert.equal(check.status,'failed'); assert.equal(check.required,true);
  assert.equal(JSON.stringify(check).includes('SYNTHETIC_SECRET'),false);
  assert.deepEqual(installationDiagnostics({status:'failed',phase:'verify',checks:[check]},1).failedRequiredChecks,[{id:'cli:chatbotx',status:'failed'}]);
  assert.deepEqual(await fs.readdir(ctx.cache),[]);
});

test('modified regular ChatbotX executable is rejected before native execution',async t=>{
  const ctx=await fixture(t); await installFixture(ctx);
  await fs.appendFile(path.join(runtimePaths(ctx).npm,'node_modules/chatbotx/dist/index.cjs'),'\n// modified bytes\n');
  let calls=0;
  assert.equal((await verifyChatbotX(ctx,{run:async()=>{calls++;}})).status,'failed');
  assert.equal(calls,0);
});

test('copied ChatbotX resource drift or missing notice is rejected before native execution',async t=>{
  const ctx=await fixture(t); await installFixture(ctx);
  const template=path.join(ctx.resources,'chatbotx/hermes-mcp.example.yaml');
  const original=await fs.readFile(template);
  await fs.writeFile(template,original.toString().replace('enabled: false','enabled: true'));
  let calls=0;
  assert.equal((await verifyChatbotX(ctx,{run:async()=>{calls++;}})).status,'failed');
  await fs.writeFile(template,original);
  await fs.unlink(path.join(ctx.resources,'chatbotx/LICENSE.upstream'));
  assert.equal((await verifyChatbotX(ctx,{run:async()=>{calls++;}})).status,'failed');
  assert.equal(calls,0);
});
