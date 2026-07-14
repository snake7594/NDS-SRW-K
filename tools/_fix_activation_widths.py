# -*- coding: utf-8 -*-
"""_fix_activation_widths.py — the battle activation popup crops each graphic to
the JP original's art width, so Korean ink must fit inside the JP ink bbox.

  A) add02 spirit/item blocks where KR ink exceeded the JP right edge (9 blocks,
     e.g. 탄창 회복 was cut to "탄창 회") -> re-render constrained to the JP bbox
     (left = JP x0, right <= JP x1). Space kept if font >= MIN_KEEP_SPACE, else
     dropped (탄창회복). Style identical to _inject_spirit.py (rowfill gradient
     from JP 2175, nib1 outline).
  B) add04 IMG#14 크리티컬: v1.5 centered the text leaving side gaps; JP ink fills
     x1..63 of its 64px window, so the neighbouring atlas tiles peeked at the
     right. Re-render with per-char spread so ink spans x1..63 like JP.

Edits kr/add02_patched.bin + kr/add04_patched.bin in place. --write to save."""
import io, sys, struct, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _enc1024b import build_ecd2
from PIL import Image, ImageFont, ImageDraw
import numpy as np

FONT = r"C:\Windows\Fonts\malgunbd.ttf"
MIN_KEEP_SPACE = 12          # drop spaces if autofit font would fall below this

jp2 = Rom('../Super Robot Wars K (Japan).nds').get('data/add02dat.bin')
def blocks(d):
    ne = struct.unpack_from('<I', d, 0)[0]//4
    return list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]
oj = blocks(jp2)

def dec(d, offs, bi):
    raw = bytes(d[offs[bi]:offs[bi+1]])
    return decomp_1024(raw)[0] if raw[:4] == b'ECD\x01' else raw

def to_grid(r):
    w, h = struct.unpack_from('<HH', r, 4); tile = r[8:]
    g = np.zeros((h*8, w*8), np.uint8)
    for ty in range(h):
        for tx in range(w):
            off = (ty*w+tx)*32
            for yy in range(8):
                for xx in range(8):
                    b = tile[off+yy*4+xx//2]
                    g[ty*8+yy, tx*8+xx] = (b & 0xF) if (xx & 1) == 0 else (b >> 4)
    return g

def jp_bbox(bi):
    g = to_grid(dec(jp2, oj, bi))
    ys, xs = np.where(g > 0)
    return int(xs.min()), int(xs.max())

# rowfill gradient from JP 2175 (加速) — same as _inject_spirit.py
r = dec(jp2, oj, 2175); w175, h175 = struct.unpack_from('<HH', r, 4); t175 = r[8:]
rowfill = []
for py in range(h175*8):
    cnt = collections.Counter()
    ty, yy = py//8, py % 8
    for tx in range(w175):
        off = (ty*w175+tx)*32
        for xx in range(8):
            b = t175[off+yy*4+xx//2]; nib = (b & 0xF) if (xx & 1) == 0 else (b >> 4)
            if nib not in (0, 1): cnt[nib] += 1
    rowfill.append(cnt.most_common(1)[0][0] if cnt else 15)

FIX = {   # block: KO text (space variant tried first)
    2154: '강철 파워', 2158: '블래스터화', 2160: '탄창 회복',
    2161: '프로펠런트 탱크', 2163: '리페어 키트', 2164: '슈퍼 리페어 키트',
    2200: '크리스탈 하트', 2201: '레 미이의 통구이', 2202: '크리슈나 하트',
}

def autofit(text, maxw):
    dd = ImageDraw.Draw(Image.new('L', (1, 1)))
    for s in range(16, 7, -1):
        f = ImageFont.truetype(FONT, s)
        bb = dd.textbbox((0, 0), text, font=f)
        if bb[2]-bb[0] <= maxw and bb[3]-bb[1] <= 15:
            return f, s, bb
    f = ImageFont.truetype(FONT, 8)
    return f, 8, dd.textbbox((0, 0), text, font=f)

def grid_from_mask(mask, W=128, H=16):
    mp = mask.load()
    fill = [[mp[x, y] >= 110 for x in range(W)] for y in range(H)]
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if fill[y][x]: continue
            if any(0 <= y+dy < H and 0 <= x+dx < W and fill[y+dy][x+dx]
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
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
                for xx in range(0, 8, 2):
                    out.append((grid[ty*8+yy][tx*8+xx] & 0xF) |
                               ((grid[ty*8+yy][tx*8+xx+1] & 0xF) << 4))
    return bytes(out)

# ---------- A) spirit/item blocks ----------
a2 = bytearray(open('kr/add02_patched.bin', 'rb').read())
o2 = blocks(a2)
for bi, ko in sorted(FIX.items()):
    jx0, jx1 = jp_bbox(bi)
    budget = jx1 - jx0 + 1 - 1          # 1px safety inside the JP right edge
    f, s, bb = autofit(ko, budget)
    used = ko
    if ' ' in ko and s < MIN_KEEP_SPACE:
        alt = ko.replace(' ', '')
        f2, s2, bb2 = autofit(alt, budget)
        if s2 > s: f, s, bb, used = f2, s2, bb2, alt
    mask = Image.new('L', (128, 16), 0)
    dr = ImageDraw.Draw(mask)
    th = bb[3]-bb[1]
    dr.text((jx0 - bb[0], max(0, (16-th)//2) - bb[1]), used, fill=255, font=f)
    tiles = grid_to_tiles(grid_from_mask(mask))
    orig = bytes(a2[o2[bi]:o2[bi+1]])
    new = build_ecd2(orig, tiles, new_preamble=b'IMG\x00'+struct.pack('<HH', 16, 2))
    ok = len(new) <= len(orig)
    # measure new ink
    xs = [x for y in range(16) for x in range(128) if grid_from_mask(mask)[y][x]]
    print(f"  {bi} '{used}' font{s}: JP x{jx0}..{jx1} | {'FITS' if ok else 'ECD-OVERFLOW'} ({len(new)}/{len(orig)}B)")
    assert ok
    a2[o2[bi]:o2[bi+1]] = new + b'\x00'*(len(orig)-len(new))

# ---------- B) add04 #14 크리티컬 spread to x1..63 ----------
a4 = bytearray(open('kr/add04_patched.bin', 'rb').read())
o4 = blocks(a4)
img = bytearray(dec(a4, o4, 14)); w14, h14 = struct.unpack_from('<HH', img, 4)
assert (w14, h14) == (32, 4)
W, H = 64, 16
text = '크리티컬'
fs = 12
f = ImageFont.truetype(FONT, fs)
dd = ImageDraw.Draw(Image.new('L', (1, 1)))
cw = [dd.textbbox((0, 0), c, font=f)[2]-dd.textbbox((0, 0), c, font=f)[0] for c in text]
X0, X1 = 1, 63
total = sum(cw); slots = len(text)
gap = (X1 - X0 + 1 - total) / (slots - 1) if slots > 1 else 0
mask = Image.new('L', (W, H), 0); dr = ImageDraw.Draw(mask)
x = float(X0)
bbh = dd.textbbox((0, 0), text, font=f); th = bbh[3]-bbh[1]
for i, c in enumerate(text):
    bb = dd.textbbox((0, 0), c, font=f)
    dr.text((round(x) - bb[0], max(0, (H-th)//2) - bbh[1]), c, fill=255, font=f)
    x += cw[i] + gap
mp = mask.load()
fill = [[mp[xx, yy] >= 110 for xx in range(W)] for yy in range(H)]
FILL = [12, 12, 11, 11, 10, 10, 10, 10]
grid = [[0]*W for _ in range(H)]
for y in range(H):
    for xx in range(W):
        if fill[y][xx]: continue
        if any(0 <= y+dy < H and 0 <= xx+dx < W and fill[y+dy][xx+dx]
               for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
            grid[y][xx] = 1
ys = [y for y in range(H) if any(fill[y])]; y0, y1 = min(ys), max(ys); span = max(1, y1-y0)
for y in range(H):
    for xx in range(W):
        if fill[y][xx]:
            grid[y][xx] = FILL[max(0, min(7, int((y-y0)/span*7+0.5)))]
xs = [xx for y in range(H) for xx in range(W) if grid[y][xx]]
print(f"  add04#14 크리티컬 spread: ink x{min(xs)}..{max(xs)} (target 1..63)")
tdata = bytearray(img[8:])
def tile_bytes(ty, tx):
    b = bytearray()
    for yy in range(8):
        for xx in range(0, 8, 2):
            b.append((grid[ty*8+yy][tx*8+xx] & 0xF) | ((grid[ty*8+yy][tx*8+xx+1] & 0xF) << 4))
    return bytes(b)
for c in range(8):
    for grow, idx in ((0, 24+c), (1, 56+c)):
        tdata[idx*32:(idx+1)*32] = tile_bytes(grow, c)
orig14 = bytes(a4[o4[14]:o4[15]])
new14 = build_ecd2(orig14, bytes(tdata), new_preamble=bytes(img[:8]))
print(f"  #14 re-encode {len(new14)}/{len(orig14)}B {'OK' if len(new14)<=len(orig14) else 'OVERFLOW'}")
assert len(new14) <= len(orig14)
a4[o4[14]:o4[15]] = new14 + b'\x00'*(len(orig14)-len(new14))

if '--write' in sys.argv:
    open('kr/add02_patched.bin', 'wb').write(bytes(a2))
    open('kr/add04_patched.bin', 'wb').write(bytes(a4))
    print("WROTE kr/add02_patched.bin + kr/add04_patched.bin")
else:
    print("(dry run — pass --write to save)")
