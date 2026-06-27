# -*- coding: utf-8 -*-
import json, os, re
from collections import Counter
PLACE=re.compile(r'[①-⓿㉑-㊿]')
def is_bad(c):
    o=ord(c); return (0x3040<=o<=0x30FF) or c in '\xad―─Ⅳ♪'
def width(s):
    return sum(12 if '가'<=c<='힣' else 8 for c in s)
def ok_width(ko):   # each ; sub-line <=176
    return all(width(p)<=176 for p in ko.split(';'))
bt=json.load(open('srwk_battle.json',encoding='utf-8'))
E=bt['entries']; pre=json.load(open('_battle_preqa.json',encoding='utf-8'))['entries']
man=json.load(open('_qab/manifest.json',encoding='utf-8'))
changed=missing=rev_bad=rev_ph=rev_struct=rev_w=0
for m in man:
    fn='_qab/out_%04d.json'%m['cid']
    if not os.path.exists(fn): missing+=1; continue
    try: r=json.load(open(fn,encoding='utf-8')).get('results',[])
    except Exception: missing+=1; continue
    for x in r:
        ek=str(x.get('ek')); vi=x.get('vi'); ko=x.get('ko')
        if ek not in E or not isinstance(vi,int): continue
        vl=E[ek]['vlines']
        if vi<0 or vi>=len(vl) or not isinstance(ko,str) or not ko.strip(): continue
        ko=ko.replace(' ','　'); preko=pre[ek]['vlines'][vi]['ko']
        if (set(ko)&set(filter(is_bad,ko)))-set(preko): rev_bad+=1; continue
        if Counter(PLACE.findall(ko))!=Counter(PLACE.findall(preko)): rev_ph+=1; continue
        if (';' in preko)!=(';' in ko): rev_struct+=1; continue
        if not ok_width(ko): rev_w+=1; continue
        if ko!=vl[vi]['ko']: vl[vi]['ko']=ko; changed+=1
json.dump(bt,open('srwk_battle.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('battle changed:',changed,'missing:',missing,'rev bad/ph/struct/width:',rev_bad,rev_ph,rev_struct,rev_w)
