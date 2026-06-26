# -*- coding: utf-8 -*-
"""
srwk_codec.py — Super Robot Wars K (NDS) text codec.

Two text systems live in data/add03dat.bin:
  * System/SJIS text  : 2-byte SJIS codes; kanji slots (>=0x889F) remapped to
                        KS X 1001 (Wansung 2350) hangul in EUC-KR order.
  * Dialogue text     : per-block variable-length prefix code into a
                        frequency-ordered character list (the "codebook" block).

This module provides:
  - KSC <-> SJIS-slot mapping (build_ksc_maps)
  - add03dat container parsing (Add03)
  - codebook (charlist) parsing (parse_codebook)
  - dialogue symbol decode/encode (lossless, index-based)
  - char-level decode for human reading

Round-trip guarantee: decode_symbols() -> encode_symbols() reproduces the exact
original bytes, because each symbol stores its codebook *index* and the
index<->byte mapping is deterministic (idx<251 -> 1 byte, else 2 bytes).
"""
import struct

# ---------------------------------------------------------------- KSC mapping
def build_ksc_maps():
    """Return (code2han, han2code) for the SJIS-slot <-> hangul mapping."""
    hangul = []
    for lead in range(0xB0, 0xC9):
        for trail in range(0xA1, 0xFF):
            try:
                ch = bytes([lead, trail]).decode("euc-kr")
            except Exception:
                continue
            if 0xAC00 <= ord(ch) <= 0xD7A3:
                hangul.append(ch)
    # consecutive SJIS double-byte codes starting at 0x889F
    codes = []
    lead, trail = 0x88, 0x9F
    while len(codes) < len(hangul):
        if 0x40 <= trail <= 0x7E or 0x80 <= trail <= 0xFC:
            codes.append((lead << 8) | trail)
        trail += 1
        if trail > 0xFC:
            trail = 0x40
            lead += 1
    code2han = {c: h for c, h in zip(codes, hangul)}
    han2code = {h: c for c, h in code2han.items()}
    return code2han, han2code

CODE2HAN, HAN2CODE = build_ksc_maps()

def _is_lead(b): return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC
def _valid_trail(b): return 0x40 <= b <= 0x7E or 0x80 <= b <= 0xFC

def sjis_slot_to_char(code, hangul=True):
    """Decode a 2-byte font code to a char.
    hangul=True (KR rom): kanji slots (>=0x889F) are remapped to hangul.
    hangul=False (JP rom): pure cp932 (the slots are still kanji)."""
    if hangul and code in CODE2HAN:
        return CODE2HAN[code]
    try:
        return bytes([code >> 8, code & 0xFF]).decode("cp932")
    except Exception:
        return None

# ------------------------------------------------------------- add03 container
class Add03:
    """Parse/rebuild data/add03dat.bin: top-level offset table -> blocks."""
    def __init__(self, data: bytes):
        self.data = data
        n = struct.unpack_from("<I", data, 0)[0] // 4
        offs = list(struct.unpack_from(f"<{n}I", data, 0)) + [len(data)]
        self.n = n
        self.blocks = [data[offs[i]:offs[i + 1]] for i in range(n)]

    @classmethod
    def from_file(cls, path):
        with open(path, "rb") as f:
            return cls(f.read())

    def rebuild(self) -> bytes:
        """Reassemble with a fresh offset table (blocks may have changed size)."""
        n = len(self.blocks)
        table_size = n * 4
        offs = []
        cur = table_size
        for b in self.blocks:
            offs.append(cur)
            cur += len(b)
        out = bytearray()
        out += struct.pack(f"<{n}I", *offs)
        for b in self.blocks:
            out += b
        return bytes(out)

def sub_entries(block: bytes):
    """A block's internal u32 offset table -> list of (off, slice)."""
    n = struct.unpack_from("<I", block, 0)[0] // 4
    offs = list(struct.unpack_from(f"<{n}I", block, 0)) + [len(block)]
    return [block[offs[i]:offs[i + 1]] for i in range(n)]

# ------------------------------------------------------------------- codebook
# Codebook layout:
#   u32 @0x00 : number of (cumfreq, offset) pairs
#   12 bytes  : reserved (0)
#   @0x10     : pairs [ (u32 cumfreq, u32 charlist_offset) ] * count
#   charlist  : 2-byte SJIS codes, beginning at the first pair's offset (@0x14)
#   trailer   : binary
def codebook_charlist_start(cb: bytes):
    return struct.unpack_from("<I", cb, 0x14)[0]

def codebook_threshold(cb: bytes):
    """Single/double byte boundary T = high byte of the first pair's cumfreq.
    Bytes < T are 1-byte symbols (indices 0..T-1); bytes >= T start a 2-byte
    symbol whose 16-bit value V gives index T + (V - T*256)."""
    first_cumfreq = struct.unpack_from("<I", cb, 0x10)[0]
    return first_cumfreq >> 8

def parse_codebook(cb: bytes, hangul=True):
    """Parse a codebook block -> (charlist, end_offset, threshold)."""
    charlist = []
    off = codebook_charlist_start(cb)
    while off + 1 < len(cb) and _is_lead(cb[off]) and _valid_trail(cb[off + 1]):
        code = (cb[off] << 8) | cb[off + 1]
        charlist.append(sjis_slot_to_char(code, hangul))
        off += 2
    return charlist, off, codebook_threshold(cb)

# --------------------------------------------------- dictionary macros (>=len)
# Indices >= len(charlist) are multi-char MACROS.  The codebook's (cumfreq,offset)
# header pairs define LENGTH-BUCKETS: bucket b covers index range
# [cf2idx(cf[b-1]), cf2idx(cf[b])) and stores fixed-width entries (width grows
# 3,4,5,... bytes) in byte range [off[b], off[b+1]).  An entry is `width` bytes
# decoded with the usual 1-byte(<T)/2-byte symbol rule; each symbol is a charlist
# char or a NESTED macro (recurse).  (Cracked + verified 16/16 on block 195.)
def dict_buckets(cb: bytes, T):
    charlist_start = codebook_charlist_start(cb)
    n = (charlist_start - 0x10) // 8
    pairs = [struct.unpack_from("<II", cb, 0x10 + 8 * i) for i in range(n)]
    base = T << 8
    def cf2idx(cf): return T + (cf - base)
    buckets = []  # (idx_start, idx_end, off_start, width)
    for i in range(1, len(pairs) - 1):
        i0, i1 = cf2idx(pairs[i - 1][0]), cf2idx(pairs[i][0])
        o0, o1 = pairs[i][1], pairs[i + 1][1]
        if i1 - i0 > 0 and o1 - o0 > 0:
            buckets.append((i0, i1, o0, (o1 - o0) // (i1 - i0)))
    return buckets

def _macro_entry_off(buckets, index):
    for i0, i1, o0, w in buckets:
        if i0 <= index < i1:
            return o0 + (index - i0) * w, w
    return None, None

def expand_macro(cb, charlist, T, index, buckets, _depth=0):
    """Expand a macro index (>=len(charlist)) to its charlist string."""
    if index < len(charlist):
        return charlist[index] if charlist[index] is not None else f"[{index}]"
    off, w = _macro_entry_off(buckets, index)
    if off is None:
        return f"<D{index}>"
    out = []
    o, end = off, off + w
    while o < end:
        b = cb[o]
        if b < T:
            sub, blen = b, 1
        else:
            sub, blen = T + (((b << 8) | cb[o + 1]) - (T << 8)), 2
        o += blen
        if sub < len(charlist):
            out.append(charlist[sub] if charlist[sub] is not None else f"[{sub}]")
        elif _depth < 8:
            out.append(expand_macro(cb, charlist, T, sub, buckets, _depth + 1))
        else:
            out.append(f"<D{sub}>")
    return "".join(out)

# --------------------------------------------------------- dialogue codec core
DEFAULT_THRESHOLD = 0xFB  # most codebooks; real value read per-codebook

def decode_symbols(raw: bytes, T=DEFAULT_THRESHOLD):
    """Lossless tokenize dialogue bytes -> list of (index, byte_len).
    T = codebook threshold (bytes < T are 1-byte symbols)."""
    syms = []
    i = 0
    n = len(raw)
    base_val = T << 8
    while i < n:
        b = raw[i]
        if b < T:
            syms.append((b, 1))
            i += 1
        else:
            if i + 1 < n:
                V = (b << 8) | raw[i + 1]
                idx = T + (V - base_val)
                syms.append((idx, 2))
                i += 2
            else:
                syms.append((b, 1))
                i += 1
    return syms

def encode_symbols(syms, T=DEFAULT_THRESHOLD) -> bytes:
    """Inverse of decode_symbols (byte-exact)."""
    out = bytearray()
    base_val = T << 8
    for idx, blen in syms:
        if blen == 1:
            out.append(idx)
        else:
            V = base_val + (idx - T)
            out.append((V >> 8) & 0xFF)
            out.append(V & 0xFF)
    return bytes(out)

def symbols_to_text(syms, charlist):
    """Human-readable string; unknown indices -> [idx] marker."""
    out = []
    for idx, blen in syms:
        if 0 <= idx < len(charlist) and charlist[idx] is not None:
            out.append(charlist[idx])
        else:
            out.append(f"[{idx}]")
    return "".join(out)

def decode_dialogue(raw, charlist):
    return symbols_to_text(decode_symbols(raw), charlist)

# ----------------------------------------------------- human-editable rendering
# Line/speaker marker = [face] OP [flag in {0,2}] 0x00 [portrait], OP in {4,5}.
# The 5th byte (portrait/expression id) is part of the marker (cracked + verified).
# Rendered as token {face|op|flag|port}; a 4-byte marker w/o portrait -> {face|op|flag|}.
# Space symbol (index 0) renders as ' '.  idx>=len(charlist) = dict macro
# (expanded for the JP reference field; left as 〈idx〉 otherwise).
import re
SPACE_IDX = 0
_MARK_RE = re.compile(r"\{(\d+)\|(\d+)\|(\d+)\|(\d*)\}")
_UNK_RE = re.compile(r"〈(\d+)〉")
_MACRO_RE = re.compile(r"《([^《》]*)》")

def build_macro_map(cb, charlist, T, buckets=None):
    """expansion_string -> macro index, for re-encoding 《...》 tokens.
    First index wins on collision (rare)."""
    if buckets is None:
        buckets = dict_buckets(cb, T)
    m = {}
    # macro indices run from len(charlist) up to the last bucket's end
    if buckets:
        hi = max(b[1] for b in buckets)
        for idx in range(len(charlist), hi):
            s = expand_macro(cb, charlist, T, idx, buckets)
            if s and not s.startswith("<") and s not in m:
                m[s] = idx
    return m
# NOTE on inline control codes (portrait/effect bytes interspersed in dialogue):
# they are dual-use — the SAME byte value is text in one spot and a control in
# another, decided by the game engine's render STATE (proven: block130 entry0
# implies "control after punctuation", entry1 contradicts it — 君=0x8a is text
# after 、 while 憶=0x88 is control after て). No positional/value heuristic is
# safe (a band-rule attempt mis-flagged real 君). Stripping them correctly needs
# the ROM's text renderer (disassembly / emulator trace). Left as-is for now.

def build_reverse_charlist(charlist):
    """char -> index (first occurrence). idx0 space handled separately."""
    rev = {}
    for i, c in enumerate(charlist):
        if c is None:
            continue
        if c not in rev:
            rev[c] = i
    return rev

def _is_marker4(syms, i):
    """The 4-byte marker core: [face] OP(4|5) [flag(0|2)] 0x00."""
    return (i + 3 < len(syms)
            and syms[i][1] == 1
            and syms[i + 1][0] in (4, 5) and syms[i + 1][1] == 1
            and syms[i + 2][0] in (0, 2) and syms[i + 2][1] == 1
            and syms[i + 3] == (0, 1))

def render_ko(syms, charlist, rev=None, cb=None, buckets=None, T=DEFAULT_THRESHOLD,
              macro_token=False):
    """Render symbols to an editable string: text + {face|op|flag|port} markers.
    A char is rendered literally only if it maps back to this exact index;
    otherwise it is 〈idx〉 so parse_ko reproduces the original bytes exactly.
    Macro indices (>=len(charlist)) need cb+buckets:
      macro_token=False -> inline expansion (read-only JP reference field)
      macro_token=True  -> 《expansion》 token (KO field; round-trips via build_macro_map)."""
    if rev is None:
        rev = build_reverse_charlist(charlist)
    out = []
    i = 0
    n = len(syms)
    prev_punct = False
    while i < n:
        if _is_marker4(syms, i):
            face = syms[i][0]; op = syms[i + 1][0]; flag = syms[i + 2][0]
            # consume a 5th portrait byte (must be 1-byte, not another marker)
            if i + 4 < n and syms[i + 4][1] == 1 and not _is_marker4(syms, i + 4):
                out.append(f"{{{face}|{op}|{flag}|{syms[i + 4][0]}}}")
                i += 5
            else:
                out.append(f"{{{face}|{op}|{flag}|}}")
                i += 4
            prev_punct = False
            continue
        idx, blen = syms[i]
        if idx == SPACE_IDX:
            out.append(" ")
        elif idx < len(charlist) and charlist[idx] is not None and rev.get(charlist[idx]) == idx:
            out.append(charlist[idx])
        elif idx >= len(charlist) and cb is not None and buckets is not None:
            exp = expand_macro(cb, charlist, T, idx, buckets)
            if macro_token:
                # only emit a 《》 token if it cleanly round-trips (no unresolved
                # <D..> placeholder); else keep the raw 〈idx〉 (still byte-exact)
                out.append(f"《{exp}》" if "<" not in exp else f"〈{idx}〉")
            else:
                out.append(exp)
        else:
            out.append(f"〈{idx}〉")
        i += 1
    return "".join(out)

def parse_ko(text, charlist, rev=None, T=DEFAULT_THRESHOLD, macro_map=None):
    """Inverse of render_ko -> symbol list. A 《...》 token whose text is a known
    macro (macro_map) re-emits that 2-byte macro index (byte-exact); an edited
    《...》 falls back to plain chars. Plain text without 《》 encodes as chars."""
    if rev is None:
        rev = build_reverse_charlist(charlist)
    syms = []
    i = 0
    n = len(text)
    while i < n:
        m = _MARK_RE.match(text, i)
        if m:
            face = int(m.group(1)); op = int(m.group(2)); flag = int(m.group(3))
            syms.append((face, 1)); syms.append((op, 1))
            syms.append((flag, 1)); syms.append((0, 1))
            if m.group(4) != "":
                syms.append((int(m.group(4)), 1))
            i = m.end(); continue
        mu = _UNK_RE.match(text, i)
        if mu:
            idx = int(mu.group(1))
            syms.append((idx, 1 if idx < T else 2))
            i = mu.end(); continue
        mm = _MACRO_RE.match(text, i)
        if mm:
            inner = mm.group(1)
            if macro_map is not None and inner in macro_map:
                syms.append((macro_map[inner], 2))
            else:                      # edited macro -> encode its chars plainly
                for ch in inner:
                    _emit_char(syms, ch, rev, T)
            i = mm.end(); continue
        ch = text[i]
        if ch == " ":
            syms.append((SPACE_IDX, 1)); i += 1; continue
        _emit_char(syms, ch, rev, T)
        i += 1
    return syms

def _emit_char(syms, ch, rev, T):
    if ch == " ":
        syms.append((SPACE_IDX, 1)); return
    idx = rev.get(ch)
    if idx is None:
        raise KeyError(f"char {ch!r} not in codebook charlist")
    syms.append((idx, 1 if idx < T else 2))
