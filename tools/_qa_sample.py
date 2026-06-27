# -*- coding: utf-8 -*-
import json, random, os
random.seed(42)
items=[]
# scenario changed
a=json.load(open('_scenario_preqa.json',encoding='utf-8'))['scenarios']
b=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))['scenarios']
sc=[]
for k in b:
    if b[k].get('translated'): continue
    for i,(ba,bb) in enumerate(zip(a[k]['boxes'],b[k]['boxes'])):
        if ba['ko']!=bb['ko'] and bb.get('jp'):
            sc.append({'t':'scenario','jp':' '.join(bb['jp']),'old':' '.join(ba['ko']),'new':' '.join(bb['ko'])})
# battle changed
pa=json.load(open('_battle_preqa.json',encoding='utf-8'))['entries']
pb=json.load(open('srwk_battle.json',encoding='utf-8'))['entries']
bl=[]
for ek in pb:
    for vi,v in enumerate(pb[ek]['vlines']):
        ov=pa[ek]['vlines'][vi]['ko']; nv=v['ko']
        if ov!=nv: bl.append({'t':'battle','jp':v.get('jp',''),'old':ov,'new':nv})
random.shuffle(sc); random.shuffle(bl)
items=sc[:100]+bl[:50]
random.shuffle(items)
os.makedirs('_qv',exist_ok=True)
for f in os.listdir('_qv'):
    if f.startswith('batch_'): os.remove('_qv/'+f)
B=25
for s in range(0,len(items),B):
    json.dump(items[s:s+B],open('_qv/batch_%02d.json'%(s//B),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('verify items:',len(items),'(scenario %d, battle %d) batches: %d'%(len(sc[:100]),len(bl[:50]),(len(items)+B-1)//B))
