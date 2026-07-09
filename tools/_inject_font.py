# -*- coding: utf-8 -*-
"""_inject_font.py — replace the KR dialogue-font hangul glyphs with Galmuri11
(11px bitmap font). The font lives in arm9 as SJIS-indexed 26-byte records:
  offset(code) = FONT_BASE + sjis_idx(code)*26 ; record = [code:2 BE][glyph:24]
  glyph = 12 rows x 2 bytes (16-bit, MSB=left); ink uses the left 12 columns.
For every hangul in HAN2CODE we render its Galmuri11 glyph into the 12x12 cell
and overwrite the 24 glyph bytes IN PLACE (arm9 size unchanged). A per-record
prefix==code guard means a mis-computed slot is skipped, never corrupted.

Reads/writes kr/arm9_patched.bin (so the name/message fixes are preserved).
--verify emits a before/after montage; --write saves."""
import io, sys, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from PIL import Image, ImageFont, ImageDraw
from srwk_codec import HAN2CODE, CODE2HAN

FONT_TTF = 'Galmuri11.ttf'
FONT_PX  = 12          # em=1200 -> 100 units/px at size 12: grid-exact (0 AA) & fills the 12x12 cell
FONT_BASE = 0x43EB8
S = 26
X_OFF, Y_OFF = 0, 0     # placement of the glyph inside the 12x12 cell

def sjis_idx(code):
    hi, lo = code >> 8, code & 0xFF
    return (hi - 0x81) * 188 + (lo - 0x40) - (1 if lo > 0x7F else 0)

def off(code):
    return FONT_BASE + sjis_idx(code) * S

arm9 = bytearray(open('kr/arm9_patched.bin', 'rb').read())
ORIG_LEN = len(arm9)
def u16be(o): return (arm9[o] << 8) | arm9[o+1]

gfont = ImageFont.truetype(FONT_TTF, FONT_PX)

def render_glyph(ch):
    """12x12 1bpp grid (list of 12 rows of 12 bits) for `ch` in Galmuri11."""
    im = Image.new('L', (16, 16), 0)
    dr = ImageDraw.Draw(im)
    dr.text((X_OFF, Y_OFF), ch, fill=255, font=gfont)
    px = im.load()
    return [[1 if px[x, y] >= 128 else 0 for x in range(12)] for y in range(12)]

def grid_to_bytes(grid):
    out = bytearray()
    for y in range(12):
        w16 = 0
        for x in range(12):
            if grid[y][x]:
                w16 |= 1 << (15 - x)
        out += struct.pack('>H', w16)
    return bytes(out)          # 24 bytes

def cur_grid(o):
    return [[(u16be(o+2+y*2) >> (15-x)) & 1 for x in range(12)] for y in range(12)]

written = 0; skipped = []
samples = {}
for code, ch in ((c, CODE2HAN.get(c)) for c in sorted(set(HAN2CODE.values()))):
    if ch is None:
        continue
    o = off(code)
    if not (0 <= o < len(arm9)-25) or u16be(o) != code:
        skipped.append((ch, hex(code)))
        continue
    if ch in ('가', '한', '로', '봇', '슈', '퍼', '전', '대', '무', '적'):
        samples[ch] = (cur_grid(o), render_glyph(ch))
    arm9[o+2:o+2+24] = grid_to_bytes(render_glyph(ch))
    written += 1

print(f"glyphs written: {written} | skipped (prefix mismatch): {len(skipped)} {skipped[:5]}")
assert len(arm9) == ORIG_LEN

if '--verify' in sys.argv:
    Z = 12
    order = [c for c in ['가','한','로','봇','슈','퍼','전','대','무','적'] if c in samples]
    W = len(order) * (12*Z + 12) + 12
    im = Image.new('RGB', (W, 2*(12*Z) + 60), (20, 20, 26))
    dr = ImageDraw.Draw(im)
    lab = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 15)
    dr.text((6, 4), "YameSoft (before)", fill=(255, 200, 90), font=lab)
    dr.text((6, 12*Z + 34), "Galmuri11 (after)", fill=(120, 255, 150), font=lab)
    for i, ch in enumerate(order):
        old_g, new_g = samples[ch]
        cx = 12 + i * (12*Z + 12)
        for row, (g, yb) in enumerate([(old_g, 26), (new_g, 12*Z + 56)]):
            for y in range(12):
                for x in range(12):
                    c = (235, 220, 120) if g[y][x] else (40, 40, 48)
                    dr.rectangle([cx+x*Z, yb+y*Z, cx+x*Z+Z-1, yb+y*Z+Z-1], fill=c)
    im.save('_verify/font_galmuri_cmp.png')
    print("saved _verify/font_galmuri_cmp.png")

if '--write' in sys.argv:
    open('kr/arm9_patched.bin', 'wb').write(bytes(arm9))
    print("WROTE kr/arm9_patched.bin")
else:
    print("(dry run — pass --write to save)")
