#!/usr/bin/env python3
import argparse, json, os, re, shutil, sys, zipfile
from pathlib import Path

REQUIRED_DIRS = ['01_MASTER', '02_DIRECTOR', '03_NANOTEAM', '04_PROFILES', '05_SKILLS', '06_PROGRAMS', '07_CAPABILITIES', '08_INTEGRATIONS', '09_KNOWLEDGE', '10_MEMORY', '11_DATA', '12_MISSIONS', '13_WORKFLOWS', '14_AUTOMATIONS', '15_PROVIDER_ROUTES', '16_HARNESS', '17_EVALS', '18_EVIDENCE', '19_DISCORD', '20_VIEWS', '21_DOCTOR', '22_UPDATE_MIGRATIONS', '23_ROLLBACK', '24_RECOVERY', '25_GOVERNANCE', '26_SELF_IMPROVEMENT', '27_LIBRARIAN', '28_DEPLOYMENT', '29_ORCHESTRATION']
REQUIRED_CONTRACT_KEYS = ['schema_version', 'os_id', 'version', 'outcome_contract', 'nano_director', 'nanoteam', 'profiles', 'ordered_skills', 'programs', 'capability_contracts', 'integration_adapters', 'knowledge_memory', 'data_model', 'mission_model', 'provider_routes', 'workflows', 'automations', 'governance', 'engineering_harness', 'evaluations', 'evidence', 'discord', 'views', 'doctor', 'update_migrations', 'rollback', 'recovery', 'self_improvement', 'librarian', 'deployment', 'orchestration', 'claim_evidence_policy']

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9]+','-',s).strip('-')
    return s or 'new-os'

def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8')

def scaffold(args):
    slug = args.slug or slugify(args.name)
    root = Path(args.output).resolve()/slug
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f'Refusing to overwrite non-empty {root}')
    for d in REQUIRED_DIRS: (root/d).mkdir(parents=True, exist_ok=True)
    manifest = {
      'schema_version':'2.0','os_id':slug,'name':args.name,'version':'0.1.0','type':'operative_system',
      'entrypoint':'01_MASTER/OS.md','contract':'CONTRACT.json','librarian_handoff':'27_LIBRARIAN/14_BUILDER_HANDOFF.md',
      'secret_policy':'references_only','dependencies':[],'capabilities':[]
    }
    contract = {
      'schema_version':'2.0','os_id':slug,'version':'0.1.0',
      'outcome_contract':{'owns':'TODO','mission_types':[]},
      'nano_director':{'profile':f'{slug}-director','persistent_bot':True,'discord_identity':'dedicated'},
      'nanoteam':{'persistent_profiles':[],'kanban_workers':[],'ephemeral_roles':[]},
      'profiles':[],'ordered_skills':[],'programs':[],'capability_contracts':[],'integration_adapters':[],
      'knowledge_memory':{'knowledge_scopes':[],'memory_scopes':[]},
      'data_model':{'schema':'11_DATA/schema.json','state_model':'11_DATA/state-machine.yaml','migrations':'22_UPDATE_MIGRATIONS/'},
      'mission_model':{'durable_engine':'hermes_kanban','root':'mission_root_task','graph':'kanban_dag'},
      'provider_routes':{'policy':'model_agnostic'},'workflows':[],'automations':[],
      'governance':{'context_envelope':True,'capability_scoped':True,'approvals':'risk_based','trust_zone':'required'},
      'engineering_harness':None,'evaluations':[],
      'evidence':{'required':True,'logs':'hermes_native','secret_redaction':True},
      'discord':{'dedicated_bot':True,'dedicated_channel':True,'commands':'19_DISCORD/commands.yaml','experience':{'plan_first':True,'mission_progress_card':True,'components':'v2-preferred','final_report':True}},
      'views':[],'doctor':{'required':True},'update_migrations':{'required':True},
      'rollback':{'required':True},'recovery':{'required':True},
      'self_improvement':{'learning':'hermes_native','promotion':'governed'},
      'librarian':{'handoff':'27_LIBRARIAN/14_BUILDER_HANDOFF.md','minimum_inputs':15,'theme':args.theme,'research_lanes':['topic_map','book_deep','bestseller','web_deep','expert_operator_map','contrarian_failure']},
      'deployment':{'fresh_session_acceptance':True,'automations_default':'disabled_until_accepted'},
      'orchestration':{'contract':'station-orchestration/v1','plan_first':True,'evidence_before_claims':True,'ownership_visible':True,'lanes':['clarify_plan','connect_boundaries','remember_operate']},
      'claim_evidence_policy':{'stages':['prepared','observed','reported','verified','read_back','accepted'],'reported_is_verified':False,'plan_completion_is_evidence':False}
    }
    write(root/'MANIFEST.json', json.dumps(manifest,indent=2)+'\n')
    write(root/'CONTRACT.json', json.dumps(contract,indent=2)+'\n')
    write(root/'01_MASTER/OS.md', f'# {args.name}\n\nTheme: {args.theme}\n\n## Mission\nTODO\n\n## Definition of success\nTODO\n')
    write(root/'27_LIBRARIAN/14_BUILDER_HANDOFF.md', '# 14_BUILDER_HANDOFF\n\nSTATUS: INCOMPLETE\n\nComplete Librarian /research-os: Topic Map + Book Deep + Web Deep + Expert/Operator Map when applicable + Bestseller editorial synthesis + contradiction/failure analysis, then provide exactly 15 selected inputs before release.\n')
    write(root/'19_DISCORD/commands.yaml', 'commands:\n  - name: mission\n  - name: status\n  - name: plan\n  - name: approve\n  - name: review\n  - name: doctor\n  - name: recover\n  - name: help\n')
    write(root/'19_DISCORD/EXPERIENCE.yaml', 'schema: 1\nexperience:\n  plan_first: required\n  progress_surface: single-editable-mission-card\n  components: v2-preferred\n  tool_noise: logs-only\n  final_report: required\n')
    write(root/'27_LIBRARIAN/RESEARCH_REQUIREMENTS.yaml', 'schema: 2\nresearch_lanes:\n  topic_map: required\n  book_deep: required\n  bestseller: required\n  web_deep: required\n  expert_operator_map: adaptive-required\n  contrarian_failure: risk-based-required\nselected_inputs: 15\n')
    write(root/'29_ORCHESTRATION/ORCHESTRATION.yaml', 'contract: station-orchestration/v1\nplan_first: true\nevidence_before_claims: true\nownership_visible: true\nlanes:\n  - clarify_plan\n  - connect_boundaries\n  - remember_operate\nclaim_stages:\n  - prepared\n  - observed\n  - reported\n  - verified\n  - read_back\n  - accepted\n')
    write(root/'29_ORCHESTRATION/ACCEPTANCE.md', '# Orchestration Acceptance\n\nDeclare active lanes, owners, verification owners, connector readiness requirements and evidence required for accepted completion.\n')
    for d in REQUIRED_DIRS:
        readme=root/d/'README.md'
        if not readme.exists(): write(readme, f'# {d}\n\nTODO: complete this required OS component.\n')
    print(root)

def count_handoff_inputs(text):
    ids = set(re.findall(r'(?im)^###?\s+Input\s+(\d{1,2})\b', text))
    return len(ids)

def doctor_path(root):
    root=Path(root).resolve(); errors=[]; warnings=[]
    for d in REQUIRED_DIRS:
        if not (root/d).is_dir(): errors.append(f'missing directory: {d}')
    for f in ['MANIFEST.json','CONTRACT.json','01_MASTER/OS.md','27_LIBRARIAN/14_BUILDER_HANDOFF.md']:
        if not (root/f).is_file(): errors.append(f'missing file: {f}')
    contract={}; manifest={}
    try: contract=json.loads((root/'CONTRACT.json').read_text())
    except Exception as e: errors.append(f'CONTRACT.json invalid: {e}')
    try: manifest=json.loads((root/'MANIFEST.json').read_text())
    except Exception as e: errors.append(f'MANIFEST.json invalid: {e}')
    for k in REQUIRED_CONTRACT_KEYS:
        if k not in contract: errors.append(f'contract missing key: {k}')
    if manifest.get('secret_policy') != 'references_only': errors.append('secret_policy must be references_only')
    if contract.get('os_id') and manifest.get('os_id') and contract['os_id'] != manifest['os_id']:
        errors.append('MANIFEST os_id != CONTRACT os_id')
    exp=root/'19_DISCORD/EXPERIENCE.yaml'
    if not exp.exists(): errors.append('missing Discord Experience contract')
    req=root/'27_LIBRARIAN/RESEARCH_REQUIREMENTS.yaml'
    if not req.exists(): errors.append('missing Librarian research requirements')
    if not (root/'29_ORCHESTRATION/ORCHESTRATION.yaml').exists(): errors.append('missing orchestration contract')
    handoff=root/'27_LIBRARIAN/14_BUILDER_HANDOFF.md'
    if handoff.exists():
        text=handoff.read_text(encoding='utf-8')
        if 'STATUS: INCOMPLETE' in text: errors.append('Librarian handoff is incomplete')
        n=count_handoff_inputs(text)
        if n < 15: errors.append(f'Librarian handoff has {n}/15 explicit inputs')
    # crude but useful secret-pattern scanner
    patterns=[r'sk-[A-Za-z0-9_-]{16,}',r'ghp_[A-Za-z0-9]{20,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    for p in root.rglob('*'):
        if p.is_file() and p.stat().st_size < 2_000_000 and p.suffix.lower() not in {'.zip','.png','.jpg','.jpeg','.gif','.pdf'}:
            try: txt=p.read_text(errors='ignore')
            except: continue
            for pat in patterns:
                if re.search(pat,txt): errors.append(f'possible secret in {p.relative_to(root)}')
    print('AGK OS DOCTOR')
    for e in errors: print('FAIL:',e)
    for x in warnings: print('WARN:',x)
    if not errors: print('PASS')
    return 1 if errors else 0

def package(root,out,recovery=False):
    root=Path(root).resolve(); out=Path(out).resolve(); out.mkdir(parents=True,exist_ok=True)
    if doctor_path(root): raise SystemExit('Doctor failed; refusing package')
    manifest=json.loads((root/'MANIFEST.json').read_text())
    suffix='recovery' if recovery else 'package'
    dest=out/f"{manifest['os_id']}-{manifest['version']}-{suffix}.zip"
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file() and '.git' not in p.parts:
                z.write(p,p.relative_to(root.parent))
        if recovery:
            instructions="""RECOVERY ARTIFACT\n\n1. Verify the package version, source reference and archive readability.\n2. Restore into a clean target scope.\n3. Rebind credential references from the secret manager.\n4. Restore durable data from the declared backup source.\n5. Run doctor.\n6. Run critical workflow from a fresh session.\n7. Verify Discord readback.\n8. Record evidence before traffic is restored.\n"""
            z.writestr(f"{root.name}/RECOVERY_README.txt",instructions)
    print(dest)

def doctor_pack():
    here=Path(__file__).resolve().parents[1]
    required=['00_CANONICAL/AGK_OS_CONTRACT.md','../os/builder/README.md','../os/librarian/README.md','programs/librarian.py','../os/_template/MANIFEST.example.json']
    missing=[x for x in required if not (here/x).exists()]
    print('PACK DOCTOR')
    if missing:
        print('FAIL',missing); return 1
    print('PASS'); return 0

def main():
    ap=argparse.ArgumentParser(prog='agk_builder')
    sp=ap.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('new'); p.add_argument('--name',required=True); p.add_argument('--slug'); p.add_argument('--theme',required=True); p.add_argument('--output',default='./generated')
    p=sp.add_parser('doctor'); p.add_argument('root')
    sp.add_parser('doctor-pack')
    p=sp.add_parser('package'); p.add_argument('root'); p.add_argument('--output',default='./dist')
    p=sp.add_parser('recovery'); p.add_argument('root'); p.add_argument('--output',default='./dist')
    a=ap.parse_args()
    if a.cmd=='new': scaffold(a)
    elif a.cmd=='doctor': raise SystemExit(doctor_path(a.root))
    elif a.cmd=='doctor-pack': raise SystemExit(doctor_pack())
    elif a.cmd=='package': package(a.root,a.output,False)
    elif a.cmd=='recovery': package(a.root,a.output,True)
if __name__=='__main__': main()
