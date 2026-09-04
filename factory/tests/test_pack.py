import json, tempfile, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_core_files_exist():
    assert (ROOT/'00_CANONICAL/AGK_OS_CONTRACT.md').exists()
    assert (ROOT.parent/'os/builder/README.md').exists()
    assert (ROOT.parent/'os/librarian/README.md').exists()

def test_example_schemas_json_parse():
    for p in (ROOT/'schemas').glob('*.json'): json.loads(p.read_text())

def test_builder_cli_help():
    r=subprocess.run([sys.executable,str(ROOT/'programs/agk_builder.py'),'--help'],capture_output=True,text=True)
    assert r.returncode==0

def test_librarian_cli_help():
    r=subprocess.run([sys.executable,str(ROOT/'programs/librarian.py'),'--help'],capture_output=True,text=True)
    assert r.returncode==0
