"""Chapter text SNR/SNRcM.E2 (c = 0-5): parse into parts and entries, rebuild.

M starts with a u16 table of part (scene) offsets (first value = table size); part k pairs with
part k of SNRcD.E2 (event script), which refers to M entries by u16 offsets from the part start.
A part is a run of entries (Eiketsuden EVM format):
  plain     text NUL                       (title, narration, caption, choice)
  dialogue  {u16 speaker, text NUL}... ffff  (speaker 0 = Kongming)
Original text is compressed: bytes 0x20-0x72 stand for hiragana, 0x73-0x76 for punctuation. The
patched decompressor copies every single byte < 0x80, so rebuilt text holds ASCII and SJIS pairs.
"""
import os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNR = os.path.join(ROOT, 'extract', 'SNR')
CHAPTERS = range(6)
MAX_SPEAKER = 0x200
PLAIN_MAX = 0x400                        # plain entries: read into 0x400-B stack buffers (interpreter 0x800252ec)
BLOCK_MAX = 0xc00                        # dialogue blocks: reader 0x80026a3c, frame grown in build.py
REMAP_MAX = 0xc00                        # RAM for one part's table (build.REMAP)
PUNCT = {0x73: '、', 0x74: '。', 0x75: '？', 0x76: '！'}


def names():
    return ['SNR%dM' % c for c in CHAPTERS]


def load(name):
    with open(os.path.join(SNR, name + '.E2'), 'rb') as f:
        return f.read()


def script(name):
    with open(os.path.join(SNR, name[:-1] + 'D.E2'), 'rb') as f:
        return f.read()


def parts(d):
    """-> [bytes] of each part"""
    n = struct.unpack_from('<H', d)[0] // 2
    base = list(struct.unpack_from('<%dH' % n, d)) + [len(d)]
    return [d[base[k]:base[k + 1]] for k in range(n)]


def d_parts(d):
    """script file: same u16 part table"""
    return parts(d)


def is_talk(d, p):
    return p + 3 <= len(d) and d[p + 1] in (0, 1) and d[p] | d[p + 1] << 8 < MAX_SPEAKER and d[p + 2] != 0


def parse(d):
    """part bytes -> [(offset, 'plain', raw) | (offset, 'talk', [(speaker, raw)...])]"""
    out, p = [], 0
    while p < len(d):
        start = p
        if is_talk(d, p):
            sp = []
            while d[p:p + 2] != b'\xff\xff':
                who = d[p] | d[p + 1] << 8
                assert who < MAX_SPEAKER, (start, p, who)
                e = d.index(0, p + 2)
                sp.append((who, d[p + 2:e]))
                p = e + 1
            p += 2
            out.append((start, 'talk', sp))
        else:
            e = d.index(0, p)
            out.append((start, 'plain', d[p:e]))
            p = e + 1
    return out


def expand(raw):
    """compressed original text -> SJIS bytes the decompressor would output"""
    out, i = bytearray(), 0
    while i < len(raw):
        b = raw[i]
        i += 1
        if b < 0x20:
            out.append(b)
        elif b < 0x73:
            out += bytes((0x82, b + 0x7f))
        elif b < 0x80:
            if b in PUNCT:
                out += PUNCT[b].encode('cp932')
        else:
            out += raw[i - 1:i + 1]
            i += 1
    return bytes(out)


def show(raw, plain_sjis=False):
    """display form of original text: Unicode, control bytes as \\n or <xx>"""
    b, out, i = raw if plain_sjis else expand(raw), [], 0
    while i < len(b):
        c = b[i]
        if c == 0x0a:
            out.append('\\n')
            i += 1
        elif c < 0x20 or c == 0x7f:
            out.append('<%02x>' % c)
            i += 1
        elif c < 0x80 or 0xa0 <= c < 0xe0:
            out.append(bytes((c,)).decode('cp932', 'replace'))
            i += 1
        elif c >= 0xf0:   # gaiji (cp932 would decode the user area to invisible PUA characters)
            out.append('<%02x%02x>' % (c, b[i + 1]))
            i += 2
        else:
            try:
                out.append(b[i:i + 2].decode('cp932'))
            except UnicodeDecodeError:
                out.append('<%02x%02x>' % (c, b[i + 1]))
            i += 2
    return ''.join(out)


def rebuild(parts_entries, en=None):
    """[[entries of part k]] (parse()); en: {(k, n, j or None): bytes} replaces text (already encoded).
    -> new M file:
      header  per part: u32 table offset, u32 table size
      table   u16 n, u16 0, u16 old[n] (sorted, D offsets from the part start), pad to 4, u32 new[n]
              (file offsets); read into RAM by the part-load hook, searched by the text-read hook
      entries of the part
    then BLOCK_MAX zero bytes (a read may run past the last entry)."""
    en = en or {}
    out = bytearray(8 * len(parts_entries))
    for k, entries in enumerate(parts_entries):
        body, olds, news = bytearray(), [], []
        for n, (off, kind, val) in enumerate(entries):
            olds.append(off)
            news.append(len(body))
            if kind == 'plain':
                t = en.get((k, n, None), expand(val))
                assert len(t) < PLAIN_MAX, 'part %d entry %d: %d bytes' % (k, n, len(t))
                body += t + b'\0'
            else:
                start = len(body)
                for j, (who, raw) in enumerate(val):
                    body += struct.pack('<H', who) + en.get((k, n, j), expand(raw)) + b'\0'
                body += b'\xff\xff'
                assert len(body) - start <= BLOCK_MAX, 'part %d block %d: %d bytes' % (k, n, len(body) - start)
        assert olds == sorted(olds)
        cnt = len(olds)
        tab = struct.pack('<HH', cnt, 0) + struct.pack('<%dH' % cnt, *olds)
        tab += bytes(-len(tab) % 4)
        base = len(out) + len(tab) + 4 * cnt
        tab += struct.pack('<%dI' % cnt, *(base + x for x in news))
        assert len(tab) <= REMAP_MAX, 'part %d: table %d bytes' % (k, len(tab))
        struct.pack_into('<II', out, 8 * k, len(out), len(tab))
        out += tab + body
        out += bytes(-len(out) % 4)
    return bytes(out + bytes(BLOCK_MAX))


def file_entries(name):
    return [parse(p) for p in parts(load(name))]


def entry_size(kind, val):
    """bytes of the entry as stored (compressed form)"""
    if kind == 'plain':
        return len(val) + 1
    return sum(3 + len(r) for _, r in val) + 2


if __name__ == '__main__':
    from collections import Counter
    big = Counter()
    for name in names():
        for k, part in enumerate(parts(load(name))):
            es = parse(part)
            sizes = [entry_size(kind, v) for _, kind, v in es]
            exp = [max(len(expand(r)) for r in ([v] if kind == 'plain' else [r for _, r in v])) for _, kind, v in es]
            print('%s.%d %6d B %4d entries  max entry %4d  max text %4d  >0x400: %d' % (
                name, k, len(part), len(es), max(sizes), max(exp), sum(s > 0x400 for s in sizes)))
