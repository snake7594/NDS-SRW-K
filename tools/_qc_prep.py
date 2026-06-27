# -*- coding: utf-8 -*-
import json, os
sc=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))['scenarios']
os.makedirs('_qc',exist_ok=True)
for f in os.listdir('_qc'):
    if f.startswith(('chunk_','out_')): os.remove('_qc/'+f)
man=[]; cid=0; CH=50
for k in ('174','186'):
    boxes=sc[k]['boxes']
    for s in range(0,len(boxes),CH):
        ch=[{'i':i,'name':boxes[i].get('name'),'jp':boxes[i]['jp'],'ko':boxes[i]['ko']}
            for i in range(s,min(s+CH,len(boxes))) if boxes[i].get('jp')]
        if not ch: continue
        json.dump({'scenario':k,'boxes':ch},open('_qc/chunk_%04d.json'%cid,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        man.append({'cid':cid,'scenario':k,'n':len(ch)}); cid+=1
json.dump(man,open('_qc/manifest.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('conciseness chunks:',cid,' total boxes:',sum(m['n'] for m in man))
