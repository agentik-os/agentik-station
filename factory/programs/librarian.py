#!/usr/bin/env python3
import argparse, json
from pathlib import Path

MANDATORY_LANES=["topic_map","book_deep","bestseller","web_deep"]

def init(theme,out):
    p=Path(out); p.parent.mkdir(parents=True,exist_ok=True)
    parts=[f"# 14_BUILDER_HANDOFF\n\nSTATUS: INCOMPLETE\n\n## Research mission\n- Theme: {theme}\n- Target OS:\n- Mission:\n- Librarian run ID:\n\n## Research lanes\n- Topic Map:\n- Book Deep:\n- Web Deep:\n- Expert/Operator Map:\n- Contrarian/Failure:\n- Bestseller synthesis:\n\n## Source integrity\n- Sources discovered:\n- Sources verified:\n- Known gaps:\n\n## 15 best inputs\n"]
    for i in range(1,16):
        parts.append(f"\n### Input {i:02d}\n- Principle:\n- Source IDs:\n- Research lane(s):\n- Why it matters:\n- Skill implication:\n- Program implication:\n- Workflow/automation implication:\n- Eval:\n- Doctor probe:\n- Recovery implication:\n- Confidence/caveat:\n")
    parts.append("\n## Contradictions / trade-offs\n\n## Recommended OS architecture changes\n\n## Open questions\n\n## Traceability table\n")
    p.write_text("".join(parts),encoding="utf-8"); print(p)

def validate(packet):
    data=json.loads(Path(packet).read_text()); errs=[]
    lanes=data.get("lanes",{})
    for lane in MANDATORY_LANES:
        if lane not in lanes: errs.append(f"missing required research lane: {lane}")
    sources=data.get("sources",[]); inputs=data.get("selected_inputs",[])
    if len(inputs)!=15: errs.append(f"selected_inputs must contain exactly 15 items, got {len(inputs)}")
    src_ids={s.get("source_id") for s in sources if s.get("source_id")}
    for i,s in enumerate(sources,1):
        for k in ["source_id","title","source_type","verification_status","principles"]:
            if not s.get(k): errs.append(f"source {i} missing {k}")
    for i,x in enumerate(inputs,1):
        for k in ["input_id","principle","source_ids","os_mapping","eval","doctor_probe","recovery_implication"]:
            if not x.get(k): errs.append(f"input {i} missing {k}")
        unknown=set(x.get("source_ids",[]))-src_ids
        if unknown: errs.append(f"input {i} references unknown sources: {sorted(unknown)}")
    print("LIBRARIAN VALIDATOR V2")
    for e in errs: print("FAIL:",e)
    if not errs: print("PASS")
    return 1 if errs else 0

def main():
    ap=argparse.ArgumentParser(prog="librarian"); sp=ap.add_subparsers(dest="cmd",required=True)
    p=sp.add_parser("init"); p.add_argument("--theme",required=True); p.add_argument("--output",required=True)
    p=sp.add_parser("validate"); p.add_argument("packet")
    a=ap.parse_args()
    if a.cmd=="init": init(a.theme,a.output)
    else: raise SystemExit(validate(a.packet))
if __name__=="__main__": main()
