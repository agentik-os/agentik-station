import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
test('npm installer has no lifecycle network or OS mutation hooks',async()=>{
  const pkg=JSON.parse(await fs.readFile(path.join(root,'package.json'),'utf8'));
  for(const script of ['preinstall','install','postinstall','prepare','prepublish','prepublishOnly']) assert.equal(pkg.scripts?.[script],undefined);
  assert.equal(pkg.dependencies,undefined);
  assert.equal(pkg.bin.agk,undefined,'must not shadow canonical Host agk');
  assert.equal(pkg.bin.station,undefined,'must not shadow canonical Host station');
  assert.equal(pkg.bin['agentik-station'],'installer/npm/cli.mjs');
  const release=(await fs.readFile(path.join(root,'VERSION'),'utf8')).trim();
  assert.equal(pkg.version,`${release}.0`);
});
