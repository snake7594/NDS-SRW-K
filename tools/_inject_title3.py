# -*- coding: utf-8 -*-
"""Re-encode the CORRECT 2D logo redraw and rebuild add02dat.bin, PADDING block
2360 to its exact original size so the archive is byte-identical everywhere
except inside the logo's own slot (no offset shift -> other images untouched)."""
import struct
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _enc1024b import build_ecd2
from _inject_title import rebuild_archive, archive_blocks_raw

KR_ROM = '../Super Robot Wars K (Korean)-기존패치.nds'
pixb = open('_fg_new.bin', 'rb').read()[0:0x7000]
print('new pixel bytes:', len(pixb))

rom = Rom(KR_ROM)
d = rom.get('data/add02dat.bin')
ne, offs = archive_blocks_raw(d)
orig = d[offs[2360]:offs[2361]]
f1 = int.from_bytes(orig[4:8], 'big'); f2 = int.from_bytes(orig[8:12], 'big')
f3 = struct.unpack_from('>I', orig, 12)[0]
print('orig block 2360: size=%d  payload(16+f2)=%d  trailing-pad=%d'
      % (len(orig), 16 + f2, len(orig) - (16 + f2)))
assert len(pixb) == f3 - 8, (len(pixb), f3 - 8)

raw = build_ecd2(orig, pixb, cap=1024)
assert len(raw) <= len(orig), ("re-encoded bigger than slot!", len(raw), len(orig))
new_block = raw + b'\x00' * (len(orig) - len(raw))      # pad to EXACT original size
assert len(new_block) == len(orig)
print('re-encoded %d B -> padded to %d B (orig)' % (len(raw), len(new_block)))

# decode still correct (decoder ignores trailing padding)
dec = decomp_1024(new_block)[0][8:8+(f3-8)]
assert dec == pixb, "re-encode round-trip FAILED"

new_arc, new_offs = rebuild_archive(d, {2360: new_block})
# STRICT: archive identical to original except inside block 2360's slot
assert len(new_arc) == len(d), (len(new_arc), len(d))
assert new_offs == offs[:-1], "offset table shifted!"
s, e = offs[2360], offs[2361]
assert new_arc[:s] == d[:s], "bytes before slot changed!"
assert new_arc[e:] == d[e:], "bytes after slot changed!"
dec2 = decomp_1024(new_arc[s:e])[0][8:8+(f3-8)]
assert dec2 == pixb, "archive decode mismatch"
open('kr/add02_patched.bin', 'wb').write(new_arc)
print('saved kr/add02_patched.bin (%d B == orig %d); ONLY block 2360 slot changed; verify OK'
      % (len(new_arc), len(d)))
