# -*- coding: utf-8 -*-
"""LZSS COMPRESSORS — inverse of srk_lzss decoders, to re-inject edited images.
Hash-chain match finder. Verified by round-trip against the decoders."""

def _matchfinder(data, max_disp):
    """yield best (len,dist) finder via 3-byte hash chains."""
    n = len(data)
    head = {}; prev = [0] * n
    def insert(i):
        if i + 2 < n:
            h = (data[i] << 16) | (data[i+1] << 8) | data[i+2]
            prev[i] = head.get(h, -1); head[h] = i
    return head, prev, insert

def _find(data, i, prev, head, max_len, max_disp, thr):
    n = len(data); best_len = 0; best_dist = 0
    if i + 2 >= n: return 0, 0
    h = (data[i] << 16) | (data[i+1] << 8) | data[i+2]
    j = head.get(h, -1); tries = 64
    jmax = min(max_len, n - i)
    while j >= 0 and tries > 0:
        if i - j > max_disp: break
        if data[j + best_len] == data[i + best_len] if best_len < jmax else False:
            pass
        l = 0
        while l < jmax and data[j + l] == data[i + l]: l += 1
        if l > best_len:
            best_len = l; best_dist = i - j
            if l >= jmax: break
        j = prev[j]; tries -= 1
    if best_len >= thr: return best_len, best_dist
    return 0, 0

class _Flags:
    def __init__(self, out): self.out=out; self.pos=None; self.bit=0; self.val=0
    def put(self, b):
        if self.bit==0:
            self.out.append(0); self.pos=len(self.out)-1; self.val=0
        if b: self.val |= (1<<self.bit)
        self.out[self.pos]=self.val; self.bit=(self.bit+1)&7

def compress_rel(data, max_len=18, max_disp=4095, thr=3):
    """8bpp IMG\x01 relative: ref{disp12=b0|((b1>>4)<<8), len=(b1&0xf)+3}."""
    out=bytearray(); fl=_Flags(out); n=len(data); i=0
    head,prev,insert=_matchfinder(data,max_disp)
    while i<n:
        ln,dist=_find(data,i,prev,head,max_len,max_disp,thr)
        if ln>=thr:
            fl.put(0); b0=dist&0xFF; b1=((dist>>8)<<4)|((ln-thr)&0xF)
            out.append(b0); out.append(b1)
            for k in range(ln): insert(i+k)
            i+=ln
        else:
            fl.put(1); out.append(data[i]); insert(i); i+=1
    return bytes(out)

def compress_ring(data, thr=3):
    """4bpp IMG\x00 absolute ring (N=4096, rr=N-18). pos=(rr-dist)&0xFFF,
    len 3-17 -> lnib=len-3; len 18-273 -> lnib=0xf + (len-18)."""
    N=4096; out=bytearray(); fl=_Flags(out); n=len(data); i=0; rr=N-18
    head,prev,insert=_matchfinder(data,N)
    max_len=273
    while i<n:
        ln,dist=_find(data,i,prev,head,max_len,N,thr)
        if ln>=thr:
            if dist>rr: dist_eff=dist  # pos wrap handles it
            pos=(rr-dist)&0xFFF
            fl.put(0); b0=pos&0xFF
            if ln<=17:
                b1=((pos>>8)<<4)&0xF0 | ((ln-thr)&0xF)
                out.append(b0); out.append(b1)
            else:
                b1=((pos>>8)<<4)&0xF0 | 0xF
                out.append(b0); out.append(b1); out.append((ln-18)&0xFF)
            for k in range(ln): insert(i+k)
            i+=ln; rr=(rr+ln)%N
        else:
            fl.put(1); out.append(data[i]); insert(i); i+=1; rr=(rr+1)%N
    return bytes(out)
