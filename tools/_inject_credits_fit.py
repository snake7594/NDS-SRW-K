# -*- coding: utf-8 -*-
"""_inject_credits_fit.py — credits injection that CANNOT break the ending.

The v1.0~v1.16 ending-credits freeze/garble. The credit renderer draws each
record's strings ([role][name1][name2]...) with a per-string budget sized for the
JAPANESE original. Korean transliterations of Japanese names run ~2x longer
(「鈴木　克弘」10B -> 「스즈키 카츠히로」16B) and overrun -> garbage tiles + freeze.
It is LENGTH, not location -- which is why v1.16 (repack into the original pool,
strings still long) changed nothing at all.

Rule enforced here: **every string must be <= its JP original's byte length and
stay at its ORIGINAL offset** (pure in-place). Result: byte-layout-compatible with
the stock overlay, size 10240, no repack, no extension, no repointing.

Note reverting a long name to its Japanese original is NOT a fix: the KR font
overwrote SJIS 0x889F..0x94FC with hangul, so kanji in that range render as random
syllables (「鈴木　克弘」 -> 「鈴木　뱃눠」). YameSoft's stock credits are already
garbled this way. Long names therefore fall back to SURNAME ONLY, which is
readable Korean and fits every slot (84 of them; 0 need the JP fallback).

--write saves kr/overlays/ovl_003_patched.bin."""
import io, sys, json, struct, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from srwk_codec import HAN2CODE

# A credit slot is a PERSONAL NAME iff its Japanese original is "姓<全角空白>名"
# (SJIS 0x8140 between two kanji runs). Judging from the Korean text instead would
# misread role labels like 「제작 관리」 as a name and truncate them to 「제작」.
def is_person_jp(off, buf):
    e = off
    while buf[e] != 0: e += 1
    raw = bytes(buf[off:e])
    if b'\x81\x40' not in raw: return False
    try: jp = raw.decode('cp932')
    except UnicodeDecodeError: return False
    return bool(re.fullmatch(r'[一-鿿぀-ヿ]+　[一-鿿぀-ヿ]+', jp))

SRC = 'kr/overlays/ovl_003.bin'      # YameSoft KR overlay (labels already Korean)
DST = 'kr/overlays/ovl_003_patched.bin'

base = bytearray(open(SRC, 'rb').read())
ov = bytearray(base)

def enc(s):
    out = bytearray()
    for ch in s:
        if ch in HAN2CODE:   out += struct.pack('>H', HAN2CODE[ch])
        elif ord(ch) < 0x80: out.append(ord(ch))
        elif ch == '／':     out += b'\x81\x5e'
        elif ch == '（':     out += b'\x81\x69'
        elif ch == '）':     out += b'\x81\x6a'
        elif ch == '　':     out += b'\x81\x40'
        else: raise ValueError('unencodable %r in %r' % (ch, s))
    return bytes(out)

def orig_len(off):
    e = off
    while e < len(base) and base[e] != 0: e += 1
    return e - off

def slot_budget(off):
    e = off
    while e < len(base) and base[e] != 0: e += 1
    z = e
    while z < len(base) and base[z] == 0: z += 1
    return z - off

tr = json.load(io.open('_credits_tr.json', encoding='utf-8'))
kept = reverted = shrunk = surname = 0
report = []
for e in sorted(tr, key=lambda x: x['off']):
    off, ko = e['off'], e['ko']
    jl = orig_len(off)
    b = enc(ko)
    if len(b) <= jl:
        pass                                   # fits as-is
    elif is_person_jp(off, base):
        # Personal name that is too long. Reverting to the Japanese original is NOT
        # an option: the KR font overwrote SJIS 0x889F..0x94FC with hangul, so a
        # kanji name renders half-garbled (「鈴木　克弘」 -> 「鈴木　뱃눠」).
        # Surname alone is readable Korean and fits every slot.
        sn = re.split(r'[ 　]', ko.strip())[0]
        sb = enc(sn)
        if len(sb) <= jl:
            b, ko, surname = sb, sn, surname + 1
            report.append(('SURNAME', off, jl, ko))
        else:
            b = None; reverted += 1
            report.append(('REVERT', off, jl, ko))
    else:
        # company / label: dropping spaces matches the JP original's own style
        alt = ko.replace(' ', '').replace('　', '')
        ab = enc(alt)
        if len(ab) <= jl and alt != ko:
            b, ko, shrunk = ab, alt, shrunk + 1
            report.append(('SHRUNK', off, jl, ko))
        else:
            b = None
            reverted += 1
            report.append(('REVERT', off, jl, ko))
    if b is None:
        continue                               # leave the original bytes untouched
    # in-place write + null, pad the rest of the slot with zeros
    bud = slot_budget(off)
    assert len(b) + 1 <= bud, (hex(off), len(b), bud)
    ov[off:off+len(b)] = b
    for k in range(off+len(b), off+bud): ov[k] = 0
    kept += 1

print(f"credits: {len(tr)} | Korean kept {kept} (surname-only {surname}, space-trimmed {shrunk}) | reverted to JP {reverted}")
print("\nreverted (staff names -> Japanese original):", sum(1 for r in report if r[0]=='REVERT'))
for tag, off, jl, ko in [r for r in report if r[0]=='SHRUNK']:
    print(f"  SHRUNK 0x{off:04x} (JP {jl}B) -> 「{ko}」")

# ---- guards ----
assert len(ov) == len(base), "overlay size changed!"
# every written string must be <= its JP original length and NUL-terminated in slot
bad = 0
for e in tr:
    off = e['off']; jl = orig_len(off)
    n = 0
    while ov[off+n] != 0: n += 1
    if n > jl: bad += 1
print(f"\nstrings longer than their JP original: {bad}  (must be 0)")
assert bad == 0
# no pointer was touched: overlay differs from base only inside string slots
diff = [k for k in range(len(base)) if ov[k] != base[k]]
slots = set()
for e in tr:
    o = e['off']; slots.update(range(o, o+slot_budget(o)))
outside = [k for k in diff if k not in slots]
print(f"changed bytes {len(diff)} | outside credit slots: {len(outside)} (must be 0)")
assert not outside

if '--write' in sys.argv:
    open(DST, 'wb').write(bytes(ov))
    print(f"\nWROTE {DST} ({len(ov)} B, in-place only, no repack/extension/repointing)")
else:
    print("\n(dry run — pass --write to save)")
