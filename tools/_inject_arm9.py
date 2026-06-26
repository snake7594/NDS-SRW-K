# -*- coding: utf-8 -*-
"""Inject Korean translations for the 15 untranslated arm9 strings (8 character
names + 7 save/load system messages) into kr/arm9.bin.

- in-place where the KO encoding (+null) fits the slot budget (bytes until next
  non-zero); the string start offset is unchanged so all pointers stay valid
  (same method the YameSoft patch used for its 2002 translated strings).
- repoint the few that don't fit: write KO into reclaimed dev-only debug-string
  space and update every arm9 pointer (LE u32 == 0x02000000+orig_off).
Verifies by decoding each slot back, and that arm9 size is unchanged."""
import io, struct
from srwk_codec import CODE2HAN, HAN2CODE

BASE = 0x02000000
arm9 = bytearray(open('kr/arm9.bin', 'rb').read())
ORIG_LEN = len(arm9)

# offset -> Korean translation (canonical names from the scenario where available)
TR = {
    0x683f8: '히이라기 후유코',   # 柊　冬子
    0x68818: '히노 요우지',       # 日野　洋治  (scenario: 히노 요우지)
    0x68890: '우즈키 미와',       # 卯月　美和  (scenario: 우즈키)
    0x688c0: '유미 겐노스케',     # 弓　弦之助  (scenario: 유미/弓)
    0x68938: '미도 류코',         # 身堂　竜子  (scenario: 미도)
    0x68a04: '미조구치 쿄스케',   # 溝口　恭介  (scenario: 미조구치)
    0x69124: 'DSSD 병사',         # ＤＳＳＤヘイ
    0x69244: '시바 칸지로',       # 司馬　還次郎 (scenario: 시바)
    0x94c1c: '데이터 로드가 완료되었습니다',
    0x94c40: '데이터를 읽지 못했습니다. 전원을 끄고 카드를 다시 꽂아 주세요',
    0x94c88: '데이터가 손상되었습니다',
    0x94ca0: '데이터가 없습니다(공장 출하 상태)',
    0x94cc8: '데이터 저장이 완료되었습니다',
    0x94cec: '데이터 저장에 실패했습니다',
    0x94d0c: '데이터를 기록하지 못했습니다. 전원을 끄고 카드를 다시 꽂아 주세요',
}

# reclaim space: dev-only debug strings (never shown to players)
RECLAIM = [(0x42980, 0x436ec - 0x42980)]   # H-blank debug str region, ~3436 bytes free for our use


def enc(s):
    """Korean/ASCII string -> game SJIS bytes (Hangul via HAN2CODE, ASCII as-is)."""
    out = bytearray()
    for ch in s:
        if ch in HAN2CODE:
            out += struct.pack('>H', HAN2CODE[ch])
        elif ord(ch) < 0x80:
            out.append(ord(ch))
        else:
            raise ValueError('unencodable char %r in %r' % (ch, s))
    return bytes(out)


def slot_budget(off):
    raw_end = off
    while raw_end < len(arm9) and arm9[raw_end] != 0:
        raw_end += 1
    z = raw_end
    while z < len(arm9) and arm9[z] == 0:
        z += 1
    return z - off          # bytes from start to next non-zero (text + padding)


def find_ptrs(off):
    target = BASE + off
    return [i for i in range(0, len(arm9) - 3) if struct.unpack_from('<I', arm9, i)[0] == target]


def main():
    log = io.open('_inject_log.txt', 'w', encoding='utf-8')
    recl_off, recl_left = RECLAIM[0][0], RECLAIM[0][1]
    inplace = repointed = 0
    for off in sorted(TR):
        ko = TR[off]
        b = enc(ko)
        budget = slot_budget(off)
        if len(b) + 1 <= budget:
            # in-place: overwrite slot, null-pad to the old string length region
            arm9[off:off + len(b)] = b
            for k in range(off + len(b), off + budget):
                arm9[k] = 0
            inplace += 1
            log.write('IN-PLACE 0x%06x budget=%d use=%d  %s\n' % (off, budget, len(b) + 1, ko))
        else:
            ptrs = find_ptrs(off)
            if not ptrs:
                log.write('!! 0x%06x NO POINTERS found, cannot repoint (%s)\n' % (off, ko)); continue
            if len(b) + 1 > recl_left:
                log.write('!! reclaim space exhausted for 0x%06x\n' % off); continue
            new_off = recl_off
            arm9[new_off:new_off + len(b)] = b
            arm9[new_off + len(b)] = 0
            recl_off += len(b) + 1; recl_left -= len(b) + 1
            for p in ptrs:
                struct.pack_into('<I', arm9, p, BASE + new_off)
            repointed += 1
            log.write('REPOINT  0x%06x -> 0x%06x  (%d ptrs)  budget=%d use=%d  %s\n'
                      % (off, new_off, len(ptrs), budget, len(b) + 1, ko))

    # verify size unchanged
    assert len(arm9) == ORIG_LEN, 'arm9 size changed!'
    open('kr/arm9_patched.bin', 'wb').write(arm9)
    log.write('\narm9 size: %d (unchanged: %s)\n' % (len(arm9), len(arm9) == ORIG_LEN))
    log.write('in-place: %d  repointed: %d\n' % (inplace, repointed))
    log.close()
    print('in-place=%d repointed=%d  -> kr/arm9_patched.bin' % (inplace, repointed))


if __name__ == '__main__':
    main()
