# -*- coding: utf-8 -*-
"""Encoder for the 4th codec (1024-ring LZSS).  Pairs with decomp_1024.
Sliding-window view: pixel index p writes ring pos (958+p)&0x3ff. A backref to
pixel q (q in [p-1024, p)) -> disp=(958+q)&0x3ff, dist=p-q in 1..1024, len 3..66
(self-overlap RLE allowed). flag LSB-first: bit1=literal, bit0=backref."""
import struct
from srwk_rom import Rom
from _codec1024 import decomp_1024

WIN, MINM, MAXM, INITWP = 1024, 3, 66, 958

def compress_pixels(data):
    n = len(data)
    out_ops = []          # ('L', byte) or ('M', disp, length)
    idx = {}              # 3-byte key -> list of positions (recent first)
    p = 0
    while p < n:
        best_len, best_q = 0, -1
        if p + MINM <= n:
            key = data[p:p+3]
            lo = p - WIN
            for q in idx.get(bytes(key), ()):
                if q < lo:
                    break
                # extend match (allow self-overlap up to MAXM)
                l = 0
                maxl = min(MAXM, n - p)
                while l < maxl and data[q + l] == data[p + l]:
                    l += 1
                if l > best_len:
                    best_len, best_q = l, q
                    if l == maxl:
                        break
        if best_len >= MINM:
            disp = (INITWP + best_q) & 0x3ff
            out_ops.append(('M', disp, best_len))
            adv = best_len
        else:
            out_ops.append(('L', data[p]))
            adv = 1
        # register positions p..p+adv-1 in the index (3-byte keys)
        for j in range(p, p + adv):
            if j + 3 <= n:
                k = bytes(data[j:j+3])
                lst = idx.setdefault(k, [])
                lst.insert(0, j)
                if len(lst) > 64:        # cap chain length for speed
                    del lst[64:]
        p += adv
    # serialize: flag byte (LSB-first) per 8 ops, then op data
    stream = bytearray()
    for i in range(0, len(out_ops), 8):
        grp = out_ops[i:i+8]
        flag = 0
        for b, op in enumerate(grp):
            if op[0] == 'L':
                flag |= (1 << b)
        stream.append(flag)
        for op in grp:
            if op[0] == 'L':
                stream.append(op[1])
            else:
                _, disp, length = op
                b1 = disp & 0xff
                b2 = ((length - 3) & 0x3f) | (((disp >> 8) & 3) << 6)
                stream.append(b1); stream.append(b2)
    return bytes(stream)

def build_ecd(orig_ecd, new_pixels):
    """Rebuild an ECD/IMG\\x01 block with new pixel data (same w/h/preamble)."""
    f1 = int.from_bytes(orig_ecd[4:8], 'big')          # 8
    preamble = orig_ecd[0x10:0x10+f1]                  # IMG header bytes
    comp = compress_pixels(new_pixels)
    f2 = f1 + len(comp)
    f3 = f1 + len(new_pixels)
    hdr = orig_ecd[:4] + struct.pack('>III', f1, f2, f3)
    return hdr + preamble + comp

if __name__ == '__main__':
    r = Rom('../Super Robot Wars K (Japan).nds')
    d = r.get('data/add02dat.bin')
    n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
    offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]
    for bi in (2348, 2349, 2345, 1872):
        ecd = d[offs[bi]:offs[bi+1]]
        dec, f3, (w, h) = decomp_1024(ecd)
        pix = dec[8:]
        rebuilt = build_ecd(ecd, pix)
        dec2, _, _ = decomp_1024(rebuilt)
        ok = dec2[8:] == pix
        print(f"block {bi}: pixels={len(pix)} orig_stream={len(ecd)-0x18} "
              f"new_stream={len(rebuilt)-0x18} roundtrip={'OK' if ok else 'FAIL'}")
