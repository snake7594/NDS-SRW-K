# -*- coding: utf-8 -*-
"""Replace all 59 JP chapter eyecatch images in kr/data/add02dat.bin
with Korean-rendered versions.

Strategy:
  - Render "제N화" + Korean subtitle as 4bpp AA tiles (Malgun Gothic TTF)
  - Map alpha → nibble: 0=transparent, 255(black)=1, grey ramp to 15
  - Pack into new IMG+SCR blocks re-encoded with build_ecd2
  - PAD to EXACT original block sizes (archive offsets are cached in game)
  - Write back in-place; archive overall size unchanged
"""
import sys, io, os, struct
sys.stdout = io.TextIOWrapper(open('_eyecatch_inject_log.txt', 'wb'), encoding='utf-8')

from _codec1024 import decomp_1024
from _enc1024b import build_ecd2
from PIL import Image, ImageFont, ImageDraw

FONT_PATH = r"C:\Windows\Fonts\malgun.ttf"
FONT_CH_SIZE  = 20   # chapter label  e.g. 제1화
FONT_SUB_SIZE = 16   # subtitle
Y_CH  = 60           # top-left y for chapter label text
Y_SUB = 92           # top-left y for subtitle text

# ── 59 chapter entries: (chapter_display, subtitle_ko) ──────────────────────
CHAPTERS = [
    ("제1화",  "웨딩벨은 싸움을 알리는 종"),       # ch01
    ("제2화",  "이세계로 부터의 방문자"),            # ch02
    ("제3화",  "빌드업！깨어나는 전설"),             # ch03
    ("제4화",  "재회의 콤비네이션 어택！"),           # ch04
    ("제5화",  "오버맨 배틀"),                      # ch05
    ("제6화",  "턱시도를 입은 얼간이 녀석"),          # ch06
    ("제7화",  "드렁크 히어로・스위프트 걸"),         # ch07
    ("제8화",  "숙명의 터미널"),                     # ch08
    ("제9화",  "에리어Zi의 결투"),                   # ch09
    ("제10화", "검은불꽃의 장군"),                   # ch10
    ("제11화", "가이킹 절체절명！！・전편"),           # ch11
    ("제11화", "가이킹 절체절명！！・후편"),           # ch12
    ("제12화", "꿈틀거리는 어둠・전편"),              # ch13
    ("제12화", "꿈틀거리는 어둠・후편"),              # ch14
    ("제13화", "변해 버린 지구"),                    # ch15
    ("제14화", "이별의 빛・전편"),                    # ch16
    ("제14화", "이별의 빛・후편"),                    # ch17
    ("제14화", "고독〜투쟁"),                        # ch18
    ("제15화", "엔젤 다운"),                         # ch19
    ("제15화", "슬픔의 비상・전편"),                  # ch20
    ("제15화", "슬픔의 비상・후편"),                  # ch21
    ("제16화", "격투！단나 베이스！！・전편"),          # ch22
    ("제16화", "격투！단나 베이스！！・후편"),          # ch23
    ("제17화", "탈환하라！또 한명의 강철지그！"),       # ch24
    ("제17화", "깨어나는 대지마룡"),                  # ch25
    ("제18화", "존재〜동료"),                        # ch26
    ("제18화", "캡틴・가리스、충격의 비밀"),            # ch27
    ("제19화", "별의문、운명의문・전편"),               # ch28
    ("제19화", "별의문、운명의문・후편"),               # ch29
    ("제20화", "배반과 만남과"),                     # ch30
    ("제21화", "결전의 시간 오다・전편"),              # ch31
    ("제21화", "결전의 시간 오다・후편"),              # ch32
    ("제22화", "컨퓨젼・카니발"),                    # ch33
    ("제23화", "결성！디갈드 토벌군"),                # ch34
    ("제24화", "오버데빌 크라이시스・전편"),            # ch35
    ("제24화", "오버데빌 크라이시스・후편"),            # ch36
    ("제25화", "기습"),                             # ch37
    ("제26화", "절망 안에서 찾은 빛"),                # ch38
    ("제26화", "진의 야망"),                         # ch39
    ("제27화", "행복의 카운트다운"),                  # ch40
    ("제27화", "결말"),                             # ch41
    ("제28화", "링케이지"),                          # ch42
    ("제29화", "슬픔의 주박을 풀어라"),               # ch43
    ("제30화", "사랑〜안녕히・전편"),                 # ch44
    ("제30화", "사랑〜안녕히・후편"),                 # ch45
    ("제30화", "결전！삼대마룡！！"),                 # ch46
    ("제30화", "래빗 신드롬의 공포"),                # ch47
    ("제31화", "창궁〜하늘"),                        # ch48
    ("제31화", "아버지의 마음・전편"),                # ch49
    ("제31화", "아버지의 마음・후편"),                # ch50
    ("제31화", "강철의 거인들・전편"),                # ch51
    ("제31화", "강철의 거인들・후편"),                # ch52
    ("제32화", "리셋 되는 세계・전편"),               # ch53
    ("제32화", "리셋 되는 세계・후편"),               # ch54
    ("제33화", "히미카、야망의 끝에서・전편"),          # ch55
    ("제33화", "히미카、야망의 끝에서・후편"),          # ch56
    ("제34화", "천국의 번개"),                       # ch57
    ("제35화", "Another Sphere"),                   # ch58
    ("최종화", "진심으로…"),                         # ch59
]
assert len(CHAPTERS) == 59

# ── Helpers ──────────────────────────────────────────────────────────────────

def rgba_to_nibble(r, g, b, a):
    """Map RGBA pixel (white text on transparent) to 4bpp nibble index.
    alpha=0 → nibble 0 (transparent)
    alpha low → nibble 1-2 (dark edges — natural dark AA fringe acts as outline)
    alpha high → nibble 15 (white fill)
    This matches the JP eyecatch style: white core + dark AA outline, no explicit stroke."""
    if a == 0:
        return 0
    return max(1, min(15, round(a * 15 / 255)))


def _norm(s):
    # Malgun Gothic lacks U+30FB (katakana middle dot) and U+301C (wave dash);
    # substitute with closest Latin equivalents that render cleanly.
    return s.replace('・', '·').replace('〜', '~')


def render_canvas(ch_label, subtitle, fch, fsub):
    """Return RGBA 256×192 PIL Image with Korean text (white on transparent)."""
    ch_label = _norm(ch_label)
    subtitle  = _norm(subtitle)
    img = Image.new('RGBA', (256, 192), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # White text on transparent — AA edges naturally fade to dark (acts as outline)
    # Chapter label
    bb = draw.textbbox((0, 0), ch_label, font=fch)
    w = bb[2] - bb[0]
    draw.text(((256 - w) // 2, Y_CH), ch_label, font=fch, fill=(255, 255, 255, 255))

    # Subtitle (auto-shrink if wider than screen)
    sub_font = fsub
    bb = draw.textbbox((0, 0), subtitle, font=sub_font)
    sub_w = bb[2] - bb[0]
    if sub_w > 248:
        sub_font = ImageFont.truetype(FONT_PATH, FONT_SUB_SIZE - 2)
        bb = draw.textbbox((0, 0), subtitle, font=sub_font)
        sub_w = bb[2] - bb[0]
    draw.text(((256 - sub_w) // 2, Y_SUB), subtitle, font=sub_font, fill=(255, 255, 255, 255))

    return img


def canvas_to_4bpp(canvas):
    """Convert RGBA 256×192 canvas to (tile_data_bytes, scr_list_768).
    tile_data_bytes: tile 0 (zeros) + tiles 1..N each 32 bytes 4bpp.
    scr_list: 768 u16 entries (tile_idx | pal_slot<<12), pal_slot=0xF."""
    tiles = [bytes(32)]   # tile 0 = transparent/empty
    tile_map = {}
    scr = []
    px = canvas.load()

    for ty in range(24):
        for tx in range(32):
            row = []
            nonempty = False
            for y in range(8):
                for xi in range(0, 8, 2):
                    n0 = rgba_to_nibble(*px[tx * 8 + xi,     ty * 8 + y])
                    n1 = rgba_to_nibble(*px[tx * 8 + xi + 1, ty * 8 + y])
                    row.append(n0 | (n1 << 4))
                    if n0 or n1:
                        nonempty = True
            if not nonempty:
                scr.append(0)
            else:
                tb = bytes(row)
                if tb not in tile_map:
                    tile_map[tb] = len(tiles)
                    tiles.append(tb)
                scr.append(tile_map[tb] | 0xF000)

    tile_data = b''.join(tiles)
    return tile_data, scr


def patch_ch(kr_mut, offs, ch_idx, ch_label, subtitle, fch, fsub):
    bi_img = 2214 + 2 * ch_idx
    bi_scr = 2215 + 2 * ch_idx

    orig_img = bytes(kr_mut[offs[bi_img]:offs[bi_img + 1]])
    orig_scr = bytes(kr_mut[offs[bi_scr]:offs[bi_scr + 1]])

    orig_img_dec = decomp_1024(orig_img)[0]
    orig_scr_dec = decomp_1024(orig_scr)[0]

    # Render Korean text
    canvas = render_canvas(ch_label, subtitle, fch, fsub)
    tile_data, scr_entries = canvas_to_4bpp(canvas)

    num_tiles = len(tile_data) // 32  # includes tile 0

    # Re-encode IMG: override preamble with updated header (num_tiles, h=1);
    # pass only tile_data as payload (preamble already contains 'IMG\x00' header)
    new_img_preamble = b'IMG\x00' + struct.pack('<HH', num_tiles, 1)
    new_img_ecd = build_ecd2(orig_img, tile_data, new_preamble=new_img_preamble)

    # Re-encode SCR: pass only entry bytes; preamble ('SCR\x00'+dims) auto-preserved
    scr_entry_bytes = struct.pack('<%dH' % len(scr_entries), *scr_entries)
    new_scr_ecd = build_ecd2(orig_scr, scr_entry_bytes)

    # Verify fits in original slots
    if len(new_img_ecd) > len(orig_img):
        raise RuntimeError(
            f"ch{ch_idx+1} IMG overflow: {len(new_img_ecd)} > {len(orig_img)} tiles={num_tiles}")
    if len(new_scr_ecd) > len(orig_scr):
        raise RuntimeError(
            f"ch{ch_idx+1} SCR overflow: {len(new_scr_ecd)} > {len(orig_scr)}")

    # Pad to exact original sizes (preserve archive offsets)
    new_img = new_img_ecd + b'\x00' * (len(orig_img) - len(new_img_ecd))
    new_scr = new_scr_ecd + b'\x00' * (len(orig_scr) - len(new_scr_ecd))

    kr_mut[offs[bi_img]:offs[bi_img + 1]] = new_img
    kr_mut[offs[bi_scr]:offs[bi_scr + 1]] = new_scr

    orig_tiles = struct.unpack_from('<H', orig_img_dec, 4)[0] * struct.unpack_from('<H', orig_img_dec, 6)[0]
    print(f"ch{ch_idx+1:02d} {ch_label!r:8s}  orig_tiles={orig_tiles:4d}  "
          f"new_tiles={num_tiles:3d}  "
          f"img {len(new_img_ecd):5d}/{len(orig_img):5d}  "
          f"scr {len(new_scr_ecd):5d}/{len(orig_scr):5d}")


# ── Main ──────────────────────────────────────────────────────────────────────

# Use the title-logo-patched version as input so we build on top of all prior patches.
# Output overwrites it (eyecatch blocks 2214-2330 injected, block 2360 title logo preserved).
KR_ADD02 = 'kr/add02_patched.bin'

kr_raw = open(KR_ADD02, 'rb').read()
n0 = struct.unpack_from('<I', kr_raw, 0)[0]
ne = n0 // 4
offs = list(struct.unpack_from('<%dI' % ne, kr_raw, 0)) + [len(kr_raw)]

kr_mut = bytearray(kr_raw)   # mutable working copy

fch  = ImageFont.truetype(FONT_PATH, FONT_CH_SIZE)
fsub = ImageFont.truetype(FONT_PATH, FONT_SUB_SIZE)

print(f"add02dat: {ne} blocks, {len(kr_raw)} bytes")

errors = []
for ch_idx, (ch_label, subtitle) in enumerate(CHAPTERS):
    try:
        patch_ch(kr_mut, offs, ch_idx, ch_label, subtitle, fch, fsub)
    except Exception as e:
        print(f"  ERROR ch{ch_idx+1}: {e}")
        errors.append(ch_idx + 1)

if errors:
    print(f"\nFAILED chapters: {errors}")
    sys.exit(1)

# Save result (overwrites add02_patched.bin; title-logo block 2360 is untouched)
out_path = KR_ADD02
open(out_path, 'wb').write(bytes(kr_mut))
print(f"\nSaved {out_path} ({len(kr_mut)} bytes)")

# Quick verification: re-parse and spot-check ch01
kr_verify = open(out_path, 'rb').read()
assert len(kr_verify) == len(kr_raw), "Archive size changed!"
v_img = kr_verify[offs[2214]:offs[2215]]
v_dec = decomp_1024(v_img)[0]
assert v_dec[:4] == b'IMG\x00', "ch01 IMG magic wrong"
v_w, v_h = struct.unpack_from('<HH', v_dec, 4)
assert v_dec[8:16] != b'IMG\x00IMG\x00'[:8], "double-header bug still present"
max_nib = max((max(b & 0xF, (b >> 4)) for b in v_dec[8:]), default=0)
print(f"Verify ch01: w={v_w} h={v_h} tiles={v_w*v_h} max_nib={max_nib}")
print("Done.")
sys.stdout.flush()
