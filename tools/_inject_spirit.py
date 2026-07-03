# -*- coding: utf-8 -*-
"""_inject_spirit.py — translate add02 spirit-command / battle-item red graphics
(blocks 2152-2202, 128x16 compressed IMG) to Korean. Style derived from block 2175
(加速): nib0=transparent, nib1=outline, per-row bright-nibble gradient fill.
Re-encode with build_ecd2, fit in original compressed size. -> kr/add02_patched.bin"""
import struct, io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _enc1024b import build_ecd2
from PIL import Image, ImageFont, ImageDraw
import numpy as np

FONT = r"C:\Windows\Fonts\malgunbd.ttf"
jp = Rom('../Super Robot Wars K (Japan).nds')
base = open('kr/add02_patched.bin','rb').read()
d = bytearray(base)
n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
offs = list(struct.unpack_from('<%dI'%ne, d, 0)) + [len(d)]
def dec(bi):
    raw = bytes(d[offs[bi]:offs[bi+1]])
    return decomp_1024(raw)[0] if raw[:4]==b'ECD\x01' else raw

# --- derive per-row fill nibble gradient from 2175 (加速) ---
r = dec(2175); w,h = struct.unpack_from('<HH', r, 4); tile = r[8:]
rowfill = []
for py in range(h*8):
    cnt = collections.Counter()
    ty = py//8; yy = py%8
    for tx in range(w):
        off = (ty*w+tx)*32
        for xx in range(8):
            b = tile[off+yy*4+xx//2]; nib = (b&0xF) if (xx&1)==0 else (b>>4)
            if nib not in (0,1): cnt[nib]+=1
    rowfill.append(cnt.most_common(1)[0][0] if cnt else 15)
# rowfill[y] = fill nibble for pixel-row y (0..15)

# --- translations (block: KO) ---
KO = {
 2152:'오버플로우',2153:'오버스킬',2154:'강철 파워',2155:'이모셔널 모드',2156:'파츠',
 2157:'SEED',2158:'블래스터화',2159:'마징 파워',2160:'탄창 회복',2161:'프로펠런트 탱크',
 2162:'카트리지',2163:'리페어 키트',2164:'슈퍼 리페어 키트',
 2165:'열혈',2166:'혼',2167:'투지',2168:'번뜩임',2169:'불굴',2170:'철벽',2171:'교란',
 2172:'집중',2173:'필중',2174:'감응',2175:'가속',2176:'각성',2177:'재동',2178:'돌격',
 2179:'근성',2180:'도근성',2181:'신뢰',2182:'우정',2183:'반',2184:'보급',2185:'저격',
 2186:'기합',2187:'기백',2188:'격려',2189:'탈력',2190:'기대',2191:'봐주기',2192:'직격',
 2193:'정찰',2194:'사랑',2195:'직감',2196:'행운',2197:'축복',2198:'노력',2199:'응원',
 2200:'크리스탈 하트',2201:'레 미이의 통구이',2202:'크리슈나 하트',
}

def render_grid(text, W=128, H=16):
    dd = ImageDraw.Draw(Image.new('L',(1,1)))
    f = None
    for s in range(16, 7, -1):
        ff = ImageFont.truetype(FONT, s); bb = dd.textbbox((0,0), text, font=ff)
        if bb[2]-bb[0] <= W-2 and bb[3]-bb[1] <= H-1: f = ff; break
    if f is None: f = ImageFont.truetype(FONT, 8)
    mask = Image.new('L',(W,H),0); dr = ImageDraw.Draw(mask)
    bb = dr.textbbox((0,0), text, font=f); tw=bb[2]-bb[0]; th=bb[3]-bb[1]
    # left-align like originals (text starts near x=2)
    dr.text((2, max(0,(H-th)//2)-bb[1]), text, fill=255, font=f)
    mp = mask.load()
    fill = [[mp[x,y]>=110 for x in range(W)] for y in range(H)]
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if fill[y][x]: continue
            if any(0<=y+dy<H and 0<=x+dx<W and fill[y+dy][x+dx] for dy in(-1,0,1) for dx in(-1,0,1)):
                grid[y][x] = 1
    for y in range(H):
        for x in range(W):
            if fill[y][x]: grid[y][x] = rowfill[y]
    return grid

def grid_to_tiles(grid, W=128, H=16):
    out = bytearray()
    for ty in range(H//8):
        for tx in range(W//8):
            for yy in range(8):
                for xx in range(0,8,2):
                    out.append((grid[ty*8+yy][tx*8+xx]&0xF)|((grid[ty*8+yy][tx*8+xx+1]&0xF)<<4))
    return bytes(out)

ok=0; fails=[]
for bi, ko in sorted(KO.items()):
    orig = bytes(d[offs[bi]:offs[bi+1]])
    grid = render_grid(ko)
    tiles = grid_to_tiles(grid)
    new = build_ecd2(orig, tiles, new_preamble=b'IMG\x00'+struct.pack('<HH',16,2))
    if len(new) > len(orig): fails.append((bi,ko,len(new),len(orig))); continue
    d[offs[bi]:offs[bi+1]] = new + b'\x00'*(len(orig)-len(new))
    ok+=1
print(f'spirit injected {ok}/{len(KO)}')
for bi,ko,nl,ol in fails: print(f'  OVERFLOW blk{bi} {ko!r}: {nl}>{ol}')
assert len(bytes(d))==len(base)
open('kr/add02_patched.bin','wb').write(bytes(d))
print('saved kr/add02_patched.bin')
