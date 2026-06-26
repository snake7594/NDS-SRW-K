#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
srk_gfx.py  --  Super Robot Wars K (NDS) graphics finder / dumper

Goal: locate the image files that contain baked-in Japanese text so they can be
redrawn in Korean, then (later) reinserted.

Pipeline performed by `dump`:
  ROM -> walk Nitro filesystem (recover real paths)
      -> recurse into NARC archives
      -> auto-decompress Nitro LZ10 (0x10) / LZ11 (0x11)
      -> parse NCGR(+pair NCLR from same dir) -> PNG
      -> write manifest.csv + visual contact sheets for fast eyeballing

This is format-standard tooling (RGCN/RLCN etc.). If K stores some graphics
head-less (raw tile blobs, like CrystalTile2's manual offset+width workflow),
those land in _unknown/ as .bin and can optionally be blind-rendered with
--raw-render for the contact sheet.

No third-party deps except Pillow.
"""

import os, sys, csv, struct, argparse
from pathlib import Path

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


# --------------------------------------------------------------------------- #
#  Nitro LZSS decompression
# --------------------------------------------------------------------------- #
def _read_size_header(data, p):
    """Return (decompressed_size, new_pos). Handles the 0-then-u32 extension."""
    size = data[p] | (data[p + 1] << 8) | (data[p + 2] << 16)
    p += 3
    if size == 0:
        size = struct.unpack_from("<I", data, p)[0]
        p += 4
    return size, p


def decompress_lz10(data):
    """Nintendo LZ10 (header byte 0x10). Returns bytes."""
    assert data[0] == 0x10, "not LZ10"
    out = bytearray()
    size, p = _read_size_header(data, 1)
    while len(out) < size:
        flags = data[p]; p += 1
        for i in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> i):                      # back-reference
                b0, b1 = data[p], data[p + 1]; p += 2
                disp = (((b0 & 0x0F) << 8) | b1) + 1
                length = (b0 >> 4) + 3
                start = len(out) - disp
                if start < 0:
                    raise ValueError("LZ10 bad displacement")
                for _ in range(length):
                    out.append(out[start]); start += 1
            else:                                        # literal
                out.append(data[p]); p += 1
    return bytes(out[:size])


def decompress_lz11(data):
    """Nintendo LZ11 (header byte 0x11). Returns bytes."""
    assert data[0] == 0x11, "not LZ11"
    out = bytearray()
    size, p = _read_size_header(data, 1)
    while len(out) < size:
        flags = data[p]; p += 1
        for i in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> i):
                b0 = data[p]; n = b0 >> 4
                if n == 0:
                    b1, b2 = data[p + 1], data[p + 2]; p += 3
                    length = (((b0 & 0x0F) << 4) | (b1 >> 4)) + 0x11
                    disp = (((b1 & 0x0F) << 8) | b2) + 1
                elif n == 1:
                    b1, b2, b3 = data[p + 1], data[p + 2], data[p + 3]; p += 4
                    length = (((b0 & 0x0F) << 12) | (b1 << 4) | (b2 >> 4)) + 0x111
                    disp = (((b2 & 0x0F) << 8) | b3) + 1
                else:
                    b1 = data[p + 1]; p += 2
                    length = n + 1
                    disp = (((b0 & 0x0F) << 8) | b1) + 1
                start = len(out) - disp
                if start < 0:
                    raise ValueError("LZ11 bad displacement")
                for _ in range(length):
                    out.append(out[start]); start += 1
            else:
                out.append(data[p]); p += 1
    return bytes(out[:size])


def maybe_decompress(data):
    """If data looks LZ-compressed, decompress it; else return as-is.
    Returns (data, tag) where tag is '', 'lz10', or 'lz11'."""
    if len(data) < 5:
        return data, ""
    try:
        if data[0] == 0x10:
            d = decompress_lz10(data)
            if len(d) >= len(data) // 2:        # sanity: real compression
                return d, "lz10"
        elif data[0] == 0x11:
            d = decompress_lz11(data)
            if len(d) >= len(data) // 2:
                return d, "lz11"
    except Exception:
        pass
    return data, ""


# --------------------------------------------------------------------------- #
#  Nitro filesystem (ROM)  +  NARC archive
# --------------------------------------------------------------------------- #
def parse_rom_filesystem(rom):
    """Yield (path, bytes) for every file in an NDS ROM, with real paths."""
    fnt_off, fnt_size, fat_off, fat_size = struct.unpack_from("<IIII", rom, 0x40)
    n_files = fat_size // 8
    fat = [struct.unpack_from("<II", rom, fat_off + 8 * i) for i in range(n_files)]

    # main FNT table: first entry has the total dir count in its parent field
    first_sub, first_id, total_dirs = struct.unpack_from("<IHH", rom, fnt_off)
    dirs = {}
    for d in range(total_dirs):
        sub_off, start_id, parent = struct.unpack_from("<IHH", rom, fnt_off + 8 * d)
        dirs[0xF000 + d] = {"sub": fnt_off + sub_off, "first": start_id,
                            "parent": parent, "name": "", "names": []}

    def walk(dir_id):
        d = dirs[dir_id]
        p = d["sub"]; fid = d["first"]
        while True:
            t = rom[p]; p += 1
            if t == 0:
                break
            ln = t & 0x7F
            name = rom[p:p + ln].decode("shift_jis", "replace"); p += ln
            if t & 0x80:                                  # subdirectory
                child = struct.unpack_from("<H", rom, p)[0]; p += 2
                dirs[child]["name"] = name
                d["names"].append(("d", child, name))
            else:                                         # file
                d["names"].append(("f", fid, name)); fid += 1

    for did in dirs:
        walk(did)

    def fullpath(dir_id):
        parts = []
        while dir_id != 0xF000 and dir_id in dirs:
            parts.append(dirs[dir_id]["name"]); dir_id = dirs[dir_id]["parent"]
        return "/".join(reversed(parts))

    for did, d in dirs.items():
        base = fullpath(did)
        for kind, idn, name in d["names"]:
            if kind == "f":
                s, e = fat[idn]
                yield (f"{base}/{name}" if base else name, rom[s:e])


def parse_narc(data):
    """Yield (index, bytes) for sub-files in a NARC. Empty if not a NARC."""
    if data[:4] != b"NARC":
        return
    # locate sections by magic (robust to header variations)
    def find(magic, start=0):
        return data.find(magic, start)

    btaf = find(b"BTAF")
    gmif = find(b"GMIF")
    if btaf < 0 or gmif < 0:
        return
    n = struct.unpack_from("<H", data, btaf + 8)[0]
    img = gmif + 8                                        # GMIF data start
    for i in range(n):
        s, e = struct.unpack_from("<II", data, btaf + 12 + 8 * i)
        yield i, data[img + s: img + e]


# --------------------------------------------------------------------------- #
#  NCGR (tiles)  +  NCLR (palette)
# --------------------------------------------------------------------------- #
def parse_nclr(data):
    """Return list of palettes, each a list of (r,g,b). Handles multi-palette."""
    if data[:4] != b"RLCN":
        return []
    pltt = data.find(b"TTLP")
    if pltt < 0:
        return []
    sec_size = struct.unpack_from("<I", data, pltt + 4)[0]
    bpp = struct.unpack_from("<I", data, pltt + 8)[0]    # 3=16col, 4=256col
    data_len = struct.unpack_from("<I", data, pltt + 0x10)[0]
    sec_end = min(pltt + sec_size, len(data)) if sec_size else len(data)
    body_avail = sec_end - (pltt + 0x18)
    if 0 < data_len <= body_avail + 8:
        raw = data[sec_end - data_len: sec_end]
    else:
        raw = data[pltt + 0x18: sec_end]
    colors = []
    for i in range(0, len(raw) - 1, 2):
        c = raw[i] | (raw[i + 1] << 8)
        r = (c & 0x1F) << 3; g = ((c >> 5) & 0x1F) << 3; b = ((c >> 10) & 0x1F) << 3
        colors.append((r | r >> 5, g | g >> 5, b | b >> 5))
    per = 16 if bpp == 3 else 256
    return [colors[i:i + per] for i in range(0, len(colors), per)] or [colors]


def parse_ncgr(data):
    """Return dict: bpp(4/8), w, h, tiles(bytes), linear(bool). Or None."""
    if data[:4] != b"RGCN":
        return None
    char = data.find(b"RAHC")
    if char < 0:
        return None
    sec_size = struct.unpack_from("<I", data, char + 4)[0]
    h_tiles = struct.unpack_from("<H", data, char + 8)[0]
    w_tiles = struct.unpack_from("<H", data, char + 10)[0]
    fmt = struct.unpack_from("<I", data, char + 12)[0]   # 3=4bpp, 4=8bpp
    tdata_len = struct.unpack_from("<I", data, char + 20)[0]
    bpp = 4 if fmt == 3 else 8

    # tile data = trailing tdata_len bytes of the CHAR section (offset-constant
    # conventions vary between tools/files, so don't trust the offset field).
    sec_end = min(char + sec_size, len(data)) if sec_size else len(data)
    body_avail = sec_end - (char + 8)
    if 0 < tdata_len <= body_avail:
        tiles = data[sec_end - tdata_len: sec_end]
    else:                                                # fallback: skip 0x18 header
        tiles = data[char + 0x18:sec_end]

    w = w_tiles * 8 if w_tiles not in (0, 0xFFFF) else None
    h = h_tiles * 8 if h_tiles not in (0, 0xFFFF) else None
    # Almost all NDS background/sprite NCGR are 8x8 tiled; default to tiled and
    # let the operator flag the rare linear ("1D scanned") sheet if it looks wrong.
    return {"bpp": bpp, "w": w, "h": h, "tiles": tiles, "linear": False}


def render_ncgr(ng, palette, default_width=256):
    """Return a PIL Image (RGB) from a parsed NCGR + palette list[(r,g,b)]."""
    bpp = ng["bpp"]; tiles = ng["tiles"]
    px_per_byte = 2 if bpp == 4 else 1
    total_px = len(tiles) * px_per_byte
    if total_px == 0:
        return None

    # decode to a flat list of palette indices
    idx = []
    if bpp == 4:
        for b in tiles:
            idx.append(b & 0x0F); idx.append(b >> 4)
    else:
        idx = list(tiles)

    w = ng["w"] or default_width
    if not ng["linear"]:
        w = (w // 8) * 8 or 8
    h = ng["h"]
    if h is None:
        rows = (total_px + w - 1) // w
        h = ((rows + 7) // 8) * 8 if not ng["linear"] else rows
        h = max(h, 8)

    img = Image.new("RGB", (w, h), (255, 0, 255))
    pal = palette or [(i, i, i) for i in range(256)]      # grayscale fallback

    def putpix(x, y, ci):
        if 0 <= x < w and 0 <= y < h:
            img.putpixel((x, y), pal[ci] if ci < len(pal) else (ci, ci, ci))

    if ng["linear"]:
        for n, ci in enumerate(idx):
            putpix(n % w, n // w, ci)
    else:                                                 # 8x8 tiled
        tiles_x = w // 8
        for t in range(len(idx) // 64):
            tx, ty = (t % tiles_x) * 8, (t // tiles_x) * 8
            for k in range(64):
                putpix(tx + (k % 8), ty + (k // 8), idx[t * 64 + k])
    return img


# --------------------------------------------------------------------------- #
#  dump command
# --------------------------------------------------------------------------- #
NITRO_MAGICS = (b"RGCN", b"RLCN", b"RCSN", b"RECN", b"RNAN")   # NCGR NCLR NSCR NCER NANR


def group_key(path):
    """Files that may share a palette: same NARC (before '#') or same directory."""
    if "#" in path:
        return path.split("#")[0]
    return path.rsplit("/", 1)[0]


def collect_files(rom_bytes):
    """Flatten ROM + nested NARCs into [(path, data)] with decompression applied."""
    out = []
    for path, raw in parse_rom_filesystem(rom_bytes):
        data, tag = maybe_decompress(raw)
        subs = list(parse_narc(data))
        if subs:
            for i, sd in subs:
                sd2, stag = maybe_decompress(sd)
                out.append((f"{path}#{i:04d}", sd2, stag or tag))
        else:
            out.append((path, data, tag))
    return out


def cmd_dump(args):
    if not HAVE_PIL:
        sys.exit("Pillow required: pip install pillow")
    rom = Path(args.rom).read_bytes()
    outdir = Path(args.out); (outdir / "png").mkdir(parents=True, exist_ok=True)
    (outdir / "_unknown").mkdir(exist_ok=True)

    files = collect_files(rom)
    # index palettes by their directory so an NCGR can find a sibling NCLR
    pal_by_dir = {}
    for path, data, _ in files:
        if data[:4] == b"RLCN":
            pal_by_dir.setdefault(group_key(path), []).append(parse_nclr(data))

    rows = []
    sheet_imgs = []
    n_ncgr = 0
    for path, data, tag in files:
        magic = data[:4]
        if magic == b"RGCN":
            ng = parse_ncgr(data)
            if not ng:
                continue
            pals = pal_by_dir.get(group_key(path), [])
            palette = None
            for plist in pals:
                if plist:
                    palette = plist[0]; break
            img = render_ncgr(ng, palette, args.default_width)
            if img is None:
                continue
            safe = path.replace("/", "__").replace("#", "_")
            fn = outdir / "png" / f"{safe}.png"
            img.save(fn)
            n_ncgr += 1
            sheet_imgs.append((img, safe))
            rows.append([path, "NCGR", f"{img.width}x{img.height}",
                         f"{ng['bpp']}bpp", "tiled" if not ng["linear"] else "linear",
                         tag, "yes" if palette else "grayscale"])
        elif magic in NITRO_MAGICS:
            rows.append([path, magic.decode("ascii", "replace"), "", "", "", tag, ""])
        elif args.dump_unknown:
            safe = path.replace("/", "__").replace("#", "_")
            (outdir / "_unknown" / f"{safe}.bin").write_bytes(data)

    # manifest
    with open(outdir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "type", "dims", "bpp", "layout", "compression", "palette"])
        w.writerows(rows)

    # contact sheets (grids) for fast visual scanning of Japanese text
    make_contact_sheets(sheet_imgs, outdir / "contact", cols=args.sheet_cols,
                        thumb=args.sheet_thumb)

    print(f"files scanned : {len(files)}")
    print(f"NCGR -> PNG   : {n_ncgr}  (see {outdir/'png'})")
    print(f"contact sheets: {outdir/'contact'}  <- scan these for Japanese text")
    print(f"manifest      : {outdir/'manifest.csv'}")


def make_contact_sheets(imgs, outdir, cols=8, thumb=128, per_sheet=64):
    if not imgs:
        return
    outdir.mkdir(parents=True, exist_ok=True)
    from PIL import ImageDraw
    pad, label_h = 4, 12
    cell = thumb + pad * 2
    cellh = thumb + pad * 2 + label_h
    for s in range(0, len(imgs), per_sheet):
        batch = imgs[s:s + per_sheet]
        rows = (len(batch) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * cellh), (30, 30, 30))
        draw = ImageDraw.Draw(sheet)
        for k, (im, name) in enumerate(batch):
            t = im.copy(); t.thumbnail((thumb, thumb))
            cx, cy = (k % cols) * cell + pad, (k // cols) * cellh + pad
            sheet.paste(t, (cx, cy))
            short = name[-22:]
            draw.text((cx, cy + thumb + 1), short, fill=(200, 200, 200))
        sheet.save(outdir / f"sheet_{s//per_sheet:03d}.png")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="SRW K (NDS) graphics finder/dumper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump", help="extract & render all graphics from a ROM")
    d.add_argument("rom")
    d.add_argument("out")
    d.add_argument("--default-width", type=int, default=256,
                   help="px width for NCGR with no stored dimensions (default 256)")
    d.add_argument("--dump-unknown", action="store_true",
                   help="also write head-less/unrecognized blobs to _unknown/")
    d.add_argument("--sheet-cols", type=int, default=8)
    d.add_argument("--sheet-thumb", type=int, default=128)
    d.set_defaults(func=cmd_dump)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
