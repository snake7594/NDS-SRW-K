# -*- coding: utf-8 -*-
import json, os
sc=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))['scenarios']
os.makedirs('_qa',exist_ok=True)
for f in os.listdir('_qa'):
    if f.startswith('chunk_'): os.remove('_qa/'+f)
manifest=[]; cid=0; CHUNK=50
for k in sorted(sc,key=int):
    s=sc[k]
    if s.get('translated'): continue          # only my (tr=False) scenarios
    boxes=s['boxes']
    for start in range(0,len(boxes),CHUNK):
        ch=[]
        for i in range(start,min(start+CHUNK,len(boxes))):
            b=boxes[i]
            if not b.get('jp'): continue       # safety (tr=False has none, but)
            ch.append({'i':i,'name':b.get('name'),'jp':b['jp'],'ko':b['ko']})
        if not ch: continue
        json.dump({'scenario':k,'boxes':ch},open('_qa/chunk_%04d.json'%cid,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        manifest.append({'cid':cid,'scenario':k,'n':len(ch)})
        cid+=1
json.dump(manifest,open('_qa/manifest.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
tot=sum(m['n'] for m in manifest)
print('chunks:',cid,' total boxes:',tot)
