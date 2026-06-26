# -*- coding: utf-8 -*-
"""srk_lzss.py — SRW K custom graphics codec (CRACKED).

Container: add0X archives = u32 offset table -> blocks. Image blocks are ECD:
  [0]  'ECD\\x01'
  [4]  u32 BE  field1 (=8, type/flags)
  [8]  u32 BE  field2 (~ block payload size)
  [12] u32 BE  field3 = DECOMPRESSED size = 8 (header) + w*h*32*bpp/4 pixels
  [16] 'IMG\\x00'(uncompressed-ish) or 'IMG\\x01'  + u16 w_tiles + u16 h_tiles
  [24] LZSS-compressed (or raw) stream -> decompresses to [8 zero bytes][pixels]
Pixels = 8x8 tiled, 4bpp (or 8bpp when field3-8 == w*h*64).

Compression = classic ring-buffer LZSS:
  N=4096 window (init 0), pos starts at N-18, flag byte LSB-first,
  bit=1 -> literal byte, bit=0 -> 2-byte ref: pos12 = b0 | (b1&0xF0)<<4,
  length = (b1&0x0F)+3 ; if (b1&0x0F)==0xF -> length = 3+0xF+next_byte (extended).
"""
import struct
from PIL import Image
import numpy as np

N_WIN, THR = 4096, 3


def lzss_decompress(src, target):
    """Ring-buffer LZSS -> bytes (stops at `target` length)."""
    buf = bytearray(N_WIN)
    rr = N_WIN - 18
    out = bytearray()
    i, n = 0, len(src)
    while i < n and len(out) < target:
        flag = src[i]; i += 1
        for b in range(8):
            if len(out) >= target or i >= n:
                break
            if (flag >> b) & 1:                       # literal
                c = src[i]; i += 1
                out.append(c); buf[rr] = c; rr = (rr + 1) % N_WIN
            else:                                      # back-reference
                if i + 1 >= n:
                    break
                b0, b1 = src[i], src[i + 1]; i += 2
                pos = b0 | ((b1 & 0xF0) << 4)
                lnib = b1 & 0x0F
                ln = lnib + THR
                if lnib == 0xF:
                    ln = THR + 0xF + src[i]; i += 1
                for k in range(ln):
                    c = buf[(pos + k) % N_WIN]
                    out.append(c); buf[rr] = c; rr = (rr + 1) % N_WIN
    return bytes(out)


def lzss_decompress_rel(src, target):
    """IMG\\x01 (8bpp) variant: SLIDING-window relative LZSS. flag LSB-first,
    bit=1 literal, bit=0 2-byte ref: disp = (b0 | ((b1>>4)<<8)) [12-bit back
    distance from current output], length = (b1&0x0F)+3, NO extension. Copy from
    out[-disp] (auto-extends for runs). Verified on add04 8bpp blocks (MAD~1)."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n and len(out) < target:
        flag = src[i]; i += 1
        for b in range(8):
            if len(out) >= target or i >= n:
                break
            if (flag >> b) & 1:
                out.append(src[i]); i += 1
            else:
                if i + 1 >= n:
                    break
                b0 = src[i]; b1 = src[i + 1]; i += 2
                disp = (b0 | ((b1 >> 4) << 8)) or 1
                length = (b1 & 0x0F) + 3
                for _ in range(length):
                    out.append(out[-disp] if len(out) >= disp else 0)
    return bytes(out)


def archive_blocks(data):
    n0 = struct.unpack_from("<I", data, 0)[0]; ne = n0 // 4
    offs = list(struct.unpack_from(f"<{ne}I", data, 0)) + [len(data)]
    return [(i, data[offs[i]:offs[i + 1]]) for i in range(ne)]


def parse_ecd(blk):
    """Return dict(w_tiles,h_tiles,bpp,decomp_size,pixels) or None if not ECD/IMG."""
    if blk[:4] != b"ECD\x01" or blk[16:19] != b"IMG":
        return None
    f3 = struct.unpack_from(">I", blk, 12)[0]          # decompressed size
    w, h = struct.unpack_from("<HH", blk, 20)
    pix_bytes = f3 - 8
    if w == 0 or h == 0 or pix_bytes <= 0:
        return None
    bpp = 4 if pix_bytes == w * h * 32 else (8 if pix_bytes == w * h * 64 else 0)
    # IMG\x00 -> absolute ring-buffer LZSS; IMG\x01 -> relative sliding-window LZSS
    if blk[19] == 1:
        decomp = lzss_decompress_rel(blk[24:], f3)
    else:
        decomp = lzss_decompress(blk[24:], f3)
    pixels = decomp[8:8 + pix_bytes]
    return {"w": w, "h": h, "bpp": bpp, "decomp_size": f3, "pixels": pixels}


def render_tiled(pixels, w_tiles, h_tiles, bpp=4, palette=None):
    """8x8-tiled -> PIL image (grayscale if no palette)."""
    if bpp == 4:
        need = w_tiles * h_tiles * 32
        d = (pixels + b"\x00" * need)[:need]
        a = np.frombuffer(d, np.uint8)
        p = np.empty(len(a) * 2, np.uint8); p[0::2] = a & 0xF; p[1::2] = a >> 4
    else:
        need = w_tiles * h_tiles * 64
        d = (pixels + b"\x00" * need)[:need]
        p = np.frombuffer(d, np.uint8).copy()
    p = p[:w_tiles * h_tiles * 64].reshape(h_tiles, w_tiles, 8, 8)
    cv = np.zeros((h_tiles * 8, w_tiles * 8), np.uint8)
    for ty in range(h_tiles):
        for tx in range(w_tiles):
            cv[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = p[ty, tx]
    if palette is not None:
        rgb = np.zeros((cv.shape[0], cv.shape[1], 3), np.uint8)
        for idx, col in enumerate(palette):
            rgb[cv == idx] = col
        return Image.fromarray(rgb, "RGB")
    scale = 17 if bpp == 4 else 1
    return Image.fromarray((cv * scale).astype(np.uint8), "L")
