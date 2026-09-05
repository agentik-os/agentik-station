import { spawn } from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const supervisor=fileURLToPath(new URL('./supervisor.mjs',import.meta.url));

// No ambient environment is merged: callers must explicitly scope credentials,
// HOME, caches and PATH. Captured native output is never written to receipts.
export function run(executable, argv = [], options = {}) {
  if (typeof executable !== 'string' || !Array.isArray(argv) || argv.some(x => typeof x !== 'string')) throw new Error('Expected executable and string argv.');
  const { env = {}, cwd, timeoutMs = 15 * 60_000, allowFailure = false, interactive = false } = options;
  return new Promise((resolve, reject) => {
    let output = '', errors = '', bytes = 0, failure, nativeResult, leaderAlive = true, drain;
    const child = spawn(interactive ? executable : process.execPath, interactive ? argv : [supervisor,executable,...argv], { cwd, env, shell: false, detached: !interactive,
      stdio: interactive ? 'inherit' : ['ignore', 'pipe', 'pipe','ipc'] });
    const stop = () => { if (leaderAlive) try { process.kill(interactive ? child.pid : -child.pid, 'SIGTERM'); } catch {} };
    const kill = () => { if (leaderAlive) try { process.kill(interactive ? child.pid : -child.pid, 'SIGKILL'); } catch {} };
    let force;
    const abort = reason => { failure = reason; stop(); force ||= setTimeout(kill, 1000); force.unref(); };
    const timer = setTimeout(() => abort('timeout'), timeoutMs); timer.unref();
    const interrupt = () => abort('interrupted');
    process.once('SIGINT', interrupt); process.once('SIGTERM', interrupt);
    const collect = (chunk, stderr) => {
      bytes += chunk.length;
      if (bytes > 1024 * 1024) { abort('output limit'); return; }
      if (stderr) errors += chunk.toString(); else output += chunk.toString();
    };
    child.stdout?.on('data', chunk => collect(chunk, false));
    child.stderr?.on('data', chunk => collect(chunk, true));
    child.on('message',result=>{
      if (nativeResult || !result || !Number.isInteger(result.code)) return;
      nativeResult=result;
      // The supervisor remains alive until this signal, so this PGID cannot be
      // recycled between native command exit and descendant cleanup.
      kill();
    });
    const cleanup = () => { clearTimeout(timer); clearTimeout(force); clearTimeout(drain); process.off('SIGINT', interrupt); process.off('SIGTERM', interrupt); };
    child.once('exit',()=>{
      leaderAlive=false;
      clearTimeout(timer); clearTimeout(force);
      // A process that deliberately creates a new session is outside this
      // same-group cleanup contract. It must not hold our capture pipes open
      // indefinitely, nor cause a later signal to a recycled supervisor PID.
      if (!interactive) drain=setTimeout(()=>{child.stdout?.destroy();child.stderr?.destroy();},100);
    });
    child.once('error', error => { cleanup(); reject(new Error(`Cannot run ${path.basename(executable)} (${error.code || 'spawn failed'}).`)); });
    child.once('close', (code, signal) => {
      cleanup();
      if (!interactive && !nativeResult && !failure) failure='supervisor exited without a command result';
      if (nativeResult?.spawnError) { reject(new Error(`Cannot run ${path.basename(executable)} (${nativeResult.spawnError}).`)); return; }
      if (nativeResult) { code=nativeResult.code; signal=nativeResult.signal; }
      const result = { code: code ?? 1, stdout: output, stderr: errors };
      if (failure || (code !== 0 && !allowFailure)) reject(new Error(`${path.basename(executable)} failed (${failure || signal || `exit ${code}`}); no command arguments or native output were recorded.`));
      else resolve(result);
    });
  });
}
