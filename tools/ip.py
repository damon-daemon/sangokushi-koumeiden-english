"""Town NPC lines SNR/IP.E2: parse into parts and strings, rebuild.

File: u16 part offsets (5 parts; the first value is also the header size). The EXE maps the town
index (byte 0x80103e50) to a part (u16 table 0x800aa254) and reads the part (length from the u32
table 0x800aa260, patched by build.py) into the buffer of descriptor 0x8010f4fc (0x3520 B at
0x801ba0c0), loader 0x800374c0. A part:
  u16 text start (from the part start)
  676 slots u16 (count, offset) = 26 x 26 (scene x progress?), ffff = empty; offset = byte offset
      into the NPC table that follows; read by 0x80037640
  NPC table: n x u16 (label, text offset from text start), one per string, strings in order
  text: n plain SJIS NUL strings (「 speech, LF lines, 3 lines a page as the talk box)
Rebuild rewrites the text offsets only.
"""
import os, struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'extract', 'SNR', 'IP.E2')
SLOTS = 676
PARTS = 5
BUF_MAX = 0x3520                         # descriptor 0x8010f4fc size (runtime value)
SIZES = 0x800aa260                       # u32 part lengths in the EXE


def load():
    with open(PATH, 'rb') as f:
        return f.read()


def parts(d=None):
    d = d or load()
    base = list(struct.unpack_from('<%dH' % PARTS, d)) + [len(d)]
    assert base[0] == 2 * PARTS
    return [d[base[k]:base[k + 1]] for k in range(PARTS)]


def parse(p):
    """part bytes -> (head bytes up to the NPC table, [label], [raw SJIS string])"""
    ts = struct.unpack_from('<H', p)[0]
    n = (ts - 2) // 4 - SLOTS
    tab = 2 + 4 * SLOTS
    labels, offs = [], []
    for i in range(n):
        a, o = struct.unpack_from('<HH', p, tab + 4 * i)
        labels.append(a)
        offs.append(o)
    strs = p[ts:].split(b'\0')
    assert strs[-1] == b'' and len(strs) == n + 1
    pos = 0
    for o, s in zip(offs, strs):
        assert o == pos
        pos += len(s) + 1
    return p[:tab], labels, strs[:-1]


def file_parts():
    return [parse(p) for p in parts()]


def rebuild(en=None):
    """en: {(k, n): bytes} -> (new IP.E2, [part lengths])"""
    en = en or {}
    out, sizes = bytearray(2 * PARTS), []
    for k, (head, labels, strs) in enumerate(file_parts()):
        tab, body = bytearray(), bytearray()
        for n, (a, s) in enumerate(zip(labels, strs)):
            tab += struct.pack('<HH', a, len(body))
            body += en.get((k, n), s) + b'\0'
        p = bytearray(head + tab + body)
        struct.pack_into('<H', p, 0, len(head) + len(tab))
        assert len(p) <= BUF_MAX, 'IP part %d: %d bytes > %d' % (k, len(p), BUF_MAX)
        struct.pack_into('<H', out, 2 * k, len(out))
        out += p
        sizes.append(len(p))
    assert len(out) < 0x10000, 'IP.E2 %d bytes: u16 part offsets' % len(out)
    return bytes(out), sizes


if __name__ == '__main__':
    d = load()
    new, sizes = rebuild()
    assert new == d, 'rebuild differs'
    for k, (head, labels, strs) in enumerate(file_parts()):
        print('part %d: %d strings, %d B text, %d B' % (k, len(strs), sum(len(s) + 1 for s in strs), sizes[k]))
    print('rebuild identical')
