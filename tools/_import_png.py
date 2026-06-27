# -*- coding: utf-8 -*-
"""Import a user-edited title-logo PNG back into the OBJ tiles (display-lossless).

Usage:  python _import_png.py title_logo_canvas.png
Accepts 256x224 (1:1) or 1024x896 (4x, auto box-downscaled). Per screen pixel:
  * opaque  -> write the colour (nearest in that sprite's 16-col palette) to the
    DISPLAY-OWNER sprite (topmost sprite whose pixel is non-transparent), or, if
    the pixel was empty, to the topmost covering sprite.
  * transparent (alpha<128) -> clear every covering sprite's pixel to index 0.
Unedited pixels round-trip byte-exact. Writes _fg_new.bin; then run
_inject_title3.py -> build_rom_all.py -> _mkpatch.py."""
import struct, sys
import numpy as np
from PIL import Image

png = sys.argv[1] if len(sys.argv) > 1 else 'title_logo_canvas.png'
im = Image.open(png).convert('RGBA')
if im.size == (1024, 896): im = im.resize((256, 224), Image.BOX)
elif im.size != (256, 224): im = im.resize((256, 224), Image.LANCZOS)
arr = np.array(im)
print('loaded', png, im.size)

ss = open('_sstate.bin', 'rb').read()
pal = open('_pal.bin', 'rb').read()
i = ss.find(b'OAMS'); oam = ss[i+12:i+12+1024]
# base tiles must match the canvas source: default = ORIGINAL Japanese VRAM tiles;
# pass 'current' as 2nd arg to edit on top of my Korean redraw (_fg_new.bin).
if len(sys.argv) > 2 and sys.argv[2] == 'current':
    FG = bytearray(open('_fg_new.bin', 'rb').read()); print('base: current Korean tiles')
else:
    FG = bytearray(open('_vram.bin', 'rb').read()[0x90000:0x90000+0x8000]); print('base: ORIGINAL Japanese tiles')
H, W = 224, 256

def palcol(pn):
    base = 0x200 + pn*32
    return [(((pal[base+k*2] | (pal[base+k*2+1] << 8)) & 31) << 3,
             (((pal[base+k*2] | (pal[base+k*2+1] << 8)) >> 5) & 31) << 3,
             (((pal[base+k*2] | (pal[base+k*2+1] << 8)) >> 10) & 31) << 3) for k in range(16)]
def nearest(cols, rgb):
    best, bi = 1 << 30, 1
    for k in range(1, 16):
        d = (cols[k][0]-rgb[0])**2 + (cols[k][1]-rgb[1])**2 + (cols[k][2]-rgb[2])**2
        if d < best: best, bi = d, k
    return bi
def rd(off, nib): return (FG[off] >> 4) if nib else (FG[off] & 0xF)
def wr(off, nib, v): FG[off] = (FG[off] & 0x0F) | (v << 4) if nib else (FG[off] & 0xF0) | (v & 0xF)

DIM = {(0,0):(1,1),(0,1):(2,2),(0,2):(4,4),(0,3):(8,8),(1,0):(2,1),(1,1):(4,1),
       (1,2):(4,2),(1,3):(8,4),(2,0):(1,2),(2,1):(1,4),(2,2):(2,4),(2,3):(4,8)}
sprites = []
for s in range(128):
    a0, a1, a2 = struct.unpack_from('<HHH', oam, s*8)
    if ((a0 >> 8) & 1) == 0 and ((a0 >> 9) & 1): continue
    shape=(a0>>14)&3; size=(a1>>14)&3; y=a0&0xFF; x=a1&0x1FF
    if x>=256: x-=512
    tile=a2&0x3FF; pn=(a2>>12)&0xF; w,h=DIM.get((shape,size),(1,1))
    if y<140: sprites.append(dict(s=s,x=x,y=y,w=w,h=h,tile=tile,pn=pn))

# per-pixel maps: covering sprites list, topmost owner, topmost NON-ZERO owner
cover = [[[] for _ in range(W)] for _ in range(H)]      # (pn, off, nib)
top   = [[None]*W for _ in range(H)]
disp  = [[None]*W for _ in range(H)]
# iterate bottom-to-top so the topmost (smallest s) is written last and wins
for sp in sorted(sprites, key=lambda q: -q['s']):
    for ty in range(sp['h']):
        for tx in range(sp['w']):
            ti = sp['tile'] + ty*32 + tx
            for py in range(8):
                sy = sp['y'] + ty*8 + py
                if not (0 <= sy < H): continue
                for px in range(8):
                    sx = sp['x'] + tx*8 + px
                    if not (0 <= sx < W): continue
                    off = ti*32 + py*4 + px//2; nib = px & 1
                    cover[sy][sx].append((sp['pn'], off, nib))
                    top[sy][sx] = (sp['pn'], off, nib)
                    if rd(off, nib) != 0:
                        disp[sy][sx] = (sp['pn'], off, nib)

changed = 0
for sy in range(H):
    for sx in range(W):
        if not cover[sy][sx]: continue
        r, g, b, a = (int(v) for v in arr[sy, sx])
        if a < 128:                                  # clear all covering -> transparent
            for pn, off, nib in cover[sy][sx]:
                if rd(off, nib) != 0: wr(off, nib, 0); changed += 1
        else:                                        # write owner only
            pn, off, nib = disp[sy][sx] or top[sy][sx]
            nv = nearest(palcol(pn), (r, g, b))
            if rd(off, nib) != nv: wr(off, nib, nv); changed += 1
print('tile pixels changed:', changed)
open('_fg_new.bin', 'wb').write(bytes(FG))
print('wrote _fg_new.bin  -> run: python _inject_title3.py ; python build_rom_all.py ; python _mkpatch.py')
