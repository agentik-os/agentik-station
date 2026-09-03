#!/usr/bin/env python3
"""Small deterministic helper to validate a mission graph JSON for cycles and dangling edges."""
import argparse, json
from pathlib import Path

def validate(path):
    g=json.loads(Path(path).read_text()); nodes={n['id'] for n in g.get('nodes',[])}; errs=[]
    adj={n:[] for n in nodes}
    for e in g.get('edges',[]):
        a,b=e.get('from'),e.get('to')
        if a not in nodes or b not in nodes: errs.append(f'dangling edge {a}->{b}'); continue
        adj[a].append(b)
    seen=set(); stack=set()
    def dfs(n):
        if n in stack: return True
        if n in seen: return False
        seen.add(n); stack.add(n)
        for m in adj[n]:
            if dfs(m): return True
        stack.remove(n); return False
    if any(dfs(n) for n in nodes): errs.append('cycle detected: declare loop semantics explicitly instead of implicit dependency cycle')
    print('PASS' if not errs else '\n'.join('FAIL: '+e for e in errs)); return 1 if errs else 0
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('graph'); a=ap.parse_args(); raise SystemExit(validate(a.graph))
