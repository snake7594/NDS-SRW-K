# -*- coding: utf-8 -*-
import json, re
from collections import Counter
PLACE=re.compile(r'[①-⓿㉑-㊿]')
BAD=set('\xad―Ⅳ─♪っ・ー')
pre=json.load(open('_scenario_preqa.json',encoding='utf-8'))['scenarios']
cur=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))
S=cur['scenarios']
rev_bad=0; rev_ph=0
for k in S:
    if S[k].get('translated'): continue
    pb=pre[k]['boxes']
    for i,box in enumerate(S[k]['boxes']):
        po=''.join(pb[i]['ko']); cu=''.join(box['ko'])
        new_bad=(set(cu)&BAD)-set(po)
        ph_changed=Counter(PLACE.findall(po))!=Counter(PLACE.findall(cu))
        if new_bad:
            box['ko']=list(pb[i]['ko']); rev_bad+=1
        elif ph_changed:
            box['ko']=list(pb[i]['ko']); rev_ph+=1
json.dump(cur,open('srwk_scenario_clean.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('reverted for new bad-char:',rev_bad,' reverted for placeholder change:',rev_ph)
# re-verify
S=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))['scenarios']
allc=set()
for k in S:
    if S[k].get('translated'): continue
    for box in S[k]['boxes']:
        for ln in box['ko']: allc.update(ln)
left=[c for c in allc if c in BAD]
print('remaining bad chars in my scenarios:',sorted(left))
