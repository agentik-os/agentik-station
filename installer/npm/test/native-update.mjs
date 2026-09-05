/** Explicit native update acceptance against a disposable native-install root.
 * Requires --root from that harness; never targets the user's default station.
 * Uses a synthetic successor label with identical reviewed pins: lifecycle/path
 * acceptance, NOT acceptance of a different upstream release or active gateway.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createContext, acquireLock, atomicJSON } from '../state.mjs';
import { updatePlan, applyUpdate } from '../update.mjs';
import { provision, verify } from '../runtime.mjs';
import { run } from '../process.mjs';

const sourceRoot = fileURLToPath(new URL('../../../', import.meta.url));
const root = process.argv[2];
if (!root || !/^\/(?:private\/)?tmp\/stnf\.[A-Za-z0-9]+\/station$/.test(root)) throw new Error('Only an explicit disposable native-acceptance root is supported.');
const prior = JSON.parse(await fs.readFile(path.join(path.dirname(root), 'native-acceptance.json')));
assert.equal(prior.root, root); assert.equal(prior.status, 'verified');
const ctx = await createContext({ root, sourceRoot });
const account = os.userInfo().homedir;
const protectedNames = ['.zprofile', '.zshrc', '.profile', '.npmrc', '.hermes/.env', '.hermes/config.yaml',
  '.codex/config.toml', '.codex/auth.json', '.codex/AGENTS.md', '.claude/CLAUDE.md', '.config/rmux/rmux.conf',
  '.rustup/settings.toml', '.chatbotX/config.json', '.chatbotX/openapi-cache.json'];
async function fingerprint() {
  const result = {};
  for (const name of protectedNames) {
    const target = path.join(account, name);
    try { const info = await fs.lstat(target); result[name] = info.isFile() ? createHash('sha256').update(await fs.readFile(target)).digest('hex') : 'nonregular'; }
    catch (error) { if (error.code === 'ENOENT') result[name] = null; else throw error; }
  }
  return result;
}
const before = await fingerprint();
const plan = await updatePlan(ctx);
const parts = ctx.release.split('.').map(Number);
const successor = { ...ctx, release: `${parts[0]}.${parts[1] + 1}` };
const unlock = await acquireLock(ctx);
let result;
try {
  console.log('Rebuilding the exact pinned software at its final paths; no service/account enrollment...');
  result = await applyUpdate(successor, { run, provision, verify, emit: event => console.log(`${event.phase}: ${event.status}`) });
  assert.equal(result.to, successor.release);
  assert.equal(result.operational, false);
  assert.equal((await updatePlan(successor)).from, successor.release);
  result.nativeScope = 'synthetic-successor-label-same-reviewed-upstreams-no-active-services';
  result.predecessor = plan.from;
} finally {
  await unlock();
  const after = await fingerprint();
  const changed = protectedNames.filter(name => before[name] !== after[name]);
  await atomicJSON(path.join(path.dirname(root), 'native-update-protected.json'),
    { protectedFileCount: protectedNames.length, changed }, { exclusive: true });
  assert.deepEqual(changed, [], 'A protected personal file changed during native update acceptance.');
}
await atomicJSON(path.join(path.dirname(root), 'native-update-acceptance.json'), result, { exclusive: true });
console.log(JSON.stringify({ status: result.status, from: result.from, to: result.to, scope: result.nativeScope, operational: false }));
