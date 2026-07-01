# -*- coding: utf-8 -*-
"""Inject Korean text into copyright screens (bi02371/02373),
bandai credit (bi01880), and save system messages (bi01119).

cp1/cp2/bandai: full canvas_to_4bpp approach (replaces IMG+SCR).
save (bi01119): tile-replacement approach (SCRs 1120/1121/1122 unchanged,
  only the text tile bytes in IMG are overwritten).
"""
import sys, io, struct
sys.stdout = io.TextIOWrapper(open('_inject_misc_log.txt','wb'), encoding='utf-8')

from _codec1024 import decomp_1024
from _enc1024b  import build_ecd2
from PIL import Image, ImageFont, ImageDraw

FONT_PATH = r"C:\Windows\Fonts\malgunbd.ttf"  # Malgun Gothic Bold

KR_ADD02 = 'kr/add02_patched.bin'

# ── nibble mapping ────────────────────────────────────────────────────────────
def rgba_to_nibble(r, g, b, a):
    if a == 0: return 0
    # Map luminance → palette index: black(0,0,0)→1, white(255,255,255)→15
    luma = (r + g + b) // 3
    return max(1, min(15, round(luma * 14 / 255) + 1))

def _norm(s):
    return s.replace('・', '·').replace('〜', '~').replace('​', '')

# ── canvas_to_4bpp (same logic as eyecatch) ───────────────────────────────────
def canvas_to_4bpp(canvas):
    """RGBA 256×192 → (tile_data_bytes, scr_entries_768)."""
    tiles   = [bytes(32)]   # tile 0 = transparent
    tile_map= {}
    scr     = []
    px = canvas.load()
    for ty in range(24):
        for tx in range(32):
            row=[]; nonempty=False
            for y in range(8):
                for xi in range(0,8,2):
                    n0=rgba_to_nibble(*px[tx*8+xi,   ty*8+y])
                    n1=rgba_to_nibble(*px[tx*8+xi+1, ty*8+y])
                    row.append(n0|(n1<<4))
                    if n0 or n1: nonempty=True
            if not nonempty:
                scr.append(0)
            else:
                tb=bytes(row)
                if tb not in tile_map:
                    tile_map[tb]=len(tiles); tiles.append(tb)
                scr.append(tile_map[tb])
    return b''.join(tiles), scr

def patch_img_scr(kr_mut, offs, img_bi, scr_bi, canvas, label):
    orig_img = bytes(kr_mut[offs[img_bi]:offs[img_bi+1]])
    orig_scr = bytes(kr_mut[offs[scr_bi]:offs[scr_bi+1]])
    tile_data, scr_entries = canvas_to_4bpp(canvas)
    num_tiles = len(tile_data) // 32
    new_img_preamble = b'IMG\x00' + struct.pack('<HH', num_tiles, 1)
    new_img_ecd = build_ecd2(orig_img, tile_data, new_preamble=new_img_preamble)
    scr_bytes = struct.pack('<%dH' % len(scr_entries), *scr_entries)
    new_scr_ecd = build_ecd2(orig_scr, scr_bytes)
    if len(new_img_ecd) > len(orig_img):
        raise RuntimeError(f"{label} IMG overflow: {len(new_img_ecd)}>{len(orig_img)}")
    if len(new_scr_ecd) > len(orig_scr):
        raise RuntimeError(f"{label} SCR overflow: {len(new_scr_ecd)}>{len(orig_scr)}")
    new_img = new_img_ecd + b'\x00'*(len(orig_img)-len(new_img_ecd))
    new_scr = new_scr_ecd + b'\x00'*(len(orig_scr)-len(new_scr_ecd))
    kr_mut[offs[img_bi]:offs[img_bi+1]] = new_img
    kr_mut[offs[scr_bi]:offs[scr_bi+1]] = new_scr
    print(f"  {label} IMG: {len(new_img_ecd)}/{len(orig_img)}  SCR: {len(new_scr_ecd)}/{len(orig_scr)}")

def draw_line(draw, text, font, canvas_w, y):
    """Draw text centered horizontally at y, returning bbox."""
    text = _norm(text)
    bb = draw.textbbox((0,0), text, font=font)
    w = bb[2]-bb[0]
    x = max(0, (canvas_w - w) // 2)
    draw.text((x, y), text, font=font, fill=(255,255,255,255))
    return w

def auto_font(text, max_w, sizes, font_path=FONT_PATH):
    """Return (font, width) using largest size that fits max_w."""
    text = _norm(text)
    for size in sizes:
        f = ImageFont.truetype(font_path, size)
        bb = ImageDraw.Draw(Image.new('RGBA',(1,1))).textbbox((0,0), text, font=f)
        w = bb[2]-bb[0]
        if w <= max_w:
            return f, w
    f = ImageFont.truetype(font_path, min(sizes))
    bb = ImageDraw.Draw(Image.new('RGBA',(1,1))).textbbox((0,0), text, font=f)
    return f, bb[2]-bb[0]

# ── copyright screens helper ──────────────────────────────────────────────────
def make_copyright_canvas(lines_y, lines_text, line_w_hints):
    """
    lines_y: list of (y_start, y_end) for each text band
    lines_text: list of text strings
    line_w_hints: available pixel widths
    Returns 256×192 RGBA canvas.
    """
    canvas = Image.new('RGBA', (256,192), (0,0,0,255))  # opaque black bg → nibble 1
    draw = ImageDraw.Draw(canvas)
    for (y0,y1), text, avail_w in zip(lines_y, lines_text, line_w_hints):
        band_h = y1 - y0  # typically 16
        # pick font size
        sizes = [13, 12, 11, 10, 9, 8]
        font, tw = auto_font(text, avail_w, sizes)
        bb = draw.textbbox((0,0), _norm(text), font=font)
        th = bb[3]-bb[1]
        x = max(0, (256-tw)//2)
        y = y0 + max(0, (band_h-th)//2)
        draw.text((x,y), _norm(text), font=font, fill=(255,255,255,255))
    return canvas

# ── load kr/add02_patched.bin ─────────────────────────────────────────────────
kr_raw = open(KR_ADD02,'rb').read()
n0 = struct.unpack_from('<I',kr_raw,0)[0]; ne = n0//4
offs = list(struct.unpack_from('<%dI'%ne,kr_raw,0))+[len(kr_raw)]
kr_mut = bytearray(kr_raw)

print(f"add02dat: {ne} blocks, {len(kr_raw)} bytes")

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Copyright screen 1 (PLT@2370, IMG@2371, SCR@2372)
#    6 text bands. Lines 4+5 (row13+15) are 2 wrapped lines of the SEGA credit.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[cp1] bi02371/02372")
CP1_BANDS = [(32,48),(56,72),(80,96),(104,120),(120,136),(144,160)]
CP1_TEXT  = [
    "©AIC·EMOTION",
    "©SUNRISE·BV·WOWOW",
    "©XEBEC·류궁도 관청",
    "©SEGA, 2003, CHARACTERS ©AUTOMUSS",
    "CHARACTER DESIGN:KATOKI HAJIME",
    "©소츠·선라이즈·마이니치 방송",
]
CP1_WIDTHS = [96, 120, 104, 208, 184, 128]
canvas = make_copyright_canvas(CP1_BANDS, CP1_TEXT, CP1_WIDTHS)
patch_img_scr(kr_mut, offs, 2371, 2372, canvas, "cp1")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. Copyright screen 2 (PLT@2370, IMG@2373, SCR@2374)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[cp2] bi02373/02374")
CP2_BANDS = [(24,40),(48,64),(72,88),(96,112),(120,136),(144,160)]
CP2_TEXT  = [
    "©다이나믹 기획",
    "©테레비 아사히·토에이 애니메이션",
    "©나가이 고/다이나믹 기획·빌드베이스",
    "© 1983 2009 TOMY © ShoPro",
    "©2003 ProjectGODANNAR",
    "©2005 AIC·팀 단체스터/건소드 파트너즈",
]
CP2_WIDTHS = [80, 144, 176, 144, 128, 196]
canvas = make_copyright_canvas(CP2_BANDS, CP2_TEXT, CP2_WIDTHS)
patch_img_scr(kr_mut, offs, 2373, 2374, canvas, "cp2")

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Bandai Namco credit (PLT@1879, IMG@1880, SCR@1881)
#    "Produced by" at y=64-79, company name at y=96-111.
#    Decorative row11 (y=88-95) becomes transparent — acceptable.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[bandai] bi01880/01881")
BANDAI_BANDS  = [(64,80),(96,112)]
BANDAI_TEXT   = ["Produced by", "주식회사 반다이남코게임스"]
BANDAI_WIDTHS = [96, 240]
canvas = make_copyright_canvas(BANDAI_BANDS, BANDAI_TEXT, BANDAI_WIDTHS)
patch_img_scr(kr_mut, offs, 1880, 1881, canvas, "bandai")

# ═══════════════════════════════════════════════════════════════════════════════
# 4. Save system messages (IMG@1119, SCRs @1120/1121/1122)
#
#    IMG is 32×8=256 tiles shared by 3 SCRs.
#    We ONLY replace text tile bytes; SCRs are untouched.
#
#    Text tile slots per SCR:
#      SCR0 row10+11 (tx=12..19, 8tiles=64px): tiles 1-8 (top), 33-40 (bot)
#      SCR0 row12+13 (tx=8..23, 16tiles=128px): tiles 64-79 (top), 96-111 (bot)
#      SCR1 row10+11 (tx=9..22, 14tiles=112px): tiles 18-31 (top), 50-63 (bot)
#      SCR1+2 row12+13 (tx=3..28, 26tiles=208px): tiles 128-153 (top), 160-185 (bot)
#      SCR2 row10+11 (tx=9..22, 14tiles=112px): tiles 82-95 (top), 114-127 (bot)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[save] bi01119")

def rgba_to_nibble_simple(r, g, b, a):
    if a == 0: return 0
    return max(1, min(15, round(a * 15 / 255)))

def render_text_to_tile_bytes(text, avail_w, n_tiles_wide, sizes=(10,9,8,7)):
    """Render text on (n_tiles_wide*8) × 16 canvas (2 tile rows).
    Uses binary alpha threshold (no AA) to maximize compression.
    Returns list of 2*n_tiles_wide tile byte strings (row0 cols, then row1 cols)."""
    w = n_tiles_wide * 8
    canvas = Image.new('RGBA', (w, 16), (0,0,0,0))
    draw = ImageDraw.Draw(canvas)
    font, tw = auto_font(text, min(w, avail_w), list(sizes))
    bb = draw.textbbox((0,0), _norm(text), font=font)
    th = bb[3]-bb[1]
    x = max(0, (w-tw)//2)
    y = max(0, (16-th)//2)
    draw.text((x,y), _norm(text), font=font, fill=(255,255,255,255))
    px = canvas.load()
    tiles = []
    for ty in range(2):          # 2 tile rows in 16px
        for tx in range(n_tiles_wide):
            row = []
            for y in range(8):
                for xi in range(0,8,2):
                    # Binary threshold: alpha>=128 → nibble 15, else 1 (black)
                    n0 = 15 if px[tx*8+xi,   ty*8+y][3] >= 128 else 1
                    n1 = 15 if px[tx*8+xi+1, ty*8+y][3] >= 128 else 1
                    row.append(n0|(n1<<4))
            tiles.append(bytes(row))
    # tiles[0..n_tiles_wide-1] = row0; tiles[n_tiles_wide..] = row1
    return tiles

def write_text_tiles(tile_data, top_range, bot_range, tiles):
    """Write rendered tile bytes into tile_data bytearray at given index ranges."""
    n = len(top_range)
    assert len(tiles) == n*2, f"tile count mismatch: got {len(tiles)}, need {n*2}"
    for i, idx in enumerate(top_range):
        tile_data[idx*32:(idx+1)*32] = tiles[i]
    for i, idx in enumerate(bot_range):
        tile_data[idx*32:(idx+1)*32] = tiles[n+i]

# Decode original save IMG
orig_img_raw = bytes(kr_mut[offs[1119]:offs[1120]])
img_dec = decomp_1024(orig_img_raw)[0]
tile_data = bytearray(img_dec[8:])   # 256 tiles × 32 bytes = 8192 bytes

# SCR0 row10+11 (64px, 8 tiles): "저장 중입니다."
tiles = render_text_to_tile_bytes("저장 중입니다.", 64, 8, sizes=(9,8,7))
write_text_tiles(tile_data, range(1,9), range(33,41), tiles)
print("  SCR0 row10+11: 저장 중입니다.")

# SCR0 row12+13 (128px, 16 tiles): "전원을 끄지 마세요."
tiles = render_text_to_tile_bytes("전원을 끄지 마세요.", 128, 16, sizes=(10,9,8))
write_text_tiles(tile_data, range(64,80), range(96,112), tiles)
print("  SCR0 row12+13: 전원을 끄지 마세요.")

# SCR1 row10+11 (112px, 14 tiles): "데이터를 읽을 수 없습니다."
tiles = render_text_to_tile_bytes("데이터를 읽을 수 없습니다.", 112, 14, sizes=(10,9,8))
write_text_tiles(tile_data, range(18,32), range(50,64), tiles)
print("  SCR1 row10+11: 데이터를 읽을 수 없습니다.")

# SCR1+2 row12+13 (208px, 26 tiles): "전원을 끄고 카드를 다시 삽입해 주세요."
tiles = render_text_to_tile_bytes("전원을 끄고 카드를 다시 삽입해 주세요.", 208, 26, sizes=(10,9,8))
write_text_tiles(tile_data, range(128,154), range(160,186), tiles)
print("  SCR1+2 row12+13: 전원을 끄고 카드를 다시 삽입해 주세요.")

# SCR2 row10+11 (112px, 14 tiles): "데이터를 쓸 수 없습니다."
tiles = render_text_to_tile_bytes("데이터를 쓸 수 없습니다.", 112, 14, sizes=(10,9,8))
write_text_tiles(tile_data, range(82,96), range(114,128), tiles)
print("  SCR2 row10+11: 데이터를 쓸 수 없습니다.")

# Re-encode IMG with same preamble (32×8 tiles, unchanged dimensions)
preamble = b'IMG\x00' + struct.pack('<HH', 32, 8)
new_img_ecd = build_ecd2(orig_img_raw, bytes(tile_data), new_preamble=preamble)
if len(new_img_ecd) > len(orig_img_raw):
    raise RuntimeError(f"save IMG overflow: {len(new_img_ecd)}>{len(orig_img_raw)}")
new_img = new_img_ecd + b'\x00'*(len(orig_img_raw)-len(new_img_ecd))
kr_mut[offs[1119]:offs[1120]] = new_img
print(f"  save IMG: {len(new_img_ecd)}/{len(orig_img_raw)}")

# ═══════════════════════════════════════════════════════════════════════════════
# Write output
# ═══════════════════════════════════════════════════════════════════════════════
out = KR_ADD02
open(out,'wb').write(bytes(kr_mut))
assert len(bytes(kr_mut))==len(kr_raw), "Archive size changed!"
print(f"\nSaved {out} ({len(kr_mut)} bytes)")

# ── Quick preview renders ─────────────────────────────────────────────────────
from srwk_rom import Rom

# Load JP rom for palette
jp = Rom('../Super Robot Wars K (Japan).nds')
jp_d = jp.get('data/add02dat.bin')
jp_n0 = struct.unpack_from('<I',jp_d,0)[0]; jp_ne=jp_n0//4
jp_offs = list(struct.unpack_from('<%dI'%jp_ne,jp_d,0))+[len(jp_d)]
def jp_dec(bi):
    raw=jp_d[jp_offs[bi]:jp_offs[bi+1]]
    return decomp_1024(raw)[0] if raw[:4]==b'ECD\x01' else raw
def parse_plt(bi):
    raw=jp_dec(bi)
    return [(((c:=struct.unpack_from('<H',raw,8+i*2)[0])&0x1F)<<3,
             ((c>>5)&0x1F)<<3, ((c>>10)&0x1F)<<3) for i in range(16)]

# Reload patched archive for preview
kr2 = open(KR_ADD02,'rb').read()
kr_n0=struct.unpack_from('<I',kr2,0)[0]; kr_offs=list(struct.unpack_from('<%dI'%(kr_n0//4),kr2,0))+[len(kr2)]
def kr_dec(bi):
    raw=kr2[kr_offs[bi]:kr_offs[bi+1]]
    return decomp_1024(raw)[0] if raw[:4]==b'ECD\x01' else raw

def preview(img_bi, scr_bi, plt_bi, out_name, scale=3):
    pal=parse_plt(plt_bi)
    img_d=kr_dec(img_bi); scr_d=kr_dec(scr_bi)
    tile=img_d[8:]; n=(len(scr_d)-8)//2
    ents=list(struct.unpack_from('<%dH'%n,scr_d,8))
    out=Image.new('RGB',(256*scale,192*scale),(30,30,30))
    px=out.load()
    for ty in range(24):
        for tx in range(32):
            ent=ents[ty*32+tx]; ti=ent&0x3FF
            hf=bool(ent&0x400); vf=bool(ent&0x800)
            if ti==0: continue
            off=ti*32
            if off+32>len(tile): continue
            for y in range(8):
                sy=7-y if vf else y
                for x in range(8):
                    sx=7-x if hf else x
                    b=tile[off+sy*4+sx//2]
                    nib=(b&0xF) if (sx&1)==0 else (b>>4)
                    if nib==0: continue
                    for dy in range(scale):
                        for dx in range(scale):
                            px[tx*8*scale+x*scale+dx,ty*8*scale+y*scale+dy]=pal[nib]
    out.save(out_name)
    print(f"  preview -> {out_name}")

print("\n[previews]")
preview(2371,2372,2370,'_preview_cp1.png')
preview(2373,2374,2370,'_preview_cp2.png')
preview(1880,1881,1879,'_preview_bandai.png')
preview(1119,1120,1116,'_preview_save0.png')
preview(1119,1121,1116,'_preview_save1.png')
preview(1119,1122,1116,'_preview_save2.png')

print("\nDone.")
sys.stdout.flush()
