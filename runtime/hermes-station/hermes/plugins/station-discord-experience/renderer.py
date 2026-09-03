from __future__ import annotations

def progress_bar(done,total,width=10):
    ratio=0 if total<=0 else max(0,min(1,done/total)); filled=round(ratio*width)
    return '█'*filled+'░'*(width-filled), round(ratio*100)

def evidence_label(state):
    stage=state.get('evidence_stage')
    kind=state.get('work_kind','mission')
    if not stage: return None
    noun={'plan':'Plan','code':'Code','test':'Test','ship':'Ship','mission':'Mission','research':'Research','artifact':'Artifact','connector':'Connector'}.get(kind,str(kind).title())
    suffix={'prepared':'not run','observed':'running','reported':'reported done','verified':'verified','read_back':'read back','accepted':'accepted'}.get(stage,stage)
    return f"{noun} • {suffix}"

def render_text(state, max_nodes=10):
    nodes=state.get('nodes',[]); done=sum(1 for n in nodes if n.get('status') in ('done','skipped'))
    bar,pct=progress_bar(done,len(nodes))
    glyph={'done':'✓','skipped':'–','running':'↻','blocked':'!','failed':'×','verifying':'◇','ready':'•','pending':'○'}
    lines=[]
    for n in nodes[:max_nodes]: lines.append(f"{glyph.get(n.get('status','pending'),'○')} {n.get('label',n.get('id','step'))}")
    if len(nodes)>max_nodes: lines.append(f"… {len(nodes)-max_nodes} more nodes · use Graph")
    return {
      'title': state.get('objective','Mission'),
      'status': str(state.get('status','planning')).upper(),
      'evidence_label': evidence_label(state),
      'progress': f"{bar} {pct}% · {done}/{len(nodes)}",
      'plan': '\n'.join(lines),
      'current': state.get('last_summary','Plan created.'),
      'revision': state.get('plan_revision',1)
    }

def components_v2(state):
    v=render_text(state)
    headline=v.get('evidence_label') or v['status']
    text=f"# {v['title']}\n**{headline}** · {v['progress']}\n\n## Plan\n{v['plan']}\n\n## Current\n{v['current']}\n\n-# Plan revision {v['revision']}"
    return {
      'flags':32768,
      'components':[
        {'type':17,'components':[
          {'type':10,'content':text},
          {'type':14,'divider':True,'spacing':1},
          {'type':1,'components':[
            {'type':2,'style':2,'label':'Details','custom_id':'station:details'},
            {'type':2,'style':2,'label':'Graph','custom_id':'station:graph'},
            {'type':2,'style':2,'label':'Evidence','custom_id':'station:evidence'}
          ]}
        ]}
      ]
    }
