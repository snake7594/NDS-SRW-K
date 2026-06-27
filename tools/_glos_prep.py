# -*- coding: utf-8 -*-
import json, re, os
from collections import Counter, defaultdict
d=json.load(open('srwk_scenario_clean.json',encoding='utf-8'))['scenarios']
KATA=re.compile(r'[ァ-ヶー・＝]{4,}')
ys_tok=Counter(); my_tok=Counter()
ys_ex=defaultdict(list); my_ex=defaultdict(list)
for k,s in d.items():
    ys=s.get('translated')
    for b in s['boxes']:
        jp=''.join(b.get('jp',[]))
        if not jp: continue
        ko=' '.join(b.get('ko',[]))
        for t in set(KATA.findall(jp)):
            if ys:
                ys_tok[t]+=1
                if len(ys_ex[t])<4: ys_ex[t].append({'jp':jp[:80],'ko':ko[:90]})
            else:
                my_tok[t]+=1
                if len(my_ex[t])<4: my_ex[t].append({'jp':jp[:80],'ko':ko[:90]})
shared=sorted(set(ys_tok)&set(my_tok), key=lambda t:-(ys_tok[t]+my_tok[t]))
items=[{'jp':t,'ys_freq':ys_tok[t],'my_freq':my_tok[t],
        'ys':ys_ex[t],'my':my_ex[t]} for t in shared]
os.makedirs('_glos',exist_ok=True)
B=40
nb=0
for i in range(0,len(items),B):
    batch=items[i:i+B]
    json.dump(batch,open('_glos/batch_%02d.json'%(i//B),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    nb+=1
print('shared tokens:',len(items),' batches:',nb,' (B=%d)'%B)
