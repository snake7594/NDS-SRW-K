# -*- coding: utf-8 -*-
"""Render preview of Korean eyecatch images from patched kr/data/add02dat.bin."""
import sys, io, os, struct
sys.stdout = io.TextIOWrapper(open('_render_ko_log.txt','wb'), encoding='utf-8')

from _codec1024 import decomp_1024
from PIL import Image

os.makedirs('_eye_ko', exist_ok=True)

d = open('kr/add02_patched.bin', 'rb').read()
n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]

# Load shared palette from PLT block 2213
plt_raw = d[offs[2213]:offs[2214]]
palette = []
for i in range(16):
    c = struct.unpack_from('<H', plt_raw, 8 + i*2)[0]
    r5 = c & 0x1F; g5 = (c>>5)&0x1F; b5 = (c>>10)&0x1F
    palette.append((r5<<3, g5<<3, b5<<3))

def render_eyecatch(img_dec, scr_dec):
    img_w, img_h = struct.unpack_from('<HH', img_dec, 4)
    tile_data = img_dec[8:]
    scr_entries = scr_dec[8:]
    out = Image.new('RGB', (256, 192), (0, 0, 0))
    px = out.load()
    for ty in range(24):
        for tx in range(32):
            ent = struct.unpack_from('<H', scr_entries, (ty*32+tx)*2)[0]
            tile_idx = ent & 0x3FF
            hflip = bool(ent & 0x400); vflip = bool(ent & 0x800)
            if tile_idx == 0: continue
            tile_off = tile_idx * 32
            if tile_off + 32 > len(tile_data): continue
            for y in range(8):
                sy = 7-y if vflip else y
                for x in range(8):
                    sx = 7-x if hflip else x
                    b = tile_data[tile_off + sy*4 + sx//2]
                    nib = (b & 0xF) if (sx & 1)==0 else (b >> 4)
                    if nib == 0: continue
                    px[tx*8+x, ty*8+y] = palette[nib]
    return out

for ch in range(1, 60):
    bi_img = 2214 + 2*(ch-1)
    bi_scr = 2215 + 2*(ch-1)
    try:
        img_dec = decomp_1024(d[offs[bi_img]:offs[bi_img+1]])[0]
        scr_dec = decomp_1024(d[offs[bi_scr]:offs[bi_scr+1]])[0]
        rendered = render_eyecatch(img_dec, scr_dec)
        crop = rendered.crop((0, 48, 256, 120)).resize((512, 144), Image.NEAREST)
        crop.save('_eye_ko/ch%02d.png' % ch)
        print('ch%02d OK tiles=%d' % (ch, struct.unpack_from('<H',img_dec,4)[0]))
    except Exception as e:
        print('ch%02d ERROR: %s' % (ch, e))

sys.stdout.flush()
print('Done.')
