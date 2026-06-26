# -*- coding: utf-8 -*-
"""srwk_native.py — faithful port of the original YameSoft SRWKDesc tool's
scenario-dialogue codec (from the supplied C# source: DescriptionBase.cs +
SRWKDesc/Description.cs + MainForm.PointerSet).

Decodes data/add03dat.bin scenario blocks EXACTLY like the tool:
  * codebook (Font) layout: T=cb[0x11], FontStart=Int32@0x14, IdiomStart=Int32@0x18,
    IdiomParam(pairs)=0x20.., FontEnd=Int32@0x2C, Map=cb[FontStart:FontEnd+2]
  * char  : value -> code; if code>=IdiomStart -> idiom; else Map[code] = SJIS code
  * idiom : pairs (cumfreq,offset) from 0x20; bucket `count` where K[c]<=V<K[c+1];
            entry @ off[K[c+1]] + (V-K[c])*(c+3), read c+3 bytes as chars
  * node  : [code1:Int16][code2:Int16] (opt changeName) then length-prefixed
            sub-lines: len byte, len%0x80 bytes; len>0x80 = last sub-line
"""
import struct

def _u16(b, o): return b[o] | (b[o+1] << 8)
def _i32(b, o): return struct.unpack_from("<i", b, o)[0]

# ---- char tables (Map gives SJIS codes; decode via cp932 / KSC hangul) ----
from srwk_codec import build_ksc_maps
_CODE2HAN, _ = build_ksc_maps()

def _sjis_char(code, hangul):
    if hangul and code in _CODE2HAN:
        return _CODE2HAN[code]
    try:
        return bytes([code >> 8, code & 0xFF]).decode("cp932")
    except Exception:
        return None

class Codebook:
    """Parse a Font/codebook block exactly like MainForm.PointerSet."""
    def __init__(self, cb, hangul):
        self.cb = cb
        self.hangul = hangul
        self.T = cb[0x11]
        self.FontStart = _i32(cb, 0x14)
        self.IdiomStart = _i32(cb, 0x18)
        self.IdiomParam = 0x20
        self.FontEnd = _i32(cb, 0x2C)
        self.Map = cb[self.FontStart: self.FontEnd + 2]
        # idiom pairs (cumfreq -> offset), sorted, first-key-wins
        pairs = {}
        o = self.IdiomParam
        while o + 8 <= len(cb) and o < self.FontStart:
            key = _i32(cb, o); val = _i32(cb, o + 4); o += 8
            if key not in pairs:
                pairs[key] = val
        self.keys = sorted(pairs)
        self.pairs = pairs

    def map_index(self, value):
        """value=(b0,b1). returns (kind, data): ('char', sjis) or ('idiom', V)."""
        code = _u16(bytes(value), 0)              # raw little-endian Int16
        if code >= self.IdiomStart:
            return ("idiom", code)
        if value[1] != 0:
            code = (value[1] - self.T + 1) * 256 + value[0] - (256 - self.T)
        # Map[code*2] high, +1 low (big-endian SJIS)
        try:
            sjis = (self.Map[code * 2] << 8) | self.Map[code * 2 + 1]
        except IndexError:
            return ("char", None)
        return ("char", sjis)

    def get_char(self, value):
        kind, data = self.map_index(value)
        if kind == "idiom":
            return self.get_idiom(data)
        return _sjis_char(data, self.hangul) if data is not None else f"<{data}>"

    def get_idiom(self, code):
        keys = self.keys
        for c in range(len(keys) - 1):
            if keys[c] <= code < keys[c + 1]:
                pos = self.pairs[keys[c + 1]] + (code - keys[c]) * (c + 3)
                width = c + 3
                out = []
                i = 0
                while i < width:
                    b = self.cb[pos]; pos += 1
                    if b >= self.T:
                        out.append(self.get_char((self.cb[pos], b))); pos += 1; i += 1
                    else:
                        out.append(self.get_char((b, 0)))
                    i += 1
                return "".join(out)
        return f"<D{code:X}>"

    # -------- encoder side (reverse Map) --------
    def _ensure_reverse(self):
        if hasattr(self, "_rev"):
            return
        self._rev = {}
        n_chars = (self.IdiomStart_index())
        for idx in range(n_chars):
            try:
                sjis = (self.Map[idx * 2] << 8) | self.Map[idx * 2 + 1]
            except IndexError:
                break
            if sjis not in self._rev:
                self._rev[sjis] = idx

    def IdiomStart_index(self):
        # charlist length = number of SJIS entries before the idiom region
        return (self.FontEnd - self.FontStart) // 2 + 1

    def char_to_index(self, c):
        self._ensure_reverse()
        if self.hangul:
            from srwk_codec import HAN2CODE
            if c in HAN2CODE:
                return self._rev.get(HAN2CODE[c])
        try:
            b = c.encode("cp932")
        except Exception:
            return None
        sjis = (b[0] << 8) | b[1] if len(b) == 2 else b[0]
        return self._rev.get(sjis)

    def get_code(self, text):
        """char string -> list of bytes (GetValue per char). Raises on unknown char."""
        out = []
        for c in text:
            idx = self.char_to_index(c)
            if idx is None:
                raise KeyError(c)
            if idx >= self.T:
                a = idx - self.T
                out.append(self.T + a // 256)
                out.append(a % 256)
            else:
                out.append(idx)
        return out

def _change_name_flag(code1):
    u = code1 & 0xFFFF
    for m in (0xA000, 0x8000, 0x3000, 0x2000, 0x1000):
        u %= m
    s = u - 0x800 - 0x400
    return s >= 0

# ---------------------------------------------------------------------------
# Codebook REGENERATION (for translating blocks whose codebook is still the JP
# original — ch25+). Mirrors the tool's GetMapCodes + InsertMap exactly:
#   * build a frequency-descending charlist from all the block's translated text
#   * overwrite the Map region from FontStart with each char's SJIS (hi,lo),
#     keeping the codebook header (T, FontStart, IdiomStart, FontEnd, pairs)
#   * encode each char as its INDEX in that charlist (GetValue / GetCode)
# This is byte-for-byte the same behaviour that produced the shipped ch1-24
# codebooks, so it is the proven-safe path for new chapters.
# ---------------------------------------------------------------------------
def to_fullwidth(s):
    """The scenario codec stores 2-byte SJIS per glyph; half-width ASCII encodes
    to 1 byte and corrupts on decode. Normalise ASCII -> full-width (matching the
    existing patch's style: full-width digits/letters/punctuation and U+3000
    word spacing). Korean and already-full-width chars pass through."""
    out = []
    for c in s:
        o = ord(c)
        if o == 0x20:
            out.append("　")
        elif 0x21 <= o <= 0x7E:
            out.append(chr(o + 0xFEE0))
        else:
            out.append(c)
    return "".join(out)


_SANITIZE_MAP = {
    "—": "―", "―": "―", "–": "―", "‒": "―", "─": "―",
    "·": "・", "・": "・", "‧": "・",
    "­": "", "​": "", "﻿": "",
    # stray compatibility jamo that slip into casual speech -> nearest syllable
    "ㅋ": "크", "ㅎ": "흐", "ㅠ": "유", "ㅜ": "우", "ㅡ": "으",
    "ㅏ": "아", "ㅓ": "어", "ㅗ": "오", "ㅑ": "야",
}


def _nearest_hangul(c):
    """un-encodable syllable -> a displayable one by dropping the final jamo
    (e.g. 햣 -> 해). None if not a hangul syllable or still undisplayable."""
    o = ord(c)
    if not (0xAC00 <= o <= 0xD7A3):
        return None
    s = o - 0xAC00
    cand = chr(0xAC00 + (s // 28) * 28)        # same cho+jung, no jong
    return cand if char_to_sjis(cand, True) is not None else None


def sanitize_ko(text):
    """Make a Korean line encodable by the 2-byte SJIS / KS X 1001 2350 codec:
    full-width ASCII, map known punctuation, approximate any syllable outside the
    2350 set, drop the rest. Returns (clean_text, substitutions[(orig,repl)])."""
    text = to_fullwidth(text)
    out, subs = [], []
    for c in text:
        if char_to_sjis(c, True) is not None:
            out.append(c)
            continue
        r = _SANITIZE_MAP.get(c)
        if r is None:
            r = _nearest_hangul(c)
        if r is None:
            r = ""
        if r:
            out.append(r)
        subs.append((c, r))
    return "".join(out), subs


def char_to_sjis(c, hangul):
    """char -> SJIS code (GetTableData). Korean via the KSC table, else cp932."""
    if hangul:
        from srwk_codec import HAN2CODE
        if c in HAN2CODE:
            return HAN2CODE[c]
    try:
        b = c.encode("cp932")
    except Exception:
        return None
    return (b[0] << 8) | b[1] if len(b) == 2 else b[0]

def build_charlist(texts, hangul):
    """GetMapCodes: frequency-descending unique-char list across all sub-lines.
    Chars with no table entry are dropped (they can't be encoded)."""
    from collections import OrderedDict
    cnt = OrderedDict()
    for t in texts:
        for c in t:
            cnt[c] = cnt.get(c, 0) + 1
    seen = list(cnt.keys())
    order = {c: i for i, c in enumerate(seen)}
    # descending count; stable by first-seen for determinism
    chars = sorted(seen, key=lambda c: (-cnt[c], order[c]))
    chars = [c for c in chars if char_to_sjis(c, hangul) is not None]
    return "".join(chars)

def regen_codebook(orig_cb, charlist, hangul):
    """InsertMap: overwrite the Map region of an existing codebook with the
    charlist's SJIS codes (hi,lo per char) from FontStart, and UPDATE FontEnd to
    match. When the charlist needs more slots than the JP original (small JP
    codebooks vs richer Korean), the Map grows past the old FontEnd into the
    now-unused idiom region (KR never emits idiom codes), extending the block if
    necessary. The char index space stays well below IdiomStart (~0xFCxx) for any
    realistic mission, so no char is mis-read as an idiom (the build's decode-back
    self-check guards this)."""
    cb = bytearray(orig_cb)
    fs = _i32(cb, 0x14)
    n = len(charlist)
    end = fs + 2 * n                      # Map occupies [fs, end)
    if end > len(cb):
        cb.extend(b"\x00" * (end - len(cb)))
    p = fs
    for c in charlist:
        sjis = char_to_sjis(c, hangul)
        cb[p] = (sjis >> 8) & 0xFF
        cb[p + 1] = sjis & 0xFF
        p += 2
    struct.pack_into("<i", cb, 0x2C, fs + 2 * n - 2)   # FontEnd
    return bytes(cb)

def get_byte_count(s):
    """GetByteCount: Korean syllable=12, everything else=8 width units."""
    return sum(12 if ("가" <= c <= "힣") else 8 for c in s)


def wrap_sublines(lines, limit=176):
    """Split any sub-line wider than `limit` into more sub-lines (extra pages),
    breaking at full-width spaces (word boundaries); hard-split a single word
    that still overflows. Keeps the original page breaks and only subdivides the
    too-long ones, so no on-screen line exceeds the box width (Max_Length=176)."""
    out = []
    for line in lines:
        if get_byte_count(line) <= limit:
            out.append(line)
            continue
        cur = ""
        for word in line.split("　"):
            piece = (cur + "　" + word) if cur else word
            if get_byte_count(piece) <= limit:
                cur = piece
                continue
            if cur:
                out.append(cur)
                cur = ""
            while get_byte_count(word) > limit:     # word alone too wide
                take = ""
                for ch in word:
                    if get_byte_count(take + ch) > limit:
                        break
                    take += ch
                out.append(take)
                word = word[len(take):]
            cur = word
        if cur:
            out.append(cur)
    return out

MAX_LENGTH = 176  # Common.Max_Length — per sub-line width cap

def decode_block_native(block, codebook_block, hangul):
    """Decode one scenario block -> list of nodes; each node = dict with
    code1, code2, name(changeName or ''), lines (list of sub-line strings)."""
    cbk = Codebook(codebook_block, hangul)
    T = cbk.T
    desc_start = _i32(block, 0)                       # pointer table size
    desc_end = _i32(block, desc_start - 4)            # last pointer = text end
    # section pointers: block[0:desc_start] Int32 each; values = section-start
    # node offsets (relative to block start); the last one = desc_end.
    sec_offsets = set(struct.unpack_from(f"<{desc_start // 4}i", block, 0)[:-1])
    nodes = []
    p = desc_start
    n = min(desc_end, len(block))
    while p < n:
        if p + 4 > n:
            break
        node_off = p
        code1 = struct.unpack_from("<h", block, p)[0]; p += 2
        code2 = struct.unpack_from("<h", block, p)[0]; p += 2
        name = ""
        if _change_name_flag(code1):
            nb = []
            while p < n and block[p] != 0:
                nb.append(block[p]); p += 1
            p += 1  # skip the 0x00
            for i in range(0, len(nb) - 1, 2):
                name += _sjis_char((nb[i] << 8) | nb[i + 1], hangul) or ""
        lines = []
        while p < n:
            length = block[p]; p += 1
            cnt = length % 0x80
            chars = []
            i = 0
            while i < cnt and p < n:
                b = block[p]; p += 1
                if b >= T:
                    chars.append(cbk.get_char((block[p], b))); p += 1; i += 1
                else:
                    chars.append(cbk.get_char((b, 0)))
                i += 1
            lines.append("".join(chars))
            if length > 0x80:
                break
        nodes.append({"code1": code1 & 0xFFFF, "code2": code2 & 0xFFFF,
                      "name": name, "lines": lines,
                      "sec": node_off in sec_offsets})
    return nodes

def encode_block_native(nodes, codebook_block, hangul, orig_block=None, charlist=None):
    """Re-encode node list -> a scenario block (pointer table + node stream),
    using the existing codebook (char-by-char, no idioms — functionally equal
    to the patchers' own GetCode encoder; byte-exact for unedited KR blocks).

    Node = {c1(hex),c2(hex),name?,lines[],sec?}. Section-start nodes (sec=True)
    re-create the section pointer table with their NEW offsets, so editing a
    line's length keeps every section pointer correct. The pointer count equals
    (#section nodes)+1 (the trailing pointer = DescEnd).

    If `charlist` is given (a regenerated mission charlist), chars are encoded by
    their index in it (GetCode/GetValue) rather than by the codebook reverse map
    — required when codebook_block is a freshly regenerated codebook (ch25+)."""
    cbk = Codebook(codebook_block, hangul)
    T = cbk.T
    def _enc_line(line):
        if charlist is None:
            return cbk.get_code(line)
        out = []
        for c in line:
            idx = charlist.find(c)
            if idx < 0:
                raise KeyError(c)
            if idx >= T:
                a = idx - T
                out.append(T + a // 256); out.append(a % 256)
            else:
                out.append(idx)
        return out
    def _hx(v):
        return int(v, 16) if isinstance(v, str) else v
    # how many section pointers are there? = #sec nodes + 1 (DescEnd). With this
    # known, the pointer table size ds = n_ptr*4, which is also node[0]'s offset.
    sec_flags = [bool(nd.get("sec", False)) for nd in nodes]
    if nodes and not sec_flags[0]:
        sec_flags[0] = True               # first node always starts a section
    n_ptr = sum(sec_flags) + 1
    ds = n_ptr * 4                         # pointer table size = first node offset
    body = bytearray()
    sec_node_off = []                     # absolute offsets of section-start nodes
    for nd, is_sec in zip(nodes, sec_flags):
        if is_sec:
            sec_node_off.append(ds + len(body))
        c1 = _hx(nd["c1"] if "c1" in nd else nd["code1"])
        c2 = _hx(nd["c2"] if "c2" in nd else nd["code2"])
        body += struct.pack("<H", c1 & 0xFFFF)
        body += struct.pack("<H", c2 & 0xFFFF)
        name = nd.get("name", "")
        if _change_name_flag(c1):
            # name is stored as raw SJIS (big-endian) regardless of charlist
            for c in name:
                sjis = char_to_sjis(c, hangul)
                if sjis is not None:
                    body += bytes([sjis >> 8, sjis & 0xFF])
            body += b"\x00"
        lines = nd["lines"]
        for li, line in enumerate(lines):
            codes = _enc_line(line)
            last = (li == len(lines) - 1)
            body.append((0x80 + len(codes)) if last else len(codes))
            body += bytes(codes)
    desc_end = ds + len(body)
    # pointer table = [section-start offsets...] + [desc_end]
    ptr_vals = sec_node_off + [desc_end]
    assert len(ptr_vals) == n_ptr, (len(ptr_vals), n_ptr)
    out = bytearray(struct.pack(f"<{n_ptr}i", *ptr_vals))
    out += body
    return bytes(out)
