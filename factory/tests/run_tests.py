#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def chk(name,fn):
    try: fn(); checks.append((name,True,''))
    except Exception as e: checks.append((name,False,str(e)))
chk('canonical contract', lambda: (_ for _ in ()).throw(Exception('missing')) if not (ROOT/'00_CANONICAL/AGK_OS_CONTRACT.md').exists() else None)
chk('builder profile', lambda: (_ for _ in ()).throw(Exception('missing')) if not (ROOT.parent/'packages/os/builder-os/BUILDER_PROFILE.md').exists() else None)
chk('librarian profile', lambda: (_ for _ in ()).throw(Exception('missing')) if not (ROOT.parent/'packages/os/librarian-os/LIBRARIAN_PROFILE.md').exists() else None)
chk('schemas parse', lambda: [json.loads(p.read_text()) for p in (ROOT/'06_SCHEMAS').glob('*.json')])
chk('builder help', lambda: subprocess.run([sys.executable,str(ROOT/'programs/agk_builder.py'),'--help'],check=True,capture_output=True))
chk('librarian help', lambda: subprocess.run([sys.executable,str(ROOT/'programs/librarian.py'),'--help'],check=True,capture_output=True))
chk('pack doctor', lambda: subprocess.run([sys.executable,str(ROOT/'programs/agk_builder.py'),'doctor-pack'],check=True,capture_output=True))
for n,ok,msg in checks: print(('PASS' if ok else 'FAIL')+': '+n+((' — '+msg) if msg else ''))
failed=[x for x in checks if not x[1]]
print(f'RESULT: {len(checks)-len(failed)}/{len(checks)} passed')
raise SystemExit(1 if failed else 0)
