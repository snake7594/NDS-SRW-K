# -*- coding: utf-8 -*-
"""Improved 1024-ring LZSS encoder: lazy matching + larger match-chain. Lossless;
aims to fit the user's logo into the original block-2360 slot (<=15692 bytes)."""
import struct
from _codec1024 import decomp_1024
WIN, MINM, MAXM, INITWP = 1024, 3, 66, 958

def _best_match(data, p, n, idx, cap):
    if p + MINM > n: return 0, -1
    key = bytes(data[p:p+3]); lo = p - WIN
    best_len, best_q, tried = 0, -1, 0
    maxl = min(MAXM, n - p)
    for q in idx.get(key, ()):
        if q < lo: break
        tried += 1
        if tried > cap: break
        if data[q + best_len] != data[p + best_len] if best_len < maxl else False:
            # quick reject: can't beat current best at the boundary byte
            continue
        l = 0
        while l < maxl and data[q + l] == data[p + l]:
            l += 1
        if l > best_len:
            best_len, best_q = l, q
            if l == maxl: break
    return best_len, best_q

def compress_pixels2(data, cap=1024, lazy=True):
    n = len(data); ops = []; idx = {}
    def reg(j):
        if j + 3 <= n:
            k = bytes(data[j:j+3]); lst = idx.get(k)
            if lst is None: idx[k] = [j]
            else: lst.insert(0, j)
    p = 0
    while p < n:
        bl, bq = _best_match(data, p, n, idx, cap)
        if bl >= MINM and lazy and bl < MAXM and p + 1 < n:
            reg(p)                                   # register p before peeking
            nl, nq = _best_match(data, p+1, n, idx, cap)
            if nl > bl:                              # defer: emit literal now
                ops.append(('L', data[p])); p += 1; continue
            # take match at p (p already registered)
            ops.append(('M', (INITWP + bq) & 0x3ff, bl))
            for j in range(p+1, p+bl): reg(j)
            p += bl; continue
        if bl >= MINM:
            ops.append(('M', (INITWP + bq) & 0x3ff, bl))
            for j in range(p, p+bl): reg(j)
            p += bl
        else:
            ops.append(('L', data[p])); reg(p); p += 1
    stream = bytearray()
    for i in range(0, len(ops), 8):
        grp = ops[i:i+8]; flag = 0
        for b, op in enumerate(grp):
            if op[0] == 'L': flag |= (1 << b)
        stream.append(flag)
        for op in grp:
            if op[0] == 'L': stream.append(op[1])
            else:
                _, disp, length = op
                stream.append(disp & 0xff)
                stream.append(((length-3) & 0x3f) | (((disp >> 8) & 3) << 6))
    return bytes(stream)

def build_ecd2(orig_ecd, new_pixels, cap=1024):
    f1 = int.from_bytes(orig_ecd[4:8], 'big')
    preamble = orig_ecd[0x10:0x10+f1]
    comp = compress_pixels2(new_pixels, cap=cap)
    f2 = f1 + len(comp); f3 = f1 + len(new_pixels)
    return orig_ecd[:4] + struct.pack('>III', f1, f2, f3) + preamble + comp

if __name__ == '__main__':
    from srwk_rom import Rom
    pix = open('_fg_new.bin', 'rb').read()[0:0x7000]
    r = Rom('../Super Robot Wars K (Korean)-기존패치.nds')
    d = r.get('data/add02dat.bin'); n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
    offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]
    orig = d[offs[2360]:offs[2361]]
    import _enc1024 as old
    s_old = len(old.compress_pixels(pix))
    for cap in (64, 256, 1024):
        comp = compress_pixels2(pix, cap=cap)
        blk = build_ecd2(orig, pix, cap=cap)
        ok = decomp_1024(blk)[0][8:8+0x7000] == pix
        print('cap %4d : stream %d  block %d  (slot 15692, fits=%s, roundtrip=%s)'
              % (cap, len(comp), len(blk), len(blk) <= 15692, ok))
    print('old greedy stream:', s_old, ' block', s_old + 0x18)
