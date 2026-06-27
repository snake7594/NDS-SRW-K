# -*- coding: utf-8 -*-
"""Export the title logo as editable PNGs (screen coordinates, 1:1 with the game).

  title_logo_canvas.png    256x224 RGBA  - the file to EDIT (current logo, rest transparent)
  title_logo_canvas_x4.png 1024x896 RGBA - same, 4x bigger (also editable; import auto-detects)
  title_logo_guide.png     256x224 RGB   - paintable area (sprite coverage) + zones
The pixel at (x,y) in the PNG maps to screen (x,y); the importer samples it back per sprite."""
import struct
import numpy as np
from PIL import Image

ss = open('_sstate.bin', 'rb').read()
vram = open('_vram.bin', 'rb').read()
pal = open('_pal.bin', 'rb').read()
i = ss.find(b'OAMS'); oam = ss[i+12:i+12+1024]
import os, sys
# default = ORIGINAL Japanese OBJ tiles (from the savestate VRAM);
# pass 'current' to export my Korean redraw instead.
if len(sys.argv) > 1 and sys.argv[1] == 'current' and os.path.exists('_fg_new.bin'):
    FG = open('_fg_new.bin', 'rb').read(); print('source: current Korean tiles (_fg_new.bin)')
else:
    FG = vram[0x90000:0x90000+0x8000]; print('source: ORIGINAL Japanese tiles (VRAM)')

def palcol(pn):
    base = 0x200 + pn*32; out = []
    for k in range(16):
        c = pal[base+k*2] | (pal[base+k*2+1] << 8)
        out.append(((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3))
    return out
DIM = {(0,0):(1,1),(0,1):(2,2),(0,2):(4,4),(0,3):(8,8),(1,0):(2,1),(1,1):(4,1),
       (1,2):(4,2),(1,3):(8,4),(2,0):(1,2),(2,1):(1,4),(2,2):(2,4),(2,3):(4,8)}
sprites = []
for s in range(128):
    a0, a1, a2 = struct.unpack_from('<HHH', oam, s*8)
    if ((a0 >> 8) & 1) == 0 and ((a0 >> 9) & 1): continue
    shape=(a0>>14)&3; size=(a1>>14)&3; y=a0&0xFF; x=a1&0x1FF
    if x>=256: x-=512
    tile=a2&0x3FF; pn=(a2>>12)&0xF; w,h=DIM.get((shape,size),(1,1))
    sprites.append(dict(s=s,x=x,y=y,w=w,h=h,tile=tile,pn=pn))
logo=[sp for sp in sprites if sp['y']<140]

H, W = 224, 256                              # match importer canvas (screen coords)
canvas=np.zeros((H,W,4),np.uint8)            # RGBA, transparent
cover =np.zeros((H,W),np.uint8)              # sprite coverage
isred =np.zeros((H,W),bool)                  # K region (reddish) -> keep red
for li in range(len(logo)-1,-1,-1):
    sp=logo[li]; cols=palcol(sp['pn'])
    for ty in range(sp['h']):
        for tx in range(sp['w']):
            ti=sp['tile']+ty*32+tx
            for py in range(8):
                sy=sp['y']+ty*8+py
                if not(0<=sy<H):continue
                for px in range(8):
                    sx=sp['x']+tx*8+px
                    if not(0<=sx<W):continue
                    cover[sy,sx]=255
                    o=ti*32+py*4+px//2; bb=FG[o]; v=(bb>>4) if(px&1) else (bb&0xF)
                    if v==0: continue
                    r,g,b=cols[v]
                    canvas[sy,sx]=(r,g,b,255)
                    if r>120 and r-b>40 and r-g>30: isred[sy,sx]=True

Image.fromarray(canvas,'RGBA').save('title_logo_canvas.png')
Image.fromarray(canvas,'RGBA').resize((W*4,H*4),Image.NEAREST).save('title_logo_canvas_x4.png')

# guide: dark = not paintable, mid-gray = paintable (covered), logo overlaid, red zone marked
guide=np.zeros((H,W,3),np.uint8); guide[:]=(28,28,34)
guide[cover>0]=(70,74,86)
guide[isred]=(120,60,55)
op=canvas[:,:,3]>0
guide[op]=canvas[:,:,:3][op]
Image.fromarray(guide,'RGB').resize((W*3,H*3),Image.NEAREST).save('title_logo_guide.png')

ys,xs=np.where(cover>0)
print("logo sprites:",len(logo)," coverage bbox: x %d..%d y %d..%d"%(xs.min(),xs.max(),ys.min(),ys.max()))
print("saved title_logo_canvas.png (256x224 EDIT THIS), title_logo_canvas_x4.png (1024x896), title_logo_guide.png")
