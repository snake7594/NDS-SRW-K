# -*- coding: utf-8 -*-
"""build_rom_all.py — build the final patched .nds with ALL native translations:
  * scenario  : srwk_scenario_clean.json -> data/add03dat.bin (build_native)
  * battle    : srwk_battle.json          -> data/add05dat.bin (build_battle)
into the existing KR rom (which already carries the font + overlay patches).

  python build_rom_all.py          # build patched rom
  python build_rom_all.py --check  # regression: both rebuilds == KR rom files
"""
import os, sys, hashlib, struct
from srwk_rom import Rom
import build_native
import build_battle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KR_ROM = os.path.join(ROOT, "Super Robot Wars K (Korean)-기존패치.nds")
OUT_ROM = os.path.join(ROOT, "Super Robot Wars K (Korean)-NEW.nds")


def _sha(b):
    return hashlib.sha1(b).hexdigest()


def patch(out_path=OUT_ROM):
    add03, s3 = build_native.build()
    add05, s5 = build_battle.build()
    rom = Rom(KR_ROM)
    rom.set("data/add03dat.bin", add03)
    rom.set("data/add05dat.bin", add05)
    # add02: inject Korean title logo (block 2360 re-encoded, see _inject_title.py)
    add02p = os.path.join(HERE, "kr", "add02_patched.bin")
    if os.path.exists(add02p):
        rom.set("data/add02dat.bin", open(add02p, "rb").read())
        print(f"  add02   : injected Korean title logo")
    # arm9: inject the 15 untranslated name/system-message fixes (see _inject_arm9.py)
    arm9p = os.path.join(HERE, "kr", "arm9_patched.bin")
    if os.path.exists(arm9p):
        a9 = open(arm9p, "rb").read()
        assert len(a9) == len(rom.rom.arm9), "patched arm9 size mismatch"
        rom.rom.arm9 = a9
        print(f"  arm9    : injected name/system-message patch ({len(a9)} B)")
    # ovl_003: inject Korean staff-credits (overlay EXTENDED -> update ramSize in
    # the arm9 overlay table, entry index == overlayID 3, ramSize @ entry+8).
    ovl3 = os.path.join(HERE, "kr", "overlays", "ovl_003_patched.bin")
    if os.path.exists(ovl3):
        d = open(ovl3, "rb").read()
        rom.rom.files[3] = d
        ot = bytearray(rom.rom.arm9OverlayTable)
        struct.pack_into("<I", ot, 3 * 32 + 8, len(d))     # ramSize = new file size
        rom.rom.arm9OverlayTable = bytes(ot)
        print(f"  ovl_003 : injected credits ({len(d)} B, ramSize updated)")
    rom.save(out_path)
    print(f"saved {out_path}")
    print(f"  scenario: re-encoded {s3['changed']} blocks")
    print(f"  battle  : changed {s5['changed_entries']} entries, "
          f"overflow {len(s5['overflow'])}, missing-char {len(s5['missing'])}")
    if s5["missing"]:
        print("  !! battle missing-char lines (kept original — fix in JSON):")
        for n, i, chars, text in s5["missing"][:10]:
            print(f"     entry {n} vl {i}: [{chars}]")
    return out_path


def check():
    add03, _ = build_native.build()
    add05, _ = build_battle.build()
    rom = Rom(KR_ROM)
    ok3 = _sha(add03) == _sha(rom.get("data/add03dat.bin"))
    ok5 = _sha(add05) == _sha(rom.get("data/add05dat.bin"))
    print(f"no-edit add03 == KR rom: {ok3}")
    print(f"no-edit add05 == KR rom: {ok5}")
    return ok3 and ok5


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        patch()
