# -*- coding: utf-8 -*-
"""Merge QA-rewritten ko back into the scenario JSON (defensive: keep original on
any missing/invalid chunk or box)."""
import json, os
man=json.load(open('_qa/manifest.json',encoding='utf-8'))
sc=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))
S=sc['scenarios']
changed=0; missing=[]; bad=[]; skipbox=0
for m in man:
    cid=m['cid']; k=m['scenario']
    fn='_qa/out_%04d.json'%cid
    if not os.path.exists(fn): missing.append(cid); continue
    try:
        r=json.load(open(fn,encoding='utf-8')).get('results',[])
    except Exception: bad.append(cid); continue
    boxes=S[k]['boxes']
    for x in r:
        i=x.get('i'); ko=x.get('ko')
        if not isinstance(i,int) or not isinstance(ko,list) or i<0 or i>=len(boxes): skipbox+=1; continue
        ko=[ln.replace(' ','　') for ln in ko if isinstance(ln,str) and ln.strip()]
        if not ko: skipbox+=1; continue
        if boxes[i]['ko']!=ko:
            boxes[i]['ko']=ko; changed+=1
json.dump(sc,open('srwk_scenario_clean.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('boxes changed:',changed,' missing chunks:',len(missing),' bad chunks:',len(bad),' skipped boxes:',skipbox)
if missing: print('missing chunk ids:',missing[:30])
