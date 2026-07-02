# -*- coding: utf-8 -*-
"""_plate_lib.py — render Korean ability/status plates matching add04's style
(yellow→orange gradient fill + black outline, transparent bg) and pack to 4bpp
tiles using the shared palette block 12. Blocks 23-119 are UNCOMPRESSED fixed-size
IMG (80x16 or 128x16) → direct tile replacement.
"""
import struct
from PIL import Image, ImageFont, ImageDraw

FONT = r"C:\Windows\Fonts\malgunbd.ttf"

# palette-12 nibble roles (verified from add04 block 12)
NIB_BG=0; NIB_OUTLINE=2
# gradient top->bottom: yellow(11) amber(10) orange(9)
GRAD=[11,11,10,10,10,9,9,9]   # per-row nibble for a 16px glyph band (8..15 area)

def _fit_font(text, maxw, maxh, sizes):
    d=ImageDraw.Draw(Image.new('L',(1,1)))
    for s in sizes:
        f=ImageFont.truetype(FONT,s)
        bb=d.textbbox((0,0),text,font=f)
        if bb[2]-bb[0]<=maxw and bb[3]-bb[1]<=maxh: return f,(bb[2]-bb[0],bb[3]-bb[1],bb[1])
    f=ImageFont.truetype(FONT,sizes[-1]); bb=d.textbbox((0,0),text,font=f)
    return f,(bb[2]-bb[0],bb[3]-bb[1],bb[1])

def render_nibbles(text, w, h):
    """Return h×w numpy-free nibble grid (list of lists) for KR text, plate style."""
    text=text.replace('·','·')
    # render white text mask at target, auto-fit
    maxw=w-4; maxh=h-3
    font,(tw,th,oy)=_fit_font(text,maxw,maxh,list(range(15,6,-1)))
    mask=Image.new('L',(w,h),0); dr=ImageDraw.Draw(mask)
    x=max(1,(w-tw)//2); y=max(0,(h-th)//2)-oy
    dr.text((x,y),text,fill=255,font=font)
    mp=mask.load()
    # build fill set (alpha>=128) and outline (neighbors of fill not in fill)
    fill=[[mp[xx,yy]>=110 for xx in range(w)] for yy in range(h)]
    grid=[[NIB_BG]*w for _ in range(h)]
    # first outline (so fill overwrites center)
    for yy in range(h):
        for xx in range(w):
            if fill[yy][xx]: continue
            near=False
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    ny,nx=yy+dy,xx+dx
                    if 0<=ny<h and 0<=nx<w and fill[ny][nx]: near=True
            if near: grid[yy][xx]=NIB_OUTLINE
    # fill with vertical gradient (relative to text band)
    ys=[yy for yy in range(h) if any(fill[yy])]
    y0=min(ys) if ys else 0; y1=max(ys) if ys else h-1
    span=max(1,y1-y0)
    for yy in range(h):
        for xx in range(w):
            if fill[yy][xx]:
                gi=int((yy-y0)/span*(len(GRAD)-1)+0.5)
                grid[yy][xx]=GRAD[max(0,min(len(GRAD)-1,gi))]
    return grid

def nibbles_to_tiles(grid, w, h):
    """grid h×w nibbles -> 4bpp NDS tile bytes (w/8 × h/8 tiles, row-major, 4B/row)."""
    tw,th=w//8,h//8
    out=bytearray()
    for ty in range(th):
        for tx in range(tw):
            for yy in range(8):
                for xx in range(0,8,2):
                    lo=grid[ty*8+yy][tx*8+xx]&0xF
                    hi=grid[ty*8+yy][tx*8+xx+1]&0xF
                    out.append(lo|(hi<<4))
    return bytes(out)

def build_img_block(text, w, h):
    """Full IMG block bytes: 'IMG\\x00' + w/8,h/8 + tile data. Matches uncompressed plate."""
    grid=render_nibbles(text,w,h)
    tiles=nibbles_to_tiles(grid,w,h)
    return b'IMG\x00'+struct.pack('<HH',w//8,h//8)+tiles
