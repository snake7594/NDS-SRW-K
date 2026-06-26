# -*- coding: utf-8 -*-
"""build_native.py — rebuild data/add03dat.bin from srwk_scenario_clean.json
using the faithful native encoder (srwk_native).

Per scenario block:
  * if the JSON 'ko' is unchanged from what is currently in the KR ROM, the block
    and its codebook are left byte-for-byte identical (regression-safe);
  * if 'ko' was edited / translated, the codebook is regenerated from the new
    text (InsertMap) and the nodes are re-encoded (OnInsertDesc), with section
    pointers rebuilt and a per-sub-line overflow check (Max_Length=176).

No-edit rebuild == the original KR add03dat.bin (verified by --check)."""
import json, os, sys
from srwk_codec import Add03
from srwk_native import (decode_block_native, encode_block_native,
                         build_charlist, regen_codebook, get_byte_count, MAX_LENGTH,
                         sanitize_ko, wrap_sublines)

HERE = os.path.dirname(os.path.abspath(__file__))
KR_BIN = os.path.join(HERE, "kr", "data", "add03dat.bin")
JSONF = os.path.join(HERE, "srwk_scenario_clean.json")
OUTDIR = os.path.join(HERE, "build", "data")
OUT_BIN = os.path.join(OUTDIR, "add03dat.bin")
SCN_FIRST, SCN_LAST, CB_OFFSET = 130, 194, 65


def _ji(v):
    return int(v, 16) if isinstance(v, str) else v


def nodes_equal(json_ko, dec_nodes):
    """text-level equality between JSON 'ko' and a freshly decoded node list."""
    if len(json_ko) != len(dec_nodes):
        return False
    for j, d in zip(json_ko, dec_nodes):
        if _ji(j["c1"]) != d["code1"] or _ji(j["c2"]) != d["code2"]:
            return False
        if j.get("name", "") != d["name"] or j["lines"] != d["lines"]:
            return False
    return True


MAX_LINES = 3   # the on-screen dialogue box shows at most 3 lines (verified: the
#               shipped KR/JP scenario never has a node with >3 sub-lines)


def reflow(lines, limit=MAX_LENGTH):
    """Re-flow a box's text into the FEWEST lines that each fit `limit` width,
    greedily packing at full-width-space word boundaries (hard-split a single word
    that still overflows). Unlike wrap_sublines this MERGES across the original
    breaks, so a box whose line 1 was too wide is re-balanced instead of just
    gaining a 4th line."""
    words = []
    for ln in lines:
        for w in ln.split("　"):
            if w:
                words.append(w)
    out, cur = [], ""
    for w in words:
        piece = (cur + "　" + w) if cur else w
        if get_byte_count(piece) <= limit:
            cur = piece
            continue
        if cur:
            out.append(cur)
            cur = ""
        while get_byte_count(w) > limit:
            take = ""
            for ch in w:
                if get_byte_count(take + ch) > limit:
                    break
                take += ch
            out.append(take)
            w = w[len(take):]
        cur = w
    if cur:
        out.append(cur)
    return out


def chunk_balanced(lines, maxlines=MAX_LINES):
    """Split a too-tall line list into balanced groups of <= maxlines (e.g. a
    4-line flow -> 2+2, a 5-line flow -> 3+2), so no continuation box is a lone
    1-liner."""
    n = len(lines)
    if n <= maxlines:
        return [lines]
    nchunks = (n + maxlines - 1) // maxlines
    base, extra = divmod(n, nchunks)
    chunks, i = [], 0
    for k in range(nchunks):
        sz = base + (1 if k < extra else 0)
        chunks.append(lines[i:i + sz])
        i += sz
    return chunks


def json_to_nodes(json_ko, subs=None, splits=None):
    # sanitise each sub-line so it is encodable by the 2-byte-SJIS / 2350-syllable
    # codec (full-width ASCII, punctuation map, approximate rare syllables)
    nodes = []
    for j in json_ko:
        clean = []
        for s in j["lines"]:
            c, sb = sanitize_ko(s)
            clean.append(c)
            if subs is not None:
                subs.extend(sb)
        # already fits the box (<=3 lines, each <=176)?  keep the translator's
        # line breaks; otherwise re-flow into the fewest <=176 lines and, if that
        # is still > MAX_LINES, split into balanced <=3-line continuation boxes
        # (same speaker/name; only the FIRST keeps the original c2/event + sec).
        if len(clean) <= MAX_LINES and all(get_byte_count(l) <= MAX_LENGTH for l in clean):
            groups = [clean]
        else:
            groups = chunk_balanced(reflow(clean, MAX_LENGTH), MAX_LINES)
            if len(groups) > 1 and splits is not None:
                splits.append((j, len(groups)))
        for gi, g in enumerate(groups):
            nodes.append({"c1": j["c1"],
                          "c2": j["c2"] if gi == 0 else "0000",
                          "name": j.get("name", ""),
                          "lines": g,
                          "sec": bool(j.get("sec")) if gi == 0 else False})
    return nodes


def build(json_path=JSONF, kr_add03_path=KR_BIN):
    """Rebuild add03dat.bin bytes from the clean JSON. Returns
    (add03_bytes, stats) where stats = {reused, changed, overflow:[(bi,w,line)]}.
    Unchanged blocks are kept byte-for-byte; edited/translated blocks regenerate
    their codebook and re-encode (with a decode-back self-check)."""
    kr = Add03(open(kr_add03_path, "rb").read())
    orig_bytes = kr.data
    doc = json.load(open(json_path, encoding="utf-8"))["scenarios"]
    reused = changed = 0
    overflow = []
    subs = []
    splits = []
    toolong = []
    for bi in range(SCN_FIRST, SCN_LAST + 1):
        cbb = bi + CB_OFFSET
        entry = doc[str(bi)]
        # new per-box format: scenarios[bi]["boxes"] = [{jp,ko,c1,c2,name?,sec?}].
        # convert to the legacy json-ko node form (lines = the Korean 'ko') so the
        # rest of the pipeline (nodes_equal / json_to_nodes) stays unchanged.
        json_ko = [{"c1": b["c1"], "c2": b["c2"], "name": b.get("name", ""),
                    "lines": b["ko"], "sec": b.get("sec")}
                   for b in entry["boxes"]]
        orig_nodes = decode_block_native(kr.blocks[bi], kr.blocks[cbb],
                                         hangul=entry["translated"])
        if nodes_equal(json_ko, orig_nodes):
            reused += 1
            continue
        changed += 1
        nodes = json_to_nodes(json_ko, subs, splits)
        for nd in nodes:
            if len(nd["lines"]) > 3:
                toolong.append((bi, len(nd["lines"]), nd["lines"]))
            for ln in nd["lines"]:
                w = get_byte_count(ln)
                if w > MAX_LENGTH:
                    overflow.append((bi, w, ln))
        texts = [ln for nd in nodes for ln in nd["lines"]]
        charlist = build_charlist(texts, hangul=True)
        new_cb = regen_codebook(kr.blocks[cbb], charlist, hangul=True)
        new_block = encode_block_native(nodes, new_cb, hangul=True,
                                        charlist=charlist)
        back = decode_block_native(new_block, new_cb, hangul=True)
        if not nodes_equal(nodes, back):     # compare the normalised nodes
            raise RuntimeError(f"block {bi}: re-encode did not round-trip")
        kr.blocks[bi] = new_block
        kr.blocks[cbb] = new_cb
    out = kr.rebuild()
    return out, {"reused": reused, "changed": changed, "overflow": overflow,
                 "subs": subs, "splits": splits, "toolong": toolong,
                 "identical_to_orig": out == orig_bytes}


def main(check=False):
    out, st = build()
    if check:
        print(f"blocks reused(byte-identical)={st['reused']} changed={st['changed']}")
        print(f"NO-EDIT REGRESSION GATE: rebuilt == original KR  -> "
              f"{st['identical_to_orig']}")
        if st["overflow"]:
            print(f"OVERFLOW sub-lines (>{MAX_LENGTH}): {len(st['overflow'])}")
            for bi, w, ln in st["overflow"][:10]:
                print(f"  block {bi} width={w}: {ln}")
        return st["identical_to_orig"]
    os.makedirs(OUTDIR, exist_ok=True)
    with open(OUT_BIN, "wb") as f:
        f.write(out)
    print(f"wrote {OUT_BIN} ({len(out)} bytes)")
    print(f"blocks reused={st['reused']} re-encoded={st['changed']}")
    print(f"over-long boxes split into continuation boxes: {len(st['splits'])}")
    print(f"nodes still >3 lines after fix: {len(st['toolong'])}")
    if st["toolong"]:
        for bi, n, lines in st["toolong"][:10]:
            print(f"   !! block {bi}: {n} lines: {lines}")
    if st["overflow"]:
        print(f"!! {len(st['overflow'])} sub-line(s) exceed Max_Length={MAX_LENGTH}:")
        for bi, w, ln in st["overflow"][:20]:
            print(f"   block {bi} width={w}: {ln}")
    else:
        print("overflow check: all sub-lines within limit")


if __name__ == "__main__":
    main(check="--check" in sys.argv)
