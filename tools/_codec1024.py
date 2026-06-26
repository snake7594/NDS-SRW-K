# -*- coding: utf-8 -*-
"""4th codec = 1024-byte ring-buffer LZSS (disassembled from arm9 0x0200e8b0).
Header: f1=BE32[4:8] preamble size, f2=BE32[8:12] compressed payload size.
Preamble: copy f1 bytes from ecd[0x10:] verbatim (not into window).
Main: flag byte LSB-first; bit=1 literal, bit=0 backref(2 bytes):
  len=(b2&0x3f)+3, disp=b1|((b2&0xc0)<<2) absolute pos in 1024 ring."""
import struct, sys
import numpy as np
from PIL import Image
from srwk_rom import Rom

def decomp_1024(ecd, sb_init=958):
    f1 = int.from_bytes(ecd[4:8], 'big')
    f2 = int.from_bytes(ecd[8:12], 'big')
    f3 = int.from_bytes(ecd[12:16], 'big')
    inp = ecd[0x10:]
    ip = 0
    out = bytearray()
    win = bytearray(1024)
    wp = sb_init & 0x3ff
    # preamble (f1 bytes), output only
    for _ in range(f1):
        out.append(inp[ip]); ip += 1
    remaining = f2 - f1
    def rd():
        nonlocal ip, remaining
        if remaining <= 0:
            return -1
        b = inp[ip]; ip += 1; remaining -= 1
        return b
    flag = 0
    while len(out) < f3:
        flag >>= 1
        if (flag & 0x100) == 0:
            b = rd()
            if b < 0:
                break
            flag = 0xff00 | b
        if flag & 1:                       # literal
            b = rd()
            if b < 0:
                break
            out.append(b); win[wp] = b; wp = (wp + 1) & 0x3ff
        else:                              # backref
            b1 = rd(); b2 = rd()
            if b1 < 0 or b2 < 0:
                break
            length = (b2 & 0x3f) + 3
            disp = b1 | ((b2 & 0xc0) << 2)
            for k in range(length):
                c = win[(disp + k) & 0x3ff]
                out.append(c); win[wp] = c; wp = (wp + 1) & 0x3ff
    return bytes(out), f3, struct.unpack_from('<HH', ecd, 20)

def pal256(buf, base):
    out = []
    for k in range(256):
        o = base + k*2
        c = (buf[o] | (buf[o+1] << 8)) if o+1 < len(buf) else 0
        out.append((((c) & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3))
    return np.array(out, np.uint8)

def render8(pix, wt, palrgb):
    p = np.frombuffer(pix, np.uint8)
    nt = len(p)//64; ht = nt//wt
    p = p[:wt*ht*64].reshape(ht, wt, 8, 8)
    cv = np.zeros((ht*8, wt*8, 3), np.uint8)
    for ty in range(ht):
        for tx in range(wt):
            cv[ty*8:ty*8+8, tx*8:tx*8+8] = palrgb[p[ty, tx].astype(int)]
    return Image.fromarray(cv, 'RGB')

def _demo():
    """Decode the title/eyecatch image blocks and dump PNGs (needs a JP ROM dump
    + a savestate palette/vram next to this script). Reference only."""
    r = Rom('../Super Robot Wars K (Japan).nds')

    def get_block(arc, bi):
        d = r.get(arc); n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0 // 4
        offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]
        return d[offs[bi]:offs[bi + 1]]

    pal = open('_pal.bin', 'rb').read()
    vram = open('_vram.bin', 'rb').read()
    for arc, bi in (('data/add02dat.bin', 2345), ('data/add02dat.bin', 1872), ('data/add02dat.bin', 1874)):
        ecd = get_block(arc, bi)
        dec, f3, (w, h) = decomp_1024(ecd)
        pix = dec[8:]
        print(f"block {bi}: decoded {len(dec)}/{f3} bytes, pixels {len(pix)}, w={w} h={h}")
        x = vram.find(pix[:64]) if len(pix) >= 64 else -1
        print(f"   first64 in vram: {'@0x%05x' % x if x >= 0 else 'NO'}; first16={pix[:16].hex()}")
        for pn, pb in (('bg0', 0x000), ('obj', 0x200)):
            render8(pix, w, pal256(pal, pb)).save(f'_c1024_{bi}_{pn}.png')


if __name__ == '__main__':
    _demo()
