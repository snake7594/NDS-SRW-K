# -*- coding: utf-8 -*-
"""_inject_credits_noext.py — inject the Korean staff credits into ovl_003
WITHOUT extending the overlay (fixes the ending-credits freeze/garble).

Why: the previous _inject_credits.py appended the 63 strings that didn't fit
their slot to a NEW region past the original end and raised ramSize
10240 -> 11292. ovl_003 shares its RAM window (0x021E6700) with ovl0/1/2/4/18
and the game uses memory right after the overlay's ORIGINAL end (bss/heap), so
that appended region is clobbered -> those 63 credits render as garbage glyphs
and the scene freezes.

Fix: the credit strings live in a pool of 17 contiguous runs. Total slot budget
is 2382 B vs 2258 B of Korean -> everything fits inside the ORIGINAL bounds.
Repack all 142 strings (largest-first, first-fit per run) and repoint every
in-overlay pointer. Overlay size stays EXACTLY 10240 -> ramSize unchanged.

--write saves kr/overlays/ovl_003_patched.bin."""
import io, sys, json, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from srwk_codec import HAN2CODE

RAM = 0x021E6700
SRC = 'kr/overlays/ovl_003.bin'
DST = 'kr/overlays/ovl_003_patched.bin'

orig = bytearray(open(SRC, 'rb').read())
ORIG_LEN = len(orig)
ov = bytearray(orig)

def enc(s):
    out = bytearray()
    for ch in s:
        if ch in HAN2CODE:      out += struct.pack('>H', HAN2CODE[ch])
        elif ord(ch) < 0x80:    out.append(ord(ch))
        elif ch == '／':        out += b'\x81\x5e'
        elif ch == '（':        out += b'\x81\x69'
        elif ch == '）':        out += b'\x81\x6a'
        else: raise ValueError('unencodable %r in %r' % (ch, s))
    return bytes(out)

def budget(off, buf):
    e = off
    while e < len(buf) and buf[e] != 0: e += 1
    z = e
    while z < len(buf) and buf[z] == 0: z += 1
    return z - off

def ptrs_to(off, buf):
    tgt = RAM + off
    return [k for k in range(0, len(buf) - 3)
            if struct.unpack_from('<I', buf, k)[0] == tgt]

tr = json.load(io.open('_credits_tr.json', encoding='utf-8'))
slots = []
for e in tr:
    off = e['off']
    slots.append(dict(off=off, bud=budget(off, orig), data=enc(e['ko']), ko=e['ko']))
slots.sort(key=lambda s: s['off'])

# pointers must be resolved against the ORIGINAL image (before we move anything)
noptr = []
for s in slots:
    s['ptrs'] = ptrs_to(s['off'], orig)
    if not s['ptrs']: noptr.append(s['ko'])
print(f"entries {len(slots)} | ptr counts: " +
      ", ".join(f"{n}x{sum(1 for s in slots if len(s['ptrs'])==n)}"
                for n in sorted({len(s['ptrs']) for s in slots})))
assert not noptr, f"entries with no pointer: {noptr[:5]}"

# --- pool = contiguous runs of slot regions ---
runs = []
cs = ce = None
for s in slots:
    if cs is None: cs, ce = s['off'], s['off'] + s['bud']
    elif s['off'] == ce: ce = s['off'] + s['bud']
    else: runs.append([cs, ce]); cs, ce = s['off'], s['off'] + s['bud']
runs.append([cs, ce])
cap = sum(b - a for a, b in runs)
need = sum(len(s['data']) + 1 for s in slots)
print(f"pool: {len(runs)} runs, capacity {cap} B | korean need {need} B | slack {cap-need:+d} B")
assert need <= cap, "does not fit in the original pool"

# --- zero the pool, then pack (largest first, first-fit) ---
for a, b in runs:
    for k in range(a, b): ov[k] = 0
free = [[a, b] for a, b in runs]
placed = 0
for s in sorted(slots, key=lambda s: len(s['data']), reverse=True):
    n = len(s['data']) + 1
    for f in free:
        if f[1] - f[0] >= n:
            s['new'] = f[0]
            ov[f[0]:f[0]+len(s['data'])] = s['data']
            ov[f[0]+len(s['data'])] = 0
            f[0] += n; placed += 1
            break
    else:
        raise SystemExit(f"could not place {s['ko']!r} ({n}B)")
print(f"packed {placed}/{len(slots)} | leftover {sum(f[1]-f[0] for f in free)} B")

# --- repoint every pointer ---
rep = 0
for s in slots:
    for p in s['ptrs']:
        struct.pack_into('<I', ov, p, RAM + s['new'])
        rep += 1
print(f"repointed {rep} pointers")

# --- guards ---
assert len(ov) == ORIG_LEN, "overlay size changed!"
# every string must decode back to its Korean at its new offset
CODE2 = {v: k for k, v in HAN2CODE.items()}
bad = 0
for s in slots:
    e = s['new']
    while ov[e] != 0: e += 1
    if bytes(ov[s['new']:e]) != s['data']: bad += 1
print(f"round-trip mismatches: {bad}")
assert bad == 0
# bytes outside the pool must be untouched
poolset = set()
for a, b in runs: poolset.update(range(a, b))
ptrset = set()
for s in slots:
    for p in s['ptrs']: ptrset.update(range(p, p+4))
diff = [k for k in range(ORIG_LEN) if ov[k] != orig[k]]
outside = [k for k in diff if k not in poolset and k not in ptrset]
print(f"changed bytes {len(diff)} | outside pool+pointers: {len(outside)}")
assert not outside, f"touched non-pool bytes: {outside[:8]}"

if '--write' in sys.argv:
    open(DST, 'wb').write(bytes(ov))
    print(f"WROTE {DST} ({len(ov)} B == original {ORIG_LEN}, NO extension)")
else:
    print("(dry run — pass --write to save)")
