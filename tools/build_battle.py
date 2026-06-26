# -*- coding: utf-8 -*-
"""build_battle.py — rebuild data/add05dat.bin from srwk_battle.json.

Unchanged voice lines (ko == jp) stay byte-identical; translated lines are
re-encoded via the hangul table, the per-entry sub-pointer speaker offsets are
recomputed, and the top 212-slot pointer table is rebuilt. Reports overflow
(>176 width) and any chars missing from the encode table.

  python build_battle.py           # JSON -> build/data/add05dat.bin
  python build_battle.py --check   # no-edit regression gate (== original)
"""
import json, os, sys
from srwk_battle import (decode_entry, encode_entry, rebuild_file, tables,
                         voiceline_text, get_byte_count, MAX_LENGTH, POINT_COUNT,
                         sanitize_ko_battle, wrap_battle)

HERE = os.path.dirname(os.path.abspath(__file__))
JP_BIN = os.path.join(HERE, "jp", "data", "add05dat.bin")
KR_BIN = os.path.join(HERE, "kr", "data", "add05dat.bin")
JSONF = os.path.join(HERE, "srwk_battle.json")
OUTDIR = os.path.join(HERE, "build", "data")
OUT_BIN = os.path.join(OUTDIR, "add05dat.bin")


def _base_path():
    return KR_BIN if os.path.exists(KR_BIN) else JP_BIN


def _missing_chars(text):
    t = tables()
    miss = []
    func = False
    for sub in text.split(";"):
        for c in sub.strip():
            if func:
                func = False
                continue
            if c == "Ｆ":
                func = True
                continue
            if t.enc_char(c) is None:
                miss.append(c)
    return miss


def build(json_path=JSONF, base_path=None):
    base_path = base_path or _base_path()
    data = open(base_path, "rb").read()
    doc = json.load(open(json_path, encoding="utf-8"))["entries"]
    edits = {}
    changed = 0
    overflow = []     # (n, vl, width, subline)
    missing = []      # (n, vl, chars, text)
    for n in range(POINT_COUNT):
        e = decode_entry(data, n, korea=False)
        ent = doc.get(str(n))
        if not ent:
            continue
        kos = [vl.get("ko", "") for vl in ent["vlines"]]
        jps = [voiceline_text(v) for v in e.vlines]
        texts = []
        any_change = False
        for i, v in enumerate(e.vlines):
            ko = kos[i] if i < len(kos) else None
            if ko is None or ko == jps[i]:
                texts.append(None)            # unchanged -> reuse original bytes
                continue
            ko, _sb = sanitize_ko_battle(ko)  # punctuation/syllable fixups
            ko = wrap_battle(ko, MAX_LENGTH)  # keep each sub-line <= 176 wide
            miss = _missing_chars(ko)
            if miss:
                # still un-encodable -> keep original bytes, report
                missing.append((n, i, "".join(sorted(set(miss))), ko))
                texts.append(None)
                continue
            any_change = True
            texts.append(ko)
        if any_change:
            edits[n] = texts
            changed += 1
    out = rebuild_file(data, edits)
    oversized = getattr(rebuild_file, "last_oversized", [])
    return out, {"changed_entries": changed, "overflow": overflow,
                 "missing": missing, "oversized": oversized,
                 "identical": out == data}


def main(check=False):
    out, st = build()
    if check:
        print(f"changed entries={st['changed_entries']}")
        print(f"NO-EDIT REGRESSION GATE: rebuilt == original -> {st['identical']}")
        return st["identical"]
    if st.get("oversized"):
        print(f"!! {len(st['oversized'])} entry(ies) too large after translation "
              f"(sub-pointer > int16 32767) — kept ORIGINAL, shorten these lines:")
        for n, vi, off in st["oversized"][:20]:
            print(f"   entry {n}: offset {off} at/after voice line {vi}")
    if st["missing"]:
        print(f"!! {len(st['missing'])} voice line(s) have chars not in the "
              f"encode table — FIX before shipping:")
        for n, i, chars, text in st["missing"][:20]:
            print(f"   entry {n} vl {i}: missing [{chars}]  in: {text}")
    if st["overflow"]:
        print(f"!! {len(st['overflow'])} sub-line(s) exceed width {MAX_LENGTH} "
              f"(will truncate to 10 chars in-game):")
        for n, i, w, sub in st["overflow"][:20]:
            print(f"   entry {n} vl {i} width={w}: {sub}")
    os.makedirs(OUTDIR, exist_ok=True)
    with open(OUT_BIN, "wb") as f:
        f.write(out)
    print(f"wrote {OUT_BIN} ({len(out)} bytes)")
    print(f"changed entries={st['changed_entries']}  "
          f"overflow={len(st['overflow'])}  missing-char lines={len(st['missing'])}")


if __name__ == "__main__":
    main(check="--check" in sys.argv)
