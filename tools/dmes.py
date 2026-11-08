"""Officer retreat lines SNR/DMES.E2: parse, rebuild.

File: entries {u8 officer id, text, LF}, then ff LF. Read whole (length 0x9f6 at 0x8003dc54, patched
by build.py) by 0x8003dbec, which finds the entry of an id and copies its text **two bytes at a
time** and stops at a LF at such a position; a byte 0x73 there became a line break and the next check is
1 byte later. build.py makes that byte 0x01 (text.DMES_BREAK; 's' is ASCII). Japanese pads lines with
full-width spaces to the 32-column box; the English uses the break byte (text.py kind 'dmes').
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'extract', 'SNR', 'DMES.E2')
SIZE = 0x9f6                             # read length in the EXE
TEXT_MAX = 0xff                          # copied to a 0x100-B stack buffer


def load():
    with open(PATH, 'rb') as f:
        return f.read()


def parse(d=None):
    """-> [(id, raw SJIS)]"""
    d = d or load()
    out, p = [], 0
    while d[p] != 0xff:
        who, p = d[p], p + 1
        s = p
        while d[p] != 0x0a:
            p += 2
        out.append((who, d[s:p]))
        p += 1
    assert d[p:] == b"\xff\n"
    return out


def readable(t, english=True):
    """the reader (2 bytes a step, 1 after a break byte) checks a position == len(t), none holds LF"""
    p = 0
    while p < len(t):
        if t[p] == 0x0a:
            return False
        p += 1 if english and t[p] == 0x01 else 2
    return p == len(t)


def rebuild(en=None):
    """en: {n: bytes} -> new file"""
    en = en or {}
    out = bytearray()
    for n, (who, raw) in enumerate(parse()):
        t = en.get(n, raw)
        assert len(t) < TEXT_MAX and readable(t, n in en), n
        out += bytes((who,)) + t + b'\n'
    out += b"\xff\n"
    assert len(out) <= SIZE, 'DMES.E2 %d bytes > %d (buffer size not known)' % (len(out), SIZE)
    return bytes(out)


if __name__ == '__main__':
    assert rebuild() == load()
    print('%d entries, rebuild identical' % len(parse()))
