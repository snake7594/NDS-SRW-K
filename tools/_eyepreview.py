# -*- coding: utf-8 -*-
"""Render a faithful eyecatch preview using the ACTUAL game font (arm9 0x4400A,
the KR-patched Korean glyphs) + the real starfield bg (add04 #16675), to show the
chapter eyecatch renders in Korean."""
import struct
import numpy as np
from PIL import Image
from srwk_rom import Rom
from srwk_codec import HAN2CODE
from _codec1024 import decomp_1024

KR = '../Super Robot Wars K (Korean)-기존패치.nds'
arm9 = bytes(Rom(KR).rom.arm9)
FONT = 0x4400A
recs = {}
i = FONT
while i + 26 <= len(arm9):
    code = struct.unpack_from('>H', arm9, i)[0]
    if not (0x814D <= code <= 0x9872):
        break
    recs[code] = arm9[i+2:i+26]
    i += 26
print('font records:', len(recs))

def glyph(code):
    b = recs.get(code)
    if not b:
        return None
    g = np.zeros((12, 16), np.uint8)
    for r in range(12):
        w = (b[r*2] << 8) | b[r*2+1]
        for c in range(16):
            if (w >> (15-c)) & 1:
                g[r, c] = 1
    return g

def code_of(ch):
    if ch in HAN2CODE:
        return HAN2CODE[ch]
    o = ord(ch)
    if 0x30 <= o <= 0x39:
        return 0x824F + (o - 0x30)        # fullwidth digits ０=0x824F
    if ch == '!':
        return 0x8149
    return None

def line_mask(text, scale):
    cells = []
    for ch in text:
        if ch == ' ':
            cells.append(None); continue
        c = code_of(ch); g = glyph(c) if c else None
        cells.append(g)
    gw = int(round(16*scale)); gh = int(round(12*scale))
    adv = int(round(13*scale))             # full-width advance ~13px * scale
    W = max(1, len(cells)*adv)
    m = np.zeros((gh, W), np.uint8)
    x = 0
    for g in cells:
        if g is not None:
            gg = np.kron(g, np.ones((int(round(scale)), int(round(scale))), np.uint8))
            h, w = gg.shape
            xoff = x + (adv - w)//2
            if xoff < 0:
                xoff = 0
            m[0:min(gh, h), xoff:xoff+w] = np.maximum(m[0:min(gh, h), xoff:xoff+w], gg[0:min(gh, h), :W-xoff])
        x += adv
    # trim to ink
    cols = np.where(m.any(axis=0))[0]
    if len(cols):
        m = m[:, cols.min():cols.max()+1]
    return m

# starfield bg (add04 #16675, 4bpp)
d = Rom(KR).get('data/add04dat.bin')
n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]
blk = d[offs[16675]:offs[16676]]
f3 = struct.unpack_from('>I', blk, 12)[0]
w, h = struct.unpack_from('<HH', blk, 20)
pix = decomp_1024(blk)[0][8:8+(f3-8)]
a = np.frombuffer(pix, np.uint8)
p = np.empty(len(a)*2, np.uint8); p[0::2] = a & 0xF; p[1::2] = a >> 4
p = p[:w*h*64].reshape(h, w, 8, 8)
star = np.zeros((h*8, w*8), np.uint8)
for ty in range(h):
    for tx in range(w):
        star[ty*8:ty*8+8, tx*8:tx*8+8] = p[ty, tx]

# canvas 256x192 dark purple space + stars
SCR_W, SCR_H = 256, 192
canvas = np.zeros((SCR_H, SCR_W, 3), np.uint8)
canvas[:, :] = (20, 12, 34)
sy = (SCR_H - star.shape[0])//2
canvas[sy:sy+star.shape[0], 0:star.shape[1]][star > 0] = (210, 205, 235)

def stamp(mask, cy, scr):
    mh, mw = mask.shape
    x0 = (SCR_W - mw)//2
    y0 = cy
    # outline (dark) then fill (white)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ys, xs = np.where(mask > 0)
            yy = ys + y0 + dy; xx = xs + x0 + dx
            ok = (yy >= 0) & (yy < SCR_H) & (xx >= 0) & (xx < SCR_W)
            scr[yy[ok], xx[ok]] = (15, 10, 30)
    ys, xs = np.where(mask > 0)
    yy = ys + y0; xx = xs + x0
    ok = (yy >= 0) & (yy < SCR_H) & (xx >= 0) & (xx < SCR_W)
    scr[yy[ok], xx[ok]] = (255, 255, 255)

# line 1: 제1화 (big), line 2: title (fit width)
hdr = line_mask('제1화', 2.4)
title_text = '웨딩벨은 싸움을 알리는 종'
sc = 1.9
tm = line_mask(title_text, sc)
while tm.shape[1] > SCR_W-16 and sc > 0.8:
    sc -= 0.1
    tm = line_mask(title_text, sc)
stamp(hdr, 38, canvas)
stamp(tm, 110, canvas)

img = Image.fromarray(canvas, 'RGB').resize((SCR_W*2, SCR_H*2), Image.NEAREST)
img.save('_eyepreview.png')
# also a font sanity montage 0x889F..
mont = Image.new('L', (16*16, 12), 0)
for k in range(16):
    g = glyph(0x889F + k)
    if g is not None:
        mont.paste(Image.fromarray(g*255, 'L'), (k*16, 0))
mont.resize((16*16*3, 12*3), Image.NEAREST).save('_fontcheck.png')
print('saved _eyepreview.png + _fontcheck.png (0x889F.. should be 가각간...)')
