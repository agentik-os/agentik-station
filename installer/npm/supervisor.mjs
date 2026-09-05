// A held process-group leader prevents PID/PGID reuse while the parent cleans
// up non-interactive installers and their descendants. No user sessions attach.
import {spawn} from 'node:child_process';

if (!process.send || !process.argv[2]) process.exit(126);
const keepAlive = setInterval(()=>{},60_000);
process.on('SIGTERM',()=>{});
process.on('SIGINT',()=>{});
const child=spawn(process.argv[2],process.argv.slice(3),{env:process.env,shell:false,stdio:['ignore','inherit','inherit']});
let reported=false;
function report(value) { if(!reported) { reported=true; process.send(value); } }
child.on('error',error=>report({code:127,spawnError:error.code || 'spawn failed'}));
child.on('exit',(code,signal)=>report({code:code ?? 1,signal}));
process.on('disconnect',()=>{
  clearInterval(keepAlive);
  // The parent disappeared; this still-live leader owns this exact group.
  try { process.kill(-process.pid,'SIGKILL'); } catch { process.exit(125); }
});
