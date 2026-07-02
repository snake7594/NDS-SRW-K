# -*- coding: utf-8 -*-
"""_inject_titles.py — translate add04 anime series-title cards (IMG 140-153 +
SCR 154-167 + shared PLT 168) to Korean. Blue-gradient text + black outline,
IMG re-encoded with build_ecd2 (1024-ring), SCR replaced (fixed 768 entries).
Operates on kr/add04_patched.bin (which already carries the 96 ability plates)."""
import struct, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _enc1024b import build_ecd2
from PIL import Image, ImageFont, ImageDraw
import numpy as np

FONT = r"C:\Windows\Fonts\malgunbd.ttf"
# blue gradient nibbles (PLT@168): 1=black outline, fill bright->mid blue top->bottom
OUT_NIB = 1
FILL = [15, 15, 14, 13, 13, 12, 11, 11]

jp = Rom('../Super Robot Wars K (Japan).nds')
base = open('kr/add04_patched.bin', 'rb').read()
d = bytearray(base)
n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]

# KO titles: (block, [lines])
TITLES = {
 140:['기동전사 건담 SEED'], 141:['기동전사 건담 SEED DESTINY'],
 142:['기동전사 건담 SEED', 'C.E.73 -STARGAZER-'], 143:['오버맨 킹게이너'],
 144:['창궁의 파프너'], 145:['전뇌전기 버추얼 온 마즈'],
 146:['기수창세기 조이드 제네시스'], 147:['마징가 Z'], 148:['강철신 지그'],
 149:['가이킹', 'LEGEND OF DAIKU-MARYU'], 150:['파사대성 단가이오'],
 151:['신혼합체 고단나!!'], 152:['신혼합체 고단나!!', 'SECOND SEASON'],
 153:['건×소드'],
}

def fit_font(text, maxw, maxh, hi=22, lo=8):
    dd = ImageDraw.Draw(Image.new('L', (1,1)))
    for s in range(hi, lo-1, -1):
        f = ImageFont.truetype(FONT, s)
        bb = dd.textbbox((0,0), text, font=f)
        if bb[2]-bb[0] <= maxw and bb[3]-bb[1] <= maxh:
            return f
    return ImageFont.truetype(FONT, lo)

def render_canvas_nibbles(lines, row0, row1):
    """256x192 nibble grid, text lines centered in the tile-row band [row0,row1]."""
    W, H = 256, 192
    y0, y1 = row0*8, (row1+1)*8
    band = y1 - y0
    per = band // len(lines)
    mask = Image.new('L', (W, H), 0); dr = ImageDraw.Draw(mask)
    for li, text in enumerate(lines):
        f = fit_font(text, W-8, per-2)
        bb = dr.textbbox((0,0), text, font=f); tw = bb[2]-bb[0]; th = bb[3]-bb[1]
        x = max(2, (W-tw)//2); y = y0 + li*per + max(0,(per-th)//2) - bb[1]
        dr.text((x,y), text, fill=255, font=f)
    mp = mask.load()
    fill = [[mp[x,y] >= 110 for x in range(W)] for y in range(H)]
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if fill[y][x]: continue
            if any(0<=y+dy<H and 0<=x+dx<W and fill[y+dy][x+dx]
                   for dy in (-1,0,1) for dx in (-1,0,1)):
                grid[y][x] = OUT_NIB
    ys = [y for y in range(H) if any(fill[y])]
    ymin = min(ys) if ys else 0; ymax = max(ys) if ys else 1; span = max(1, ymax-ymin)
    for y in range(H):
        for x in range(W):
            if fill[y][x]:
                gi = int((y-ymin)/span*(len(FILL)-1)+0.5)
                grid[y][x] = FILL[max(0,min(len(FILL)-1,gi))]
    return grid

def grid_to_tiles_scr(grid):
    """32x24 tiles. tile 0 = transparent. returns (tile_data, scr_entries[768])."""
    tiles = [bytes(32)]; tmap = {bytes(32): 0}; scr = []
    for ty in range(24):
        for tx in range(32):
            tb = bytearray()
            for yy in range(8):
                for xx in range(0,8,2):
                    lo = grid[ty*8+yy][tx*8+xx] & 0xF
                    hi = grid[ty*8+yy][tx*8+xx+1] & 0xF
                    tb.append(lo|(hi<<4))
            tb = bytes(tb)
            if tb == bytes(32): scr.append(0); continue
            if tb not in tmap: tmap[tb] = len(tiles); tiles.append(tb)
            scr.append(tmap[tb])
    return b''.join(tiles), scr

ok = 0; fail = []
for i in range(14):
    blk = 140+i; scr_blk = 154+i
    orig_img = bytes(d[offs[blk]:offs[blk+1]])
    orig_scr = bytes(d[offs[scr_blk]:offs[scr_blk+1]])
    # original row band
    sd = decomp_1024(orig_scr)[0] if orig_scr[:4]==b'ECD\x01' else orig_scr
    ents = struct.unpack_from('<768H', sd, 8)
    rows = [ei//32 for ei,v in enumerate(ents) if v&0x3FF]
    r0, r1 = (min(rows), max(rows)) if rows else (10,14)
    grid = render_canvas_nibbles(TITLES[blk], r0, r1)
    tile_data, scr_ents = grid_to_tiles_scr(grid)
    ntiles = len(tile_data)//32
    if ntiles > 1024: fail.append((blk,'>1024 tiles')); continue
    h_tiles = (ntiles + 31)//32                      # rows of the 32-wide tile grid
    tile_data = tile_data + b'\x00'*(h_tiles*32*32 - len(tile_data))   # pad to full grid
    new_img = build_ecd2(orig_img, tile_data, new_preamble=b'IMG\x00'+struct.pack('<HH', 32, h_tiles))
    scr_bytes = struct.pack('<768H', *scr_ents)
    new_scr = b'SCR\x00'+sd[4:8]+scr_bytes if orig_scr[:4]!=b'ECD\x01' else build_ecd2(orig_scr, scr_bytes)
    if len(new_img) > len(orig_img): fail.append((blk, f'IMG {len(new_img)}>{len(orig_img)}')); continue
    if len(new_scr) > len(orig_scr): fail.append((blk, f'SCR {len(new_scr)}>{len(orig_scr)}')); continue
    d[offs[blk]:offs[blk+1]] = new_img + b'\x00'*(len(orig_img)-len(new_img))
    d[offs[scr_blk]:offs[scr_blk+1]] = new_scr + b'\x00'*(len(orig_scr)-len(new_scr))
    ok += 1; print(f'  t{i} blk{blk}: IMG {len(new_img)}/{len(orig_img)} SCR {len(new_scr)}/{len(orig_scr)} tiles={ntiles} OK')

print(f'titles injected {ok}/14; fails: {fail}')
assert len(bytes(d)) == len(base), 'size changed!'
open('kr/add04_patched.bin', 'wb').write(bytes(d))
print('saved kr/add04_patched.bin')
