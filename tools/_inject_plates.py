# -*- coding: utf-8 -*-
"""_inject_plates.py — translate add04 special-ability / status text plates to Korean.
Blocks 24-119 are UNCOMPRESSED fixed-size IMG (80x16 / 128x16) → direct tile replace.
Output: kr/add04_patched.bin (+ verification montage _plates_ko.png)."""
import struct, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _plate_lib import build_img_block
from PIL import Image, ImageDraw
import numpy as np

jp = Rom('../Super Robot Wars K (Japan).nds')
d = bytearray(jp.get('data/add04dat.bin'))
n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]

# --- ability names (blocks 24-88) : jp reference, ko target ---
ABIL = {
 24:'MAP 병기', 25:'합체 공격', 26:'어택 콤보', 27:'쳐내기', 28:'격추', 29:'분신',
 30:'레이스 아르카나', 31:'오르곤 클라우드', 32:'미라지 콜로이드', 33:'일루전 프로텍트',
 34:'스텔스 장갑', 35:'오버스킬「가속」', 36:'오버스킬「초가속」', 37:'오버스킬「시간정지」',
 38:'오버스킬「투명화」', 39:'오버스킬「변형」', 40:'ECS', 41:'하이퍼 재머', 42:'오픈 겟',
 43:'ES 편대', 44:'갓 섀도', 45:'바이탈 점프', 46:'차원연결 시스템', 47:'레이스 아르카나',
 48:'오르곤 클라우드', 49:'빔 코트', 50:'라미네이트 장갑', 51:'야타노카가미', 52:'전자 실드',
 53:'확산 망토', 54:'페이즈 시프트 장갑', 55:'베리어블 페이즈 시프트 장갑', 56:'배리어',
 57:'양전자 리플렉터', 58:'비바추르 뤼미에르', 59:'포톤 매트 배리어', 60:'이지스 장비',
 61:'노른 시스템', 62:'바이오 장갑', 63:'플레어 실드', 64:'엔젤 월', 65:'엘도라 블록',
 66:'가디언 커튼', 67:'크리스탈 하트', 68:'트랜스 페이즈 장갑', 69:'차크라 실드',
 70:'프로텍트 월', 71:'프로텍트 시드', 72:'제네식 아머', 73:'제네레이팅 아머',
 74:'아르쥬르 뤼미에르', 75:'디스토션 필드', 76:'람다 드라이버', 77:'차원연결 시스템',
 78:'크리슈나 하트', 79:'실드 방어', 80:'AB 실드 방어', 81:'빔 실드 방어', 82:'환영',
 83:'원호 공격', 84:'원호 방어', 85:'카운터', 86:'동화', 87:'변조', 88:'시간 정지',
}
# --- status ailments (89-119): [stat] 저하 L[n], EN 흡수 L[n], 특수효과 무효 ---
STAT = ['조준치','운동성','장갑치','이동력','공격력','사정','SP','기력','EN']
STATUS = {}
bi = 89
for s in STAT:
    for lv in (1,2,3):
        STATUS[bi] = f'{s} 저하 L{lv}'; bi += 1
for lv in (1,2,3):
    STATUS[bi] = f'EN 흡수 L{lv}'; bi += 1
STATUS[bi] = '특수효과 무효'  # 119

PLATES = {**ABIL, **STATUS}

count = 0
for b, ko in sorted(PLATES.items()):
    orig = bytes(d[offs[b]:offs[b+1]])
    if orig[:4] != b'IMG\x00':
        print(f'  !! blk{b} not raw IMG ({orig[:4]!r}), skip'); continue
    w, h = struct.unpack_from('<HH', orig, 4); w*=8; h*=8
    new = build_img_block(ko, w, h)
    if len(new) != len(orig):
        print(f'  !! blk{b} size {len(new)}!={len(orig)}, skip'); continue
    d[offs[b]:offs[b+1]] = new
    count += 1
print(f'injected {count}/{len(PLATES)} plates')

os.makedirs('kr', exist_ok=True)
open('kr/add04_patched.bin', 'wb').write(bytes(d))
assert len(bytes(d)) == len(jp.get('data/add04dat.bin')), 'size changed!'
print('saved kr/add04_patched.bin')

# --- verification montage ---
p = decomp_1024(bytes(jp.get('data/add04dat.bin')[offs[12]:offs[13]]))[0] if False else jp.get('data/add04dat.bin')[offs[12]:offs[13]]
PAL = [(((c:=struct.unpack_from('<H', p, 8+i*2)[0])&0x1f)<<3, ((c>>5)&0x1f)<<3, ((c>>10)&0x1f)<<3) for i in range(16)]
def render(block, scale=3, bg=(40,40,60)):
    w,h = struct.unpack_from('<HH', block, 4); tile = block[8:8+w*h*32]
    a=np.frombuffer(tile,np.uint8); pp=np.empty(len(a)*2,np.uint8); pp[0::2]=a&0xF; pp[1::2]=a>>4
    pp=pp[:w*h*64].reshape(h,w,8,8); cv=np.zeros((h*8,w*8,3),np.uint8); cv[:]=bg; pa=np.array(PAL,np.uint8)
    for ty in range(h):
        for tx in range(w):
            blk=pp[ty,tx]; m=blk>0; cv[ty*8:ty*8+8,tx*8:tx*8+8][m]=pa[blk[m]]
    im=Image.fromarray(cv,'RGB'); return im.resize((im.width*scale,im.height*scale),Image.NEAREST)
bis=sorted(PLATES)
def mont(sub, fn):
    imgs=[(b,render(bytes(d[offs[b]:offs[b+1]]))) for b in sub]
    rowh=max(i.height for _,i in imgs)+6; W=max(i.width for _,i in imgs)+46
    M=Image.new('RGB',(W,len(imgs)*rowh),(15,15,15)); dr=ImageDraw.Draw(M)
    for k,(b,im) in enumerate(imgs): dr.text((2,k*rowh+rowh//2-4),str(b),fill=(255,255,0)); M.paste(im,(42,k*rowh+3))
    M.save(fn); print('saved',fn,M.size)
mont(bis[:len(bis)//2], '_plates_ko_a.png')
mont(bis[len(bis)//2:], '_plates_ko_b.png')
