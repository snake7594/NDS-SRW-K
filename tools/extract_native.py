# -*- coding: utf-8 -*-
"""extract_native.py — BOOTSTRAP only. Produce the per-box editing JSON from the
original KR/JP add03 binaries using the faithful codec port (srwk_native).

Output structure (edit-friendly, paired per dialogue box):
  scenarios[bi] = {
    codebook_block, translated, box_count,
    boxes: [ {jp:[...일본어 원문...], ko:[...한국어 번역...], c1, c2, name?, sec?}, ... ]
  }
Each box = one on-screen text page. 'jp' is reference; edit only 'ko'. A box with
jp == [] is a split continuation of the previous box (its source is the box above).

WARNING: this re-derives everything from the ORIGINAL binaries, which contain only
the YameSoft ch1-24 Korean (no ch25-46 translation, no later fixes). Running it will
DESTROY the translated srwk_scenario_clean.json. It refuses to overwrite an existing
output and writes to *.bootstrap.json instead. Edit srwk_scenario_clean.json directly."""
import json, os, difflib
from srwk_codec import Add03
from srwk_native import decode_block_native

HERE = os.path.dirname(os.path.abspath(__file__))
JP = os.path.join(HERE, "jp", "data", "add03dat.bin")
KR = os.path.join(HERE, "kr", "data", "add03dat.bin")
OUT = os.path.join(HERE, "srwk_scenario_clean.json")
SCN_FIRST, SCN_LAST, CB_OFFSET = 130, 194, 65


def _key(n):
    return (n["code1"], n["code2"], n.get("name", ""))


def align_jp(jp_nodes, ko_nodes):
    """jp-line-list aligned to each ko box (difflib on (c1,c2,name) keys)."""
    jp_for_ko = [[] for _ in ko_nodes]
    if not jp_nodes:
        return jp_for_ko
    sm = difflib.SequenceMatcher(None, [_key(n) for n in jp_nodes],
                                 [_key(n) for n in ko_nodes], autojunk=False)
    pending = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                jp_for_ko[j1 + k] = list(jp_nodes[i1 + k]["lines"])
            if pending:
                jp_for_ko[j1] = pending + jp_for_ko[j1]; pending = []
        elif tag == "replace":
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                jp_for_ko[j1 + k] = list(jp_nodes[i1 + k]["lines"])
            for k in range(n, i2 - i1):
                pending += list(jp_nodes[i1 + k]["lines"])
            if pending and j2 > j1 + n:
                jp_for_ko[j1 + n] = pending + jp_for_ko[j1 + n]; pending = []
        elif tag == "delete":
            for k in range(i1, i2):
                pending += list(jp_nodes[k]["lines"])
        # 'insert' = extra ko boxes (split continuation) -> jp stays []
    if pending and ko_nodes:
        jp_for_ko[-1] = jp_for_ko[-1] + pending
    return jp_for_ko


def make_boxes(jp_nodes, ko_nodes):
    jpf = align_jp(jp_nodes, ko_nodes)
    boxes = []
    for j, nd in enumerate(ko_nodes):
        box = {"jp": jpf[j], "ko": nd["lines"],
               "c1": f"{nd['code1']:04X}", "c2": f"{nd['code2']:04X}"}
        if nd.get("name"):
            box["name"] = nd["name"]
        if nd.get("sec"):
            box["sec"] = 1
        boxes.append(box)
    return boxes


def main():
    out_path = OUT
    if os.path.exists(OUT):
        out_path = OUT.replace(".json", ".bootstrap.json")
        print(f"WARNING: {OUT} exists; refusing to overwrite translated file.")
        print(f"         writing fresh bootstrap to {out_path} instead.")
    jp = Add03(open(JP, "rb").read())
    kr = Add03(open(KR, "rb").read())
    scenarios = {}
    for bi in range(SCN_FIRST, SCN_LAST + 1):
        cbb = bi + CB_OFFSET
        translated = jp.blocks[bi] != kr.blocks[bi]
        jp_nodes = decode_block_native(jp.blocks[bi], jp.blocks[cbb], hangul=False)
        ko_nodes = decode_block_native(kr.blocks[bi], kr.blocks[cbb], hangul=True) \
            if translated else jp_nodes
        scenarios[str(bi)] = {
            "codebook_block": cbb,
            "translated": translated,
            "box_count": len(ko_nodes),
            "boxes": make_boxes(jp_nodes, ko_nodes),
        }
    doc = {
        "_about": (
            "SRW K 시나리오 — 대사 박스 단위 편집용. 각 블록 'boxes'의 각 항목 = 화면 대사 한 칸: "
            "'jp'(일본어 원문, 참조) → 'ko'(한국어 번역, 이것만 수정). c1=화자/초상화, c2=플래그, "
            "name=이름오버라이드, sec=섹션시작 — 모두 유지(빌드용). jp가 빈 칸([])은 앞 칸에서 이어진 "
            "분할 박스. ①②③ 등 동그라미 숫자는 게임이 이름으로 치환하는 자리표시자 — 번역/삭제 금지. "
            "줄당 최대 176폭(한글 12/그외 8). 빌드: build_native.py → add03dat.bin → build_rom_all.py."),
        "scenarios": scenarios,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    nt = sum(1 for b in scenarios.values() if b["translated"])
    print(f"wrote {out_path}")
    print(f"blocks: {len(scenarios)} (translated {nt})")
    print(f"total boxes: {sum(b['box_count'] for b in scenarios.values())}")


if __name__ == "__main__":
    main()
