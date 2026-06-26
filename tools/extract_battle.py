# -*- coding: utf-8 -*-
"""extract_battle.py — dump battle dialogue (data/add05dat.bin) to an editable
JSON (srwk_battle.json). Each entry = a list of voice lines (battle quotes).

Edit only the 'ko' field of each voice line. 'ko' starts equal to 'jp' (the
Japanese is untranslated); leaving it unchanged keeps that line byte-identical,
replacing it with Korean re-encodes it via the hangul table on build.

Constraints (build_battle.py enforces/reports):
  * per sub-line width <= 176 (Korean=12 / other=8); the tool TRUNCATES to the
    first 10 chars on overflow, so keep lines short.
  * every char must exist in 한글테이블.txt (build reports missing chars). Use the
    table's punctuation forms: '!'(not '！'), ' '(half-width, not '　'),
    '…','。','·' are present; '？','，','、' are NOT.
  * structure (speaker code 'sp', control layout) is fixed — don't add/remove
    voice lines or sub-lines ';' unless you know the per-entry pointer count."""
import json, os
from srwk_battle import decode_entry, voiceline_text, POINT_COUNT

HERE = os.path.dirname(os.path.abspath(__file__))
JP = os.path.join(HERE, "jp", "data", "add05dat.bin")
KR = os.path.join(HERE, "kr", "data", "add05dat.bin")
OUT = os.path.join(HERE, "srwk_battle.json")


def main():
    data = open(KR if os.path.exists(KR) else JP, "rb").read()
    entries = {}
    total_vl = 0
    for n in range(POINT_COUNT):
        e = decode_entry(data, n, korea=False)   # original = Japanese
        vls = []
        for v in e.vlines:
            jp = voiceline_text(v)
            vls.append({"sp": v["sp"], "jp": jp, "ko": jp})
            total_vl += 1
        entries[str(n)] = {"n": n, "vlines": vls}
    doc = {
        "_about": (
            "SRW K 전투대사(add05dat.bin). 각 엔트리=전투 보이스라인 목록. "
            "'ko'만 편집(처음엔 jp와 동일=미번역). ko를 한국어로 바꾸면 빌드 시 "
            "한글 테이블로 재인코딩, 그대로 두면 원본 바이트 유지. "
            "줄당 폭<=176(한글12/그외8; 초과시 앞10자로 잘림). "
            "표는 반각 '!' ' ' '…' '。' '·' 사용(전각 '！？　，、' 없음). "
            "sp(화자코드)와 보이스라인/서브라인(;) 구조는 그대로 유지."
        ),
        "entries": entries,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"wrote {OUT}")
    print(f"entries: {len(entries)}  voice lines: {total_vl}")


if __name__ == "__main__":
    main()
