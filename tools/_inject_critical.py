# -*- coding: utf-8 -*-
"""_inject_critical.py — replace ONLY the クリティカル text in add04 IMG#14 with
크리티컬, keeping numbers/AP/EN/OFENSUPRT intact. クリティカル occupies linear tiles
(ty0,tx24-31)+(ty1,tx24-31) = indices 24-31 & 56-63. Style: gradient nib12(top)→
nib10(bottom), nib1 outline, nib0 transparent bg. Operates on kr/add04_patched.bin."""
import struct, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _enc1024b import build_ecd2
from PIL import Image, ImageFont, ImageDraw

FONT = r"C:\Windows\Fonts\malgunbd.ttf"
OUT_NIB = 1
FILL = [12, 12, 11, 11, 10, 10, 10, 10]   # top->bottom over 16px band

jp = Rom('../Super Robot Wars K (Japan).nds')
base = open('kr/add04_patched.bin', 'rb').read()
d = bytearray(base)
n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]

def dec(bi):
    raw = bytes(d[offs[bi]:offs[bi+1]])
    return decomp_1024(raw)[0] if raw[:4]==b'ECD\x01' else raw

# render 크리티컬 into 64x16 nibble grid (transparent bg)
W, H = 64, 16
text = '크리티컬'
dd = ImageDraw.Draw(Image.new('L',(1,1)))
f = None
for s in range(15, 8, -1):
    ff = ImageFont.truetype(FONT, s); bb = dd.textbbox((0,0), text, font=ff)
    if bb[2]-bb[0] <= W-2 and bb[3]-bb[1] <= H-1: f = ff; break
if f is None: f = ImageFont.truetype(FONT, 10)
mask = Image.new('L',(W,H),0); dr = ImageDraw.Draw(mask)
bb = dr.textbbox((0,0), text, font=f); tw=bb[2]-bb[0]; th=bb[3]-bb[1]
dr.text((max(0,(W-tw)//2), max(0,(H-th)//2)-bb[1]), text, fill=255, font=f)
mp = mask.load()
fill = [[mp[x,y]>=110 for x in range(W)] for y in range(H)]
grid = [[0]*W for _ in range(H)]
for y in range(H):
    for x in range(W):
        if fill[y][x]: continue
        if any(0<=y+dy<H and 0<=x+dx<W and fill[y+dy][x+dx] for dy in(-1,0,1) for dx in(-1,0,1)):
            grid[y][x] = OUT_NIB
ys=[y for y in range(H) if any(fill[y])]; y0=min(ys) if ys else 0; y1=max(ys) if ys else 1; span=max(1,y1-y0)
for y in range(H):
    for x in range(W):
        if fill[y][x]:
            grid[y][x] = FILL[max(0,min(len(FILL)-1,int((y-y0)/span*(len(FILL)-1)+0.5)))]

# build 16 tiles (2 rows x 8 cols) from grid
def tile_bytes(ty,tx):
    b=bytearray()
    for yy in range(8):
        for xx in range(0,8,2):
            b.append((grid[ty*8+yy][tx*8+xx]&0xF)|((grid[ty*8+yy][tx*8+xx+1]&0xF)<<4))
    return bytes(b)

img = bytearray(dec(14)); w,h = struct.unpack_from('<HH', img, 4)
assert (w,h)==(32,4), (w,h)
tdata = img[8:]
# replace linear tiles: row0 -> idx 24+c, row1 -> idx 56+c  (c=0..7)
for c in range(8):
    for (grow, idx) in ((0, 24+c),(1, 56+c)):
        tb = tile_bytes(grow, c)
        tdata[idx*32:(idx+1)*32] = tb
new_dec = bytes(img[:8]) + bytes(tdata)
orig_ecd = bytes(d[offs[14]:offs[15]])
new_ecd = build_ecd2(orig_ecd, new_dec[8:], new_preamble=new_dec[:8])
print(f'IMG14: {len(new_ecd)}/{len(orig_ecd)}', 'OK' if len(new_ecd)<=len(orig_ecd) else 'OVERFLOW')
if len(new_ecd) <= len(orig_ecd):
    d[offs[14]:offs[15]] = new_ecd + b'\x00'*(len(orig_ecd)-len(new_ecd))
    assert len(bytes(d))==len(base)
    open('kr/add04_patched.bin','wb').write(bytes(d))
    print('saved kr/add04_patched.bin')
