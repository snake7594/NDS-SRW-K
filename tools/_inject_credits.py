# -*- coding: utf-8 -*-
"""Inject Korean staff-credit translations into ovl_003 (RAM base 0x021e6700).
Reads _credits_tr.json [{off, ko}].  In-place where KO fits the slot budget;
otherwise append to an extended region at the end of the overlay and repoint the
overlay-internal pointer(s).  Writes kr/overlays/ovl_003_patched.bin and prints
the new ramSize (build_rom_all injects it + updates the overlay table)."""
import io, json, struct
from srwk_codec import HAN2CODE

RAM = 0x021e6700
ov = bytearray(open('kr/overlays/ovl_003.bin', 'rb').read())
ORIG = len(ov)


def enc(s):
    out = bytearray()
    for ch in s:
        if ch in HAN2CODE:
            out += struct.pack('>H', HAN2CODE[ch])
        elif ord(ch) < 0x80:
            out.append(ord(ch))
        elif ch == '／':           # fullwidth slash -> SJIS 0x815E
            out += b'\x81\x5e'
        elif ch == '（':
            out += b'\x81\x69'
        elif ch == '）':
            out += b'\x81\x6a'
        else:
            raise ValueError('unencodable %r in %r' % (ch, s))
    return bytes(out)


def budget(off):
    e = off
    while e < len(ov) and ov[e] != 0:
        e += 1
    z = e
    while z < len(ov) and ov[z] == 0:
        z += 1
    return z - off


def ptrs_in_ovl(off):
    tgt = RAM + off
    return [k for k in range(0, len(ov) - 3) if struct.unpack_from('<I', ov, k)[0] == tgt]


def main():
    tr = json.load(io.open('_credits_tr.json', encoding='utf-8'))
    log = io.open('_credits_inj_log.txt', 'w', encoding='utf-8')
    # extension region starts at current end (pad to 4). Reserve the first 4
    # bytes as zeros: the original overlay has legacy "empty-string" pointers to
    # offset len(ov) (the boundary) — keep them pointing at a NUL so they stay empty.
    ext = bytearray(4)
    ext_base = (len(ov) + 3) & ~3
    pad0 = ext_base - len(ov)
    inplace = repoint = noptr = 0
    for e in sorted(tr, key=lambda x: x['off']):
        off, ko = e['off'], e['ko']
        b = enc(ko)
        if len(b) + 1 <= budget(off):
            ov[off:off + len(b)] = b
            for k in range(off + len(b), off + budget(off)):
                ov[k] = 0
            inplace += 1
            log.write('IN-PLACE 0x%04x b=%d bud=%d  %s\n' % (off, len(b), budget(off), ko))
        else:
            ps = ptrs_in_ovl(off)
            if not ps:
                noptr += 1
                log.write('!! 0x%04x NO ovl-internal pointer; left JP  %s\n' % (off, ko))
                continue
            new_off = ext_base + len(ext)
            ext += b + b'\x00'
            if len(ext) % 2:           # keep 2-byte alignment for next
                ext += b'\x00'
            for p in ps:
                struct.pack_into('<I', ov, p, RAM + new_off)
            repoint += 1
            log.write('REPOINT  0x%04x -> 0x%04x (%d ptr) bud=%d use=%d  %s\n'
                      % (off, new_off, len(ps), budget(off), len(b) + 1, ko))
    # trailing pad: keep the overlay's bss zone (last bssSize bytes the loader may
    # zero-init) as empty padding, never real string data.
    patched = bytes(ov) + b'\x00' * pad0 + bytes(ext) + b'\x00' * 64
    open('kr/overlays/ovl_003_patched.bin', 'wb').write(patched)
    log.write('\norig=%d patched=%d (ramSize must become %d)\n' % (ORIG, len(patched), len(patched)))
    log.write('in-place=%d repoint=%d no-ptr=%d\n' % (inplace, repoint, noptr))
    log.close()
    print('in-place=%d repoint=%d no-ptr=%d  patched_len=%d (orig %d)'
          % (inplace, repoint, noptr, len(patched), ORIG))


if __name__ == '__main__':
    main()
