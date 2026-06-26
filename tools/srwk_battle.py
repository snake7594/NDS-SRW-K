# -*- coding: utf-8 -*-
"""srwk_battle.py — faithful port of the YameSoft SRWKBattleDESC tool's codec for
battle dialogue (data/add05dat.bin). DIFFERENT from the scenario codec:

  * NO embedded codebook/Font/idiom. Decode/encode use two STATIC external text
    tables shared by all entries: 일본어테이블.txt (decode key->char) and
    한글테이블.txt (encode char->key, first-match-by-value).
  * Flat file: top pointer table [0x0..0x350) = i32 LE slots. Entry N:
    FileStart=slot[N], FileEnd=slot[N+1] (N in 0..209, Point_Count=210).
  * Per-entry header @FileStart: 4 bytes meta, i16 PointerCount@+4,
    i16 DescStartOff@+6 -> DescStart=FileStart+off. Sub-pointer table stride 24
    (first i16 = sub-line offset rel DescStart, 22 bytes voice/face metadata).
  * Entry 0: +867 byte preamble after DescStart before the text stream.
  * Token stream (DescStart(+867)..FileEnd): leading speaker byte, then
    1-byte glyph (b in dict, 0x00-0x6F) / control 0x70-0x7F / 2-byte glyph
    (b>=0x80, b high, next low, NO swap).
    controls: 0x70 block break(+speaker, may be 0x70 0x71 sp), 0x71 line break
    (+speaker), 0x72 sub-line ';', 0x73 special(+speaker), 0x74-0x7F function.

Design mirrors srwk_native: lossless structured decode + byte-exact rebuild for
unchanged entries; edited entries re-encode the stream + recompute sub-pointers
and the top table (like the scenario section pointers)."""
import os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
TBL_DIR = os.path.join(HERE, "_analysis_zip", "SRWKBattleDESC_SRC", "SRWWDesc")
JP_TBL = os.path.join(TBL_DIR, "일본어테이블.txt")
KO_TBL = os.path.join(TBL_DIR, "한글테이블.txt")

POINT_START = 0x0
POINT_END = 0x350
POINT_COUNT = 210
MAX_LENGTH = 176


# --------------------------------------------------------------------------- #
#  static tables
# --------------------------------------------------------------------------- #
def _read_table(path):
    raw = open(path, "rb").read()
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-16-le"
    txt = raw.decode(enc, errors="replace")
    pairs = []  # (key, char) in file order, first key wins
    seen = set()
    for line in txt.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("/") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k in seen:
            continue
        seen.add(k)
        pairs.append((k, v))
    return pairs


class BattleTables:
    """Japan = original-JP decode (key->char); Korea = patched decode AND encode.
    The Korean font remaps the same 2-byte slots (0x88xx+) to hangul, so original
    JP data decodes via `japan`, while translated data decodes via `korea`."""
    def __init__(self):
        jp_pairs = _read_table(JP_TBL)
        ko_pairs = _read_table(KO_TBL)
        self.japan = {}          # key(upper hex) -> char   (original JP glyphs)
        for k, v in jp_pairs:
            self.japan.setdefault(k, v)
        self.korea = {}          # key(upper hex) -> char   (patched glyphs)
        for k, v in ko_pairs:
            self.korea.setdefault(k, v)
        # encode: char -> key (first occurrence in file order, like GetChar's scan)
        self.korea_char2key = {}
        for k, v in ko_pairs:
            self.korea_char2key.setdefault(v, k)
        self.jp_one_byte = {k for k in self.japan if len(k) == 2}
        self.ko_one_byte = {k for k in self.korea if len(k) == 2}

    def table(self, korea):
        return (self.korea, self.ko_one_byte) if korea else (self.japan, self.jp_one_byte)

    def enc_char(self, c):
        """char -> bytes (1 or 2). None if absent (GetChar returns null)."""
        k = self.korea_char2key.get(c)
        if k is None:
            return None
        if len(k) == 2:
            return bytes([int(k, 16)])
        return bytes([int(k[0:2], 16), int(k[2:4], 16)])


_TBL = None
def tables():
    global _TBL
    if _TBL is None:
        _TBL = BattleTables()
    return _TBL


# --------------------------------------------------------------------------- #
#  pointer set
# --------------------------------------------------------------------------- #
def _u16(b, o): return b[o] | (b[o + 1] << 8)
def _u32(b, o): return struct.unpack_from("<I", b, o)[0]


class Entry:
    """Decoded per-entry framing (PointerSet equivalent)."""
    def __init__(self, data, n):
        self.n = n
        pos = POINT_START + n * 4
        self.file_start = _u32(data, pos)
        self.file_end = _u32(data, pos + 4)
        self.pointer_count = _u16(data, self.file_start + 4)
        self.desc_start = self.file_start + _u16(data, self.file_start + 6)
        self.stream_start = self.desc_start + (867 if n == 0 else 0)


# --------------------------------------------------------------------------- #
#  lossless token decode
# --------------------------------------------------------------------------- #
# token kinds: 'sp'(speaker byte), 'g1'(1-byte glyph), 'g2'(2-byte glyph),
#              'c'(control 0x70/0x71/0x72/0x73), 'f'(function 0x74-0x7F)
def decode_tokens(data, stream_start, file_end, korea=False):
    """Decode [stream_start, file_end) into a lossless token list. Every byte is
    covered: b''.join(t['raw'] for t in toks) == data[stream_start:file_end].
    korea=True uses the patched (hangul) table for glyph rendering."""
    dec, one_byte = tables().table(korea)
    toks = []
    i = stream_start
    end = file_end
    # leading speaker byte (Extract reads one byte before the loop)
    if i < end:
        toks.append({"k": "sp", "raw": bytes(data[i:i + 1]), "b": data[i]})
        i += 1
    while i <= end - 1:
        b = data[i]
        if ("%02X" % b) in one_byte:
            toks.append({"k": "g1", "raw": bytes(data[i:i + 1]), "b": b,
                         "c": dec["%02X" % b]})
            i += 1
        elif 0x70 <= b < 0x80:
            if b == 0x72:
                toks.append({"k": "c", "raw": b"\x72", "b": 0x72})
                i += 1
            elif b in (0x70, 0x71, 0x73):
                # line/block control; consume the control + following speaker
                if b == 0x70:
                    # AppendLine x2 then read speaker. If the speaker byte would
                    # fall at/after FileEnd it belongs to the NEXT entry (the tool
                    # overshoots here) -> treat the trailing 0x70 as a bare
                    # terminator so our per-entry decode stays within bounds.
                    if i + 1 >= end:        # 0x70 is the entry's last byte
                        toks.append({"k": "c", "raw": b"\x70", "b": 0x70})
                        i += 1
                        continue
                    nb = data[i + 1]
                    if nb == 0x71:
                        # 0x70 0x71 [sp]
                        sp = data[i + 2] if i + 2 < end else None
                        if sp is None:
                            toks.append({"k": "c", "raw": bytes(data[i:i + 2]),
                                         "b": 0x70, "lead": "7071"})
                            i += 2
                        else:
                            toks.append({"k": "c", "raw": bytes(data[i:i + 3]),
                                         "b": 0x70, "lead": "7071", "sp": sp})
                            i += 3
                    else:
                        # 0x70 [sp]
                        toks.append({"k": "c", "raw": bytes(data[i:i + 2]),
                                     "b": 0x70, "lead": "70", "sp": nb})
                        i += 2
                else:
                    # 0x71 [sp] or 0x73 [sp]
                    sp = data[i + 1] if i + 1 < end else None
                    if sp is None:
                        toks.append({"k": "c", "raw": bytes(data[i:i + 1]),
                                     "b": b, "lead": "%02X" % b})
                        i += 1
                    else:
                        toks.append({"k": "c", "raw": bytes(data[i:i + 2]),
                                     "b": b, "lead": "%02X" % b, "sp": sp})
                        i += 2
            else:  # 0x74-0x7F function
                toks.append({"k": "f", "raw": bytes(data[i:i + 1]), "b": b})
                i += 1
        else:
            # 2-byte glyph: b high, next low (NO swap)
            b2 = data[i + 1] if i + 1 < end else 0
            toks.append({"k": "g2", "raw": bytes(data[i:i + 2]), "b1": b,
                         "b2": b2, "c": dec.get("%02X%02X" % (b, b2), "")})
            i += 2
    return toks


def tokens_raw(toks):
    return b"".join(tk["raw"] for tk in toks)


# --------------------------------------------------------------------------- #
#  voice-line grouping (the editable unit) + entry decode
# --------------------------------------------------------------------------- #
# A voice line = one battle quote: an optional lead control (b"", b"\x70",
# b"\x70\x71", b"\x71", b"\x73"), a speaker byte, and a body (glyph text split
# into sub-lines by 0x72, with 0x74-0x7F function bytes inline). The sub-pointer
# table records (k>=1) point at each voice line's SPEAKER offset (rel DescStart).
FUNC_LO, FUNC_HI = 0x74, 0x80


def _body_to_sublines(body_toks):
    """body tokens -> list of sub-line dicts {text, parts} where parts keeps the
    lossless token sequence (glyph chars + ('f',byte)) and text is the readable
    string (functions shown as 'Ｆ'+chr(byte), matching the tool's escape)."""
    sublines = []
    cur = []
    for tk in body_toks:
        if tk["k"] == "c" and tk["b"] == 0x72:
            sublines.append(cur); cur = []
        else:
            cur.append(tk)
    sublines.append(cur)
    return sublines


def decode_entry(data, n, korea=False):
    e = Entry(data, n)
    toks = decode_tokens(data, e.stream_start, e.file_end, korea=korea)
    header = bytes(data[e.file_start:e.desc_start])
    preamble = bytes(data[e.desc_start:e.stream_start])   # 867 for entry 0 else b""
    # group tokens into voice lines
    vlines = []
    pos = e.stream_start
    # first token = leading speaker
    cur = None
    idx = 0
    while idx < len(toks):
        tk = toks[idx]
        if idx == 0 and tk["k"] == "sp":
            cur = {"lead": b"", "sp": tk["b"],
                   "sp_off": pos - e.desc_start, "body": []}
            pos += len(tk["raw"]); idx += 1
            continue
        if tk["k"] == "c" and tk["b"] in (0x70, 0x71, 0x73):
            vlines.append(cur)
            raw = tk["raw"]
            sp = tk.get("sp")
            if sp is None:
                lead = raw                       # bare terminal control
                sp_off = None
            else:
                lead = raw[:-1]                  # control bytes minus speaker
                sp_off = (pos + len(raw) - 1) - e.desc_start
            cur = {"lead": lead, "sp": sp, "sp_off": sp_off, "body": []}
            pos += len(raw); idx += 1
            continue
        cur["body"].append(tk)
        pos += len(tk["raw"]); idx += 1
    if cur is not None:
        vlines.append(cur)
    # attach sub-lines + raw bytes per voice line
    for v in vlines:
        v["sublines"] = _body_to_sublines(v["body"])
        body_raw = b"".join(tk["raw"] for tk in v["body"])
        v["raw"] = v["lead"] + (bytes([v["sp"]]) if v["sp"] is not None else b"") + body_raw
    # Each voice line has an ANCHOR offset the sub-pointer table records: it is
    # the byte right AFTER the first control byte (speaker for 1-byte leads "70"/
    # "71"/"73"; the 0x71 byte for the 2-byte lead "7071"), or the speaker itself
    # for the first voice line (no lead). anchor = sp_off - len(lead) + 1, or
    # sp_off when lead is empty.
    for v in vlines:
        if v["sp_off"] is None:
            v["anchor"] = None
        elif v["lead"] == b"":
            v["anchor"] = v["sp_off"]
        else:
            v["anchor"] = v["sp_off"] - len(v["lead"]) + 1
    # map sub-pointer records (k>=1) to voice lines by matching original i16 ->
    # anchor. Record 0 = DescStartOff (skip). Unmatched records (entry-0 preamble
    # slots) are preserved verbatim.
    anchor2vi = {}
    for vi, v in enumerate(vlines):
        if v["anchor"] is not None and v["anchor"] not in anchor2vi:
            anchor2vi[v["anchor"]] = vi
    subptr_map = {}
    for k in range(1, e.pointer_count):
        val = struct.unpack_from("<h", header, 24 * k + 6)[0]
        if val in anchor2vi:
            subptr_map[k] = anchor2vi[val]
    e.header = header
    e.preamble = preamble
    e.vlines = vlines
    e.subptr_map = subptr_map
    return e


def render_subline(subtoks):
    """token list of one sub-line -> readable string ('Ｆ'+chr escape for funcs)."""
    out = []
    for tk in subtoks:
        if tk["k"] == "f":
            out.append("Ｆ" + chr(tk["b"]))
        elif tk["k"] in ("g1", "g2"):
            out.append(tk["c"])
        else:
            out.append("")
    return "".join(out)


def voiceline_text(v):
    """full readable text of a voice line: sub-lines joined by ';'."""
    return ";".join(render_subline(s) for s in v["sublines"])


# --------------------------------------------------------------------------- #
#  encode
# --------------------------------------------------------------------------- #
class BattleOverflow(Exception):
    """An edited entry grew until a sub-pointer offset exceeded signed int16.
    The whole entry is too large to ship; shorten its voice lines."""
    def __init__(self, n, vi, off):
        self.n, self.vi, self.off = n, vi, off
        super().__init__(f"entry {n} voice line {vi}: sub-pointer offset {off} "
                         f"exceeds signed int16 (32767) — shorten this entry")


def _encode_text(text):
    """readable voice-line text -> body bytes (sub-lines joined by 0x72).
    'Ｆ'+c escape writes c's low byte; other chars via the Korea table.
    Raises KeyError(c) if a char has no encode key. Applies Max_Length truncation
    (desc[:10]) per sub-line exactly like the tool."""
    t = tables()
    out = bytearray()
    # mirror C# Split(';', RemoveEmptyEntries): drop empty sub-lines so a stray
    # or doubled ';' never emits an extra 0x72 break the tool wouldn't.
    sublines = [s for s in text.split(";") if s.strip()]
    for si, sub in enumerate(sublines):
        sub = sub.strip()
        if get_byte_count(sub) > MAX_LENGTH:
            sub = sub[:10]
        func = False
        for c in sub:
            if func:
                out.append(ord(c) & 0xFF)
                func = False
                continue
            if c == "Ｆ":
                func = True
                continue
            enc = t.enc_char(c)
            if enc is None:
                raise KeyError(c)
            out += enc
        if si != len(sublines) - 1:
            out.append(0x72)
    return bytes(out)


def get_byte_count(s):
    return sum(12 if ("가" <= c <= "힣") else 8 for c in s)


# full-width / unsupported punctuation -> battle-table forms (half-width)
_BAT_MAP = {
    "！": "!", "？": "?", "，": ",", "、": ",", "　": " ", "．": ".",
    "‥": "…", "—": "-", "―": "-", "–": "-", "～": "-", "~": "-", "〜": "-",
    "・": "·", "“": "", "”": "", "\"": "", "「": "", "」": "", "『": "", "』": "",
    "­": "", "​": "",
}


def _nearest_hangul_bat(c):
    o = ord(c)
    if not (0xAC00 <= o <= 0xD7A3):
        return None
    s = o - 0xAC00
    cand = chr(0xAC00 + (s // 28) * 28)        # drop final jamo
    return cand if tables().enc_char(cand) is not None else None


def sanitize_ko_battle(text):
    """Make a Korean battle line encodable by the battle table: map full-width /
    unsupported punctuation to half-width forms, approximate syllables outside the
    table, drop the rest. ';' (sub-line separator) and 'Ｆ' (function escape) pass
    through untouched. Returns (clean, substitutions)."""
    t = tables()
    out, subs = [], []
    for c in text:
        if c in (";", "Ｆ") or t.enc_char(c) is not None:
            out.append(c)
            continue
        r = _BAT_MAP.get(c)
        if r is None:
            r = _nearest_hangul_bat(c)
        if r is None:
            r = ""
        if r and all(t.enc_char(x) is not None for x in r):
            out.append(r)
        subs.append((c, r))
    return "".join(out), subs


def wrap_battle(text, limit=MAX_LENGTH):
    """Keep every ';'-separated sub-line within `limit` width, splitting long ones
    at spaces (extra sub-lines) so the game never truncates a >176 line to 10 chars."""
    pieces = []
    for sub in text.split(";"):
        if get_byte_count(sub) <= limit:
            pieces.append(sub)
            continue
        cur = ""
        for word in sub.split(" "):
            cand = (cur + " " + word) if cur else word
            if get_byte_count(cand) <= limit:
                cur = cand
                continue
            if cur:
                pieces.append(cur)
                cur = ""
            while get_byte_count(word) > limit:
                take = ""
                for ch in word:
                    if get_byte_count(take + ch) > limit:
                        break
                    take += ch
                pieces.append(take)
                word = word[len(take):]
            cur = word
        if cur:
            pieces.append(cur)
    return ";".join(pieces)


def encode_voiceline(v, new_text=None):
    """bytes for a voice line. Reuses original bytes when text is unchanged
    (byte-exact); re-encodes the body via the Korea table when edited."""
    if new_text is None or new_text == voiceline_text(v):
        return v["raw"]
    body = _encode_text(new_text)
    return v["lead"] + (bytes([v["sp"]]) if v["sp"] is not None else b"") + body


def encode_entry(e, new_texts=None):
    """Reassemble one entry's bytes. new_texts (optional) = list aligned to
    e.vlines; None entries reuse the original. Recomputes the sub-pointer table
    speaker offsets (records 1..PointerCount-1) for the new layout."""
    header = bytearray(e.header)
    pre_len = len(e.preamble)                      # 0, or 867 for entry 0
    stream = bytearray()
    new_anchor = []                                # per voice line, rel DescStart
    for i, v in enumerate(e.vlines):
        nt = new_texts[i] if (new_texts and i < len(new_texts)) else None
        line_start = pre_len + len(stream)         # = lead start, rel DescStart
        if v["sp"] is None:
            anchor = None
        elif v["lead"] == b"":
            anchor = line_start                    # first voice line: speaker pos
        else:
            anchor = line_start + 1                # byte after first control byte
        new_anchor.append(anchor)
        stream += encode_voiceline(v, nt)
    # rewrite only the sub-pointer records that originally mapped to a voice line
    for k, vi in e.subptr_map.items():
        a = new_anchor[vi]
        if a is None:
            continue
        if not (-32768 <= a <= 32767):
            # the sub-pointer is a signed int16 offset from DescStart; a value
            # past 32767 cannot be stored (C# would silently wrap to a negative
            # offset -> in-game corruption). Surface it instead of crashing.
            raise BattleOverflow(e.n, vi, a)
        struct.pack_into("<h", header, 24 * k + 6, a)
    return bytes(header) + e.preamble + bytes(stream)


def rebuild_file(data, edits=None):
    """Rebuild add05dat.bin. edits = {entry_index: [text_or_None per voice line]}.
    Unedited entries are byte-identical. Recomputes the 212-slot top pointer
    table and preserves the trailing region."""
    edits = edits or {}
    # trailing region geometry from the original table
    slot210 = _u32(data, POINT_START + 210 * 4)
    slot211 = _u32(data, POINT_START + 211 * 4)
    trailing = data[slot210:]
    tail_internal = slot211 - slot210
    # encode every entry; an entry whose edits overflow the i16 sub-pointer is
    # reported and falls back to its original bytes so the rest still builds.
    entry_bytes = []
    oversized = []
    for n in range(POINT_COUNT):
        e = decode_entry(data, n)
        try:
            entry_bytes.append(encode_entry(e, edits.get(n)))
        except BattleOverflow as ex:
            oversized.append((n, ex.vi, ex.off))
            entry_bytes.append(encode_entry(e, None))   # keep original bytes
    rebuild_file.last_oversized = oversized
    # lay out: pointer table (212 slots) then entries then trailing
    table_size = POINT_END                          # 0x350 = 212*4
    slots = [0] * 212
    cur = table_size
    for n in range(POINT_COUNT):
        slots[n] = cur
        cur += len(entry_bytes[n])
    slots[210] = cur                                # start of trailing
    slots[211] = cur + tail_internal
    out = bytearray(struct.pack("<212i", *slots))
    for eb in entry_bytes:
        out += eb
    out += trailing
    return bytes(out)


