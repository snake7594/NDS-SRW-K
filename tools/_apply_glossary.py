# -*- coding: utf-8 -*-
import json, re
from collections import Counter
rules=json.load(open('_glossary_apply.json',encoding='utf-8'))
def sepvars(s):
    parts=[p for p in re.split(r'[　・＝ ]',s) if p]
    if len(parts)<=1: return {s}
    return set(sep.join(parts) for sep in ['　','・','','＝',' ']) | {s}
# build (jp, [(src,to)...]) sorted longest-src-first; rules sorted longest-jp-first
RULES=[]
for r in rules:
    srcs=(sepvars(r['from'])|sepvars(r['to']))-{r['to']}
    srcs=sorted(srcs,key=len,reverse=True)
    RULES.append((r['jp'],[(s,r['to']) for s in srcs]))
RULES.sort(key=lambda x:-len(x[0]))

def apply_to_ko(kolines, jptext):
    cnt=0; out=[]
    active=[(jp,reps) for jp,reps in RULES if jp in jptext]
    for ln in kolines:
        for jp,reps in active:
            for src,to in reps:
                if src in ln:
                    ln=ln.replace(src,to); cnt+=1
        out.append(ln)
    return out,cnt

# SCENARIO tr=False
sc=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))
nchg=0; perrule=Counter()
for k,s in sc['scenarios'].items():
    if s.get('translated'): continue   # skip YameSoft
    for b in s['boxes']:
        jp=''.join(b.get('jp',[]))
        if not jp: continue
        before=list(b['ko'])
        b['ko'],c=apply_to_ko(b['ko'],jp)
        if b['ko']!=before:
            nchg+=1
            for jpk,reps in RULES:
                if jpk in jp:
                    for src,to in reps:
                        if any(src in x for x in before): perrule[jpk]+=1; break
json.dump(sc,open('srwk_scenario_clean.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('SCENARIO boxes changed:',nchg)

# BATTLE
bt=json.load(open('srwk_battle.json',encoding='utf-8'))
bchg=0
for e in (bt['entries'].values() if isinstance(bt['entries'],dict) else bt['entries']):
    for v in e['vlines']:
        jp=v.get('jp','')
        if not jp: continue
        before=v['ko']
        out,c=apply_to_ko([v['ko']],jp)
        if out[0]!=before: v['ko']=out[0]; bchg+=1
json.dump(bt,open('srwk_battle.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('BATTLE vlines changed:',bchg)
print('top rules applied:',perrule.most_common(12))
