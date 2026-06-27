# -*- coding: utf-8 -*-
import json, os
bt=json.load(open('srwk_battle.json',encoding='utf-8'))['entries']
os.makedirs('_qab',exist_ok=True)
for f in os.listdir('_qab'):
    if f.startswith('chunk_'): os.remove('_qab/'+f)
flat=[]
for ek,e in bt.items():
    for vi,v in enumerate(e['vlines']):
        if v.get('jp') and v.get('ko'):
            flat.append({'ek':ek,'vi':vi,'sp':v.get('sp'),'jp':v['jp'],'ko':v['ko']})
CH=120; man=[]; cid=0
for s in range(0,len(flat),CH):
    json.dump(flat[s:s+CH],open('_qab/chunk_%04d.json'%cid,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    man.append({'cid':cid,'n':len(flat[s:s+CH])}); cid+=1
json.dump(man,open('_qab/manifest.json','w',encoding='utf-8'),ensure_ascii=False)
print('battle vlines:',len(flat),' chunks:',cid)
