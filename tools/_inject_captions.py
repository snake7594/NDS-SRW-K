# -*- coding: utf-8 -*-
"""_inject_captions.py — translate add02 time-skip caption graphics to Korean.
#1152 二ヵ月後… → 2개월 후…, #1154 一年後… → 1년 후…  (IMG + SCR + PLT@1151).
PLT@1151 is a black→white grayscale ramp (nib1=black .. nib12=white); text uses
luma→nibble on that ramp. Operates on kr/add02_patched.bin."""
import struct, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _enc1024b import build_ecd2
from PIL import Image, ImageFont, ImageDraw

FONT = r"C:\Windows\Fonts\malgunbd.ttf"

jp = Rom('../Super Robot Wars K (Japan).nds')
kr_path = 'kr/add02_patched.bin'
base = open(kr_path, 'rb').read()
d = bytearray(base)
n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]

def dec(bi):
    raw = bytes(d[offs[bi]:offs[bi+1]])
    return decomp_1024(raw)[0] if raw[:4]==b'ECD\x01' else raw

# PLT@1151 ramp: nib1..12 = black..white. luma 0->1, 255->12
def luma_to_nib(l):
    return max(1, min(12, round(l/255*11)+1))

CAPS = {1152:('2개월 후…',1153), 1154:('1년 후…',1155)}

def render_grid(text, row0, row1, maxw=96):
    W,H = 256,192
    y0,y1 = row0*8,(row1+1)*8; band=y1-y0
    f=None
    dd=ImageDraw.Draw(Image.new('L',(1,1)))
    for s in range(band, 8, -1):
        ff=ImageFont.truetype(FONT,s); bb=dd.textbbox((0,0),text,font=ff)
        if bb[2]-bb[0]<=maxw and bb[3]-bb[1]<=band-2: f=ff; break
    if f is None: f=ImageFont.truetype(FONT,10)
    mask=Image.new('L',(W,H),0); dr=ImageDraw.Draw(mask)
    bb=dr.textbbox((0,0),text,font=f); tw=bb[2]-bb[0]; th=bb[3]-bb[1]
    x=max(2,(W-tw)//2); y=y0+max(0,(band-th)//2)-bb[1]
    dr.text((x,y),text,fill=255,font=f)
    mp=mask.load()
    grid=[[1]*W for _ in range(H)]   # bg = nib1 (black)
    for yy in range(H):
        for xx in range(W):
            if mp[xx,yy]>=110: grid[yy][xx]=12   # hard threshold: white text (nib12), no AA
    return grid

def grid_to_tiles_scr(grid):
    tiles=[]; tmap={}; scr=[]
    for ty in range(24):
        for tx in range(32):
            tb=bytearray()
            for yy in range(8):
                for xx in range(0,8,2):
                    tb.append((grid[ty*8+yy][tx*8+xx]&0xF)|((grid[ty*8+yy][tx*8+xx+1]&0xF)<<4))
            tb=bytes(tb)
            if tb not in tmap: tmap[tb]=len(tiles); tiles.append(tb)
            scr.append(tmap[tb])
    return b''.join(tiles), scr

ok=0
for img_bi,(text,scr_bi) in CAPS.items():
    orig_img=bytes(d[offs[img_bi]:offs[img_bi+1]]); orig_scr=bytes(d[offs[scr_bi]:offs[scr_bi+1]])
    sd=dec(scr_bi); ents=struct.unpack_from('<768H',sd,8)
    # original text rows = rows whose tiles differ (non-bg). find rows with a 'bright' tile.
    idec=dec(img_bi); tile=idec[8:]
    def tile_has_bright(ti):
        o=ti*32
        return any((b&0xF)>=6 or (b>>4)>=6 for b in tile[o:o+32]) if o+32<=len(tile) else False
    rows=[ei//32 for ei,v in enumerate(ents) if tile_has_bright(v&0x3FF)]
    r0,r1=(min(rows),max(rows)) if rows else (10,12)
    grid=render_grid(text,r0,r1,maxw=(88 if img_bi==1152 else 68))
    tile_data,scr_ents=grid_to_tiles_scr(grid); ntiles=len(tile_data)//32
    h_tiles=(ntiles+31)//32; tile_data=tile_data+b'\x00'*(h_tiles*32*32-len(tile_data))
    new_img=build_ecd2(orig_img,tile_data,new_preamble=b'IMG\x00'+struct.pack('<HH',32,h_tiles))
    new_scr=build_ecd2(orig_scr,struct.pack('<768H',*scr_ents))
    if len(new_img)>len(orig_img): print(f'  !! IMG{img_bi} {len(new_img)}>{len(orig_img)} OVERFLOW'); continue
    if len(new_scr)>len(orig_scr): print(f'  !! SCR{scr_bi} {len(new_scr)}>{len(orig_scr)} OVERFLOW'); continue
    d[offs[img_bi]:offs[img_bi+1]]=new_img+b'\x00'*(len(orig_img)-len(new_img))
    d[offs[scr_bi]:offs[scr_bi+1]]=new_scr+b'\x00'*(len(orig_scr)-len(new_scr))
    ok+=1; print(f'  #{img_bi} {text}: IMG {len(new_img)}/{len(orig_img)} SCR {len(new_scr)}/{len(orig_scr)} rows{r0}-{r1} tiles={ntiles} OK')

assert len(bytes(d))==len(base),'size changed'
open(kr_path,'wb').write(bytes(d))
print(f'captions injected {ok}/2; saved {kr_path}')
