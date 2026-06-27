# -*- coding: utf-8 -*-
import json, os, re
from collections import Counter
PLACE=re.compile(r'[①-⓿㉑-㊿]')
def is_bad(c):
    o=ord(c); return (0x3040<=o<=0x30FF) or c in '\xad―─Ⅳ♪'
man=json.load(open('_qc/manifest.json',encoding='utf-8'))
sc=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))
pre=json.load(open('_scenario_preconcise.json',encoding='utf-8'))['scenarios']
S=sc['scenarios']
changed=miss=revb=revp=0
for m in man:
    fn='_qc/out_%04d.json'%m['cid']; k=m['scenario']
    if not os.path.exists(fn): miss+=1; continue
    try: r=json.load(open(fn,encoding='utf-8')).get('results',[])
    except Exception: miss+=1; continue
    boxes=S[k]['boxes']
    for x in r:
        i=x.get('i'); ko=x.get('ko')
        if not isinstance(i,int) or not isinstance(ko,list) or i<0 or i>=len(boxes): continue
        ko=[ln.replace(' ','　') for ln in ko if isinstance(ln,str) and ln.strip()]
        if not ko: continue
        preko=pre[k]['boxes'][i]['ko']; allk=''.join(ko); allp=''.join(preko)
        if (set(allk)&set(filter(is_bad,allk)))-set(allp): revb+=1; continue
        if Counter(PLACE.findall(allk))!=Counter(PLACE.findall(allp)): revp+=1; continue
        if boxes[i]['ko']!=ko: boxes[i]['ko']=ko; changed+=1
json.dump(sc,open('srwk_scenario_clean.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('concise applied:',changed,'missing:',miss,'rev bad/placeholder:',revb,revp)
