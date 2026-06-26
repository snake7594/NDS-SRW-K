# -*- coding: utf-8 -*-
"""srk_dump.py — extract ALL images from Super Robot Wars K (NDS).

SRW K does NOT use standard Nitro formats (NARC/NCGR) — confirmed by srk_gfx.py
finding 0 NCGR. Graphics are a CUSTOM tagged format (ECD/IMG/PLT/CEL/MAP/SCR)
inside the data/add0X archives, with a CUSTOM ring-buffer LZSS (see srk_lzss.py).

This dumps every ECD image block in every archive to PNG (grayscale by palette
index) + per-archive contact sheets + manifest.csv, so the baked-in Japanese
text images (chapter eyecatch 第N話…, captions 二ヵ月後…, UI/name plates) can be
found by eye, then redrawn in Korean and re-injected.

  python srk_dump.py            # dump all archives -> _gfx/
"""
import os, sys, csv, struct
from PIL import Image, ImageDraw
import numpy as np
from srwk_rom import Rom

N_WIN, THR = 4096, 3
ROM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "Super Robot Wars K (Japan).nds")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_gfx")
ARCHIVES = ["data/add02dat.bin", "data/add04dat.bin", "data/add08dat.bin",
            "btlPicDat.bin", "btlCutinPicData.bin"]


def lzss_rel(src, target):
    """IMG\\x01 (8bpp) sliding-window relative LZSS."""
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
                for _ in range((b1 & 0x0F) + 3):
                    out.append(out[-disp] if len(out) >= disp else 0)
    return bytes(out)


def lzss(src, target):
    """Ring-buffer LZSS -> bytes (best-effort up to `target`)."""
    buf = bytearray(N_WIN)
    rr = N_WIN - 18
    out = bytearray()
    i, n = 0, len(src)
    ap = out.append
    while i < n and len(out) < target:
        flag = src[i]; i += 1
        for b in range(8):
            if len(out) >= target or i >= n:
                break
            if (flag >> b) & 1:
                c = src[i]; i += 1
                ap(c); buf[rr] = c; rr = (rr + 1) & 0xFFF
            else:
                if i + 1 >= n:
                    break
                b0 = src[i]; b1 = src[i + 1]; i += 2
                pos = b0 | ((b1 & 0xF0) << 4)
                lnib = b1 & 0x0F
                ln = lnib + THR
                if lnib == 0xF:
                    if i >= n:
                        break
                    ln = THR + 0xF + src[i]; i += 1
                for k in range(ln):
                    c = buf[(pos + k) & 0xFFF]
                    ap(c); buf[rr] = c; rr = (rr + 1) & 0xFFF
    return bytes(out)


def archive_blocks(data):
    n0 = struct.unpack_from("<I", data, 0)[0]; ne = n0 // 4
    if ne <= 0 or ne > 100000:
        return []
    offs = list(struct.unpack_from(f"<{ne}I", data, 0)) + [len(data)]
    return [(i, data[offs[i]:offs[i + 1]]) for i in range(ne)]


def parse_ecd(blk):
    if blk[:4] != b"ECD\x01" or blk[16:19] != b"IMG":
        return None
    f3 = struct.unpack_from(">I", blk, 12)[0]
    w, h = struct.unpack_from("<HH", blk, 20)
    pix = f3 - 8
    if w == 0 or h == 0 or pix <= 0 or pix > 4_000_000:
        return None
    bpp = 4 if pix == w * h * 32 else (8 if pix == w * h * 64 else 4)
    decomp = (lzss_rel if blk[19] == 1 else lzss)(blk[24:], f3)
    return {"w": w, "h": h, "bpp": bpp, "img_type": blk[19],
            "pixels": decomp[8:8 + pix], "got": len(decomp) - 8, "need": pix}


def render(info):
    w, h, bpp = info["w"], info["h"], info["bpp"]
    px = info["pixels"]
    if bpp == 4:
        need = w * h * 32
        d = (px + b"\x00" * need)[:need]
        a = np.frombuffer(d, np.uint8)
        p = np.empty(len(a) * 2, np.uint8); p[0::2] = a & 0xF; p[1::2] = a >> 4
        scale = 17
    else:
        need = w * h * 64
        d = (px + b"\x00" * need)[:need]
        p = np.frombuffer(d, np.uint8).copy()
        scale = 1
    p = p[:w * h * 64].reshape(h, w, 8, 8)
    cv = np.zeros((h * 8, w * 8), np.uint8)
    for ty in range(h):
        for tx in range(w):
            cv[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = p[ty, tx]
    return Image.fromarray((cv * scale).astype(np.uint8), "L")


def contact_sheets(imgs, outdir, cols=8, thumb=128, per=64):
    os.makedirs(outdir, exist_ok=True)
    for s in range(0, len(imgs), per):
        batch = imgs[s:s + per]
        rows = (len(batch) + cols - 1) // cols
        cw, ch = thumb + 6, thumb + 18
        sheet = Image.new("L", (cols * cw, rows * ch), 30)
        dr = ImageDraw.Draw(sheet)
        for k, (name, im) in enumerate(batch):
            t = im.copy(); t.thumbnail((thumb, thumb))
            cx, cy = (k % cols) * cw + 3, (k // cols) * ch + 3
            sheet.paste(t, (cx, cy))
            dr.text((cx, cy + t.height + 1), name, fill=255)
        sheet.save(os.path.join(outdir, f"sheet_{s // per:03d}.png"))


def main():
    rom = Rom(ROM)
    os.makedirs(os.path.join(OUT, "png"), exist_ok=True)
    rows = []
    total = 0
    for arc in ARCHIVES:
        try:
            data = rom.get(arc)
        except Exception:
            continue
        tag = arc.split("/")[-1].replace(".bin", "")
        blocks = archive_blocks(data)
        imgs = []
        n = 0
        for i, blk in blocks:
            info = parse_ecd(blk)
            if not info:
                continue
            try:
                im = render(info)
            except Exception:
                continue
            name = f"{tag}_{i:05d}"
            im.save(os.path.join(OUT, "png", f"{name}.png"))
            imgs.append((f"{i}", im))
            partial = "" if info["got"] >= info["need"] else "PARTIAL"
            rows.append([name, f"{info['w']*8}x{info['h']*8}", f"{info['bpp']}bpp",
                         f"IMG{info['img_type']}", partial])
            n += 1; total += 1
            if n % 500 == 0:
                print(f"  {tag}: {n} images...", flush=True)
        contact_sheets(imgs, os.path.join(OUT, "contact", tag))
        print(f"{tag}: {n} ECD images dumped", flush=True)
    with open(os.path.join(OUT, "manifest.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["name", "dims", "bpp", "imgtype", "note"])
        w.writerows(rows)
    print(f"TOTAL: {total} images -> {OUT}/png , contact sheets -> {OUT}/contact")


if __name__ == "__main__":
    main()
