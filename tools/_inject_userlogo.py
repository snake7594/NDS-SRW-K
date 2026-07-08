# -*- coding: utf-8 -*-
"""_inject_userlogo.py — inject the user-drawn Korean title logo
(../title_logo_canvas z.png, RGBA, pixel-aligned to OAM screen coords) into
add02 blocks 2359 (PLT values) + 2360 (tiles, ECD exact-size pad).

Fit strategy (slot is tight):
  * base = JP ROM block-2360 tiles; alpha-aware change mask (user canvas vs JP
    reference ../title_logo_canvas.png, +1px dilation). UNCHANGED pixels keep
    JP bytes verbatim.
  * OWNER rewrite: for a changed pixel only the topmost covering sprite stores
    the color; sprites underneath store 0 -> long transparent runs (invisible,
    LZSS-friendly).
  * palettes: pn0/1/2 shared with non-logo sprites -> untouched. For exclusive
    pns, entries with unchanged-usage < FREE_T are freed (their few unchanged
    pixels re-indexed to the nearest kept color) and reassigned (median-cut)
    to the colors the user's art demands.
  * FREE_T / color-count escalate until the re-encoded block fits the slot.
Edits the CURRENT kr/add02_patched.bin (v1.3~v1.9 preserved). --verify renders
_verify/title_user_final.png; --write saves."""
import io, sys, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import numpy as np
from PIL import Image
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _enc1024b import build_ecd2

USER_PNG = '../title_logo_canvas z.png'
REF_PNG  = '../title_logo_canvas.png'
SHARED_PN = {0, 1, 2}
H = W = 256

# ---- OAM logo layout (list order == OAM order == priority, spr0 topmost) ----
ss = open('_sstate.bin', 'rb').read()
i = ss.find(b'OAMS'); oam = ss[i+12:i+12+1024]
DIM = {(0,0):(1,1),(0,1):(2,2),(0,2):(4,4),(0,3):(8,8),(1,0):(2,1),(1,1):(4,1),
       (1,2):(4,2),(1,3):(8,4),(2,0):(1,2),(2,1):(1,4),(2,2):(2,4),(2,3):(4,8)}
logo = []
for s in range(128):
    a0, a1, a2 = struct.unpack_from('<HHH', oam, s*8)
    if ((a0 >> 8) & 1) == 0 and ((a0 >> 9) & 1):
        continue
    y = a0 & 0xFF; x = a1 & 0x1FF
    if x >= 256: x -= 512
    if y >= 140: continue
    w, h = DIM.get(((a0 >> 14) & 3, (a1 >> 14) & 3), (1, 1))
    logo.append(dict(x=x, y=y, w=w, h=h, tile=a2 & 0x3FF, pn=(a2 >> 12) & 0xF))

def covered(sp):
    for ty in range(sp['h']):
        for tx in range(sp['w']):
            ti = sp['tile'] + ty*32 + tx
            for py in range(8):
                sy = sp['y']+ty*8+py
                if not (0 <= sy < H): continue
                for px in range(8):
                    sx = sp['x']+tx*8+px
                    if 0 <= sx < W:
                        yield ti, py, px, sy, sx

# ---- base tiles/palettes from JP ROM; current archive for slots ----
jp = Rom('../Super Robot Wars K (Japan).nds')
djp = jp.get('data/add02dat.bin')
nej = struct.unpack_from('<I', djp, 0)[0] // 4
oj = list(struct.unpack_from('<%dI' % nej, djp, 0)) + [len(djp)]
jblk = bytes(djp[oj[2360]:oj[2361]])
f3 = struct.unpack_from('>I', jblk, 12)[0]
FG0 = bytes(decomp_1024(jblk)[0][8:8+(f3-8)]) + bytes(0x8000 - (f3-8))
PLT0 = bytes(djp[oj[2359]:oj[2360]])

arc = bytearray(open('kr/add02_patched.bin', 'rb').read())
ne = struct.unpack_from('<I', arc, 0)[0] // 4
offs = list(struct.unpack_from('<%dI' % ne, arc, 0)) + [len(arc)]
slot = offs[2361] - offs[2360]
assert len(PLT0) == offs[2360]-offs[2359]

def pal_of(pn, buf):
    base = 8 + pn*32
    return [(((c := buf[base+k*2] | (buf[base+k*2+1] << 8)) & 31) << 3,
             ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3) for k in range(16)]

# ---- change mask + owner map ----
def load(p):
    a = np.zeros((H, W, 4), np.uint8)
    v = np.array(Image.open(p).convert('RGBA')); a[:v.shape[0], :v.shape[1]] = v
    return a
usr = load(USER_PNG); ref = load(REF_PNG)
ua = usr[:, :, 3] >= 128; ra = ref[:, :, 3] >= 128
rgbd = np.abs(usr[:, :, :3].astype(int) - ref[:, :, :3].astype(int)).sum(axis=2)
M = (ua != ra) | (ua & ra & (rgbd > 24))
dm = M.copy()
dm[1:, :] |= M[:-1, :]; dm[:-1, :] |= M[1:, :]
dm[:, 1:] |= M[:, :-1]; dm[:, :-1] |= M[:, 1:]
M = dm
owner = np.full((H, W), -1, np.int32)
for li, sp in enumerate(logo):
    for ti, py, px, sy, sx in covered(sp):
        if owner[sy, sx] < 0:
            owner[sy, sx] = li
print("changed px:", int(M.sum()))

def get0(ti, py, px):
    o = ti*32 + py*4 + px//2; b = FG0[o]
    return (b >> 4) if (px & 1) else (b & 0xF)

# usage of each palette entry by UNCHANGED pixels (per pn, across its sprites)
usage = {}
for sp in logo:
    u = usage.setdefault(sp['pn'], np.zeros(16, np.int64))
    for ti, py, px, sy, sx in covered(sp):
        if not M[sy, sx]:
            u[get0(ti, py, px)] += 1
# owner-demand: user colors at changed px owned by each pn
demand = {}
for li, sp in enumerate(logo):
    dl = demand.setdefault(sp['pn'], [])
    for ti, py, px, sy, sx in covered(sp):
        if M[sy, sx] and owner[sy, sx] == li and usr[sy, sx, 3] >= 128:
            dl.append(tuple(int(c) for c in usr[sy, sx, :3]))

def attempt(FREE_T, MAXC):
    plt = bytearray(PLT0)
    FG = bytearray(FG0)
    remap = {}          # pn -> {freedIdx: keptIdx}
    for pn, dl in demand.items():
        if pn in SHARED_PN or not dl:
            continue
        u = usage[pn]
        kept = [k for k in range(1, 16) if u[k] >= FREE_T]
        if not kept:                           # near-fully-freed palette (e.g. pn12):
            kept = [k for k in range(1, 16) if u[k] > 0]   # preserve only truly-used entries
        freed = [k for k in range(1, 16) if k not in kept]
        if not freed:
            continue
        cols0 = pal_of(pn, PLT0)
        remap[pn] = {}
        for fk in freed:                       # unchanged px on freed entries -> nearest kept
            if u[fk] == 0 or not kept:
                continue
            fr, fg, fb = cols0[fk]
            remap[pn][fk] = min(kept, key=lambda kk: (cols0[kk][0]-fr)**2 +
                                (cols0[kk][1]-fg)**2 + (cols0[kk][2]-fb)**2)
        ncol = min(len(freed), MAXC)
        src = Image.fromarray(np.array(dl, np.uint8).reshape(-1, 1, 3), 'RGB')
        q = src.quantize(colors=ncol, method=Image.MEDIANCUT)
        pcols = q.getpalette()[:ncol*3]
        for j in range(ncol):
            r, g, b = pcols[j*3:j*3+3]
            struct.pack_into('<H', plt, 8 + pn*32 + freed[j]*2,
                             (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10))
    pals = {pn: pal_of(pn, plt) for pn in usage}
    freed_sets = {pn: set(rm.keys()) for pn, rm in remap.items()}

    def nearest(cols, rgb):
        best, bi = 1 << 30, 1
        for k in range(1, 16):
            pr, pg, pb = cols[k]
            dd = (pr-rgb[0])**2 + (pg-rgb[1])**2 + (pb-rgb[2])**2
            if dd < best: best, bi = dd, k
        return bi

    def setp(ti, py, px, val):
        o = ti*32 + py*4 + px//2; b = FG[o]
        FG[o] = (b & 0x0F) | (val << 4) if (px & 1) else (b & 0xF0) | (val & 0xF)

    for li, sp in enumerate(logo):
        pn = sp['pn']; cols = pals[pn]
        fs = freed_sets.get(pn, set()); rm = remap.get(pn, {})
        for ti, py, px, sy, sx in covered(sp):
            if M[sy, sx]:
                if owner[sy, sx] == li and usr[sy, sx, 3] >= 128:
                    setp(ti, py, px, nearest(cols, tuple(int(c) for c in usr[sy, sx, :3])))
                else:
                    setp(ti, py, px, 0)
            else:
                v = get0(ti, py, px)
                if v in fs:
                    setp(ti, py, px, rm[v])
    pixb = bytes(FG[:f3-8])
    raw = build_ecd2(jblk, pixb, cap=1024)
    return raw, pixb, plt, FG

raw = None
for FREE_T, MAXC in [(60, 12), (100, 12), (150, 10), (250, 8)]:
    raw, pixb, plt, FG = attempt(FREE_T, MAXC)
    print("attempt FREE_T=%d MAXC=%d -> %d B (slot %d) %s"
          % (FREE_T, MAXC, len(raw), slot, "FITS" if len(raw) <= slot else "overflow"))
    if len(raw) <= slot:
        break
assert len(raw) <= slot, "could not fit even at max settings"

new2360 = raw + b'\x00' * (slot - len(raw))
assert decomp_1024(new2360)[0][8:8+(f3-8)] == pixb, "round-trip failed"
old = bytes(arc)
arc[offs[2359]:offs[2360]] = plt
arc[offs[2360]:offs[2361]] = new2360
assert len(arc) == len(old)
diffb = [k for k in range(len(old)) if old[k] != arc[k]]
lo, hi = (min(diffb), max(diffb)) if diffb else (0, 0)
ok = offs[2359] <= lo and hi < offs[2361]
print("changed bytes %d in [0x%x,0x%x], confined to 2359..2360: %s" % (len(diffb), lo, hi, ok))
assert ok

if '--verify' in sys.argv:
    pals = {pn: pal_of(pn, plt) for pn in usage}
    def getn(ti, py, px):
        o = ti*32 + py*4 + px//2; b = FG[o]
        return (b >> 4) if (px & 1) else (b & 0xF)
    prev = np.zeros((H, W, 3), np.uint8); prev[:] = (8, 8, 20)
    shown = np.zeros((H, W), bool)
    for li, sp in enumerate(logo):          # topmost-first: first non-zero wins
        cols = pals[sp['pn']]
        for ti, py, px, sy, sx in covered(sp):
            if shown[sy, sx]: continue
            v = getn(ti, py, px)
            if v: prev[sy, sx] = cols[v]; shown[sy, sx] = True
    Image.fromarray(prev[:224]).resize((512, 448), Image.NEAREST).save('_verify/title_user_final.png')
    err = np.abs(prev[:224].astype(int) - usr[:224, :, :3].astype(int)).sum(axis=2)
    mk = usr[:224, :, 3] >= 128
    print("mean |RGB err| on user ink: %.2f" % float(err[mk].mean()))
    print("saved _verify/title_user_final.png")

if '--write' in sys.argv:
    open('kr/add02_patched.bin', 'wb').write(bytes(arc))
    print("WROTE kr/add02_patched.bin")
else:
    print("(dry run — pass --write to save)")
