# -*- coding: utf-8 -*-
"""Re-encode the Korean title logo (block 2360) and rebuild add02dat.bin.
Outputs kr/add02_patched.bin. Verifies by re-extracting + decoding."""
import struct, os
import numpy as np
from srwk_rom import Rom
from _codec1024 import decomp_1024
from _enc1024 import build_ecd

ROOT = '..'
KR_ROM = os.path.join(ROOT, 'Super Robot Wars K (Korean)-기존패치.nds')

def pack4bpp(idx):
    """(H,W) index grid -> 8x8-tiled 4bpp bytes (low nibble=even pixel)."""
    H, W = idx.shape
    wt, ht = W//8, H//8
    out = bytearray()
    for ty in range(ht):
        for tx in range(wt):
            tile = idx[ty*8:ty*8+8, tx*8:tx*8+8].reshape(-1)
            for i in range(0, 64, 2):
                out.append((int(tile[i]) & 0xF) | ((int(tile[i+1]) & 0xF) << 4))
    return bytes(out)

def archive_blocks_raw(d):
    n0 = struct.unpack_from('<I', d, 0)[0]; ne = n0//4
    offs = list(struct.unpack_from('<%dI' % ne, d, 0)) + [len(d)]
    return ne, offs

def rebuild_archive(d, replacements):
    """replacements: {block_index: new_bytes}. Returns new archive bytes."""
    ne, offs = archive_blocks_raw(d)
    blocks = [bytearray(d[offs[i]:offs[i+1]]) for i in range(ne)]
    for bi, nb in replacements.items():
        blocks[bi] = bytearray(nb)
    # rebuild offset table
    table_size = ne*4
    new_offs = []
    cur = table_size
    for i in range(ne):
        new_offs.append(cur); cur += len(blocks[i])
    out = bytearray()
    for o in new_offs:
        out += struct.pack('<I', o)
    for b in blocks:
        out += b
    return bytes(out), new_offs

def main():
    rom = Rom(KR_ROM)
    d = rom.get('data/add02dat.bin')
    ne, offs = archive_blocks_raw(d)
    orig = d[offs[2360]:offs[2361]]
    # sanity: KR title block decodes to same dims
    f3 = struct.unpack_from('>I', orig, 12)[0]
    w, h = struct.unpack_from('<HH', orig, 20)
    print(f"KR add02 #2360: w={w} h={h} f3={f3} streamlen={len(orig)-0x18}")

    new_idx = np.load('_logo_idx_new.npy')
    assert new_idx.shape == (h*8, w*8), f"shape {new_idx.shape} != {(h*8, w*8)}"
    new_pix = pack4bpp(new_idx)
    new_block = build_ecd(orig, new_pix)

    # verify round-trip through the game-mirroring decoder
    dec = decomp_1024(new_block)[0][8:8+(f3-8)]
    assert dec == new_pix, "re-encode round-trip FAILED"
    print(f"re-encode OK: new block {len(new_block)} B (orig {len(orig)} B, "
          f"delta {len(new_block)-len(orig):+d})")

    new_arc, _ = rebuild_archive(d, {2360: new_block})
    # verify archive: extract 2360 again
    ne2, offs2 = archive_blocks_raw(new_arc)
    re_extracted = new_arc[offs2[2360]:offs2[2360+1]]
    assert re_extracted == new_block, "archive re-extract mismatch"
    dec2 = decomp_1024(re_extracted)[0][8:8+(f3-8)]
    assert dec2 == new_pix, "archive decode mismatch"
    os.makedirs('kr', exist_ok=True)
    open('kr/add02_patched.bin', 'wb').write(new_arc)
    print(f"saved kr/add02_patched.bin ({len(new_arc)} B, orig {len(d)} B, "
          f"delta {len(new_arc)-len(d):+d}); archive verify OK")

if __name__ == '__main__':
    main()
