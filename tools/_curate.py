# -*- coding: utf-8 -*-
import json
r=json.load(open('_glossary_raw.json',encoding='utf-8'))['rules']
SOLID=[0,1,2,3,6,7,12,13,14,20,22,23,24,27,29,31,32,33,34,35,36,38,40,43,44,45,46,47,50,51,53,54,57,65,67,68,70,71,75,76,79,80,81,82,92,93,96,97,98,99,106,107,108,129,141,145]
BORDER=[9,42,48,49,62,109]   # YS less-standard, unify for consistency (flag)
MEANING=[25]                  # YS translates the name's meaning
apply=[]
for tier,idxs in (('solid',SOLID),('borderline',BORDER),('meaning',MEANING)):
    for i in idxs:
        e=r[i]; apply.append({'jp':e['jp'],'from':e['from'],'to':e['to'],'tier':tier,'note':e.get('note','')})
json.dump(apply,open('_glossary_apply.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
out=open('_glossary_show.txt','w',encoding='utf-8')
for tier in ('solid','borderline','meaning'):
    rows=[a for a in apply if a['tier']==tier]
    out.write('\n=== %s (%d) ===\n'%(tier.upper(),len(rows)))
    for a in rows: out.write('  %-22s  %s  ->  %s\n'%(a['jp'],a['from'],a['to']))
out.close()
print('apply rules:',len(apply),'(solid %d, border %d, meaning %d)'%(len(SOLID),len(BORDER),len(MEANING)))
