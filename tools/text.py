"""English encoder and wrapper for the chapter text (snr.py).

English (tl/): plain ASCII; '\\n' forces a line break, a blank line ('\\n\\n') starts a new page.
The game pages by itself every PAGE lines (Japanese pads pages with full-width-space lines; the
opening bracket 「『（ of each Japanese page is decoration, not a code). We pad with ' ' lines.

Kinds (the plain kind is taken from the Japanese entry, see kind_of):
  talk    speech in the talk box: 29 columns x 3 lines, LF
  narr    narration / multi-line caption (Japanese uses CR LF): 36 columns x 6 lines, CR LF
  choice  menu, one option per '\\n' line, numbered '1. ' ... by the encoder, CR LF, not wrapped
  plain   one line (titles, places, captions), not wrapped
  npc     town NPC line (IP.E2): NPC_COLS columns x 3 lines, LF (seen: 36 columns, Xinye hall)
  dmes    retreat line (DMES.E2): one box of 32 columns x 3 lines; lines end with the reader's line-break
          byte DMES_BREAK at a position the reader checks (it steps 2 bytes, 1 after a break; dmes.py)
Widths are pixels of our proportional font (vwf.width). Typographic quotes, dashes and
ellipses are folded to ASCII; '%' and '\\' (other than \\n) are refused.
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import vwf

CHAR_PX = 8
NPC_COLS = 36
DMES_COLS, DMES_LINES = 29, 3          # the talk box (seen in battle, session 13: 32 overflowed)
DMES_BREAK = 0x01                        # build.py patches the reader's break byte (was 0x73) to this
WIDTH = {'talk': 29 * CHAR_PX, 'narr': 36 * CHAR_PX, 'choice': 29 * CHAR_PX, 'plain': 36 * CHAR_PX,
         'npc': NPC_COLS * CHAR_PX, 'dmes': DMES_COLS * CHAR_PX}
PAGE = {'talk': 3, 'narr': 6, 'choice': 0, 'plain': 0, 'npc': 3, 'dmes': DMES_LINES}
EOL = {'talk': '\n', 'narr': '\r\n', 'choice': '\r\n', 'plain': '\r\n', 'npc': '\n', 'dmes': ''}
TEXT_MAX = 0x400                         # one speech / plain entry: 0x400-B output buffers
FOLD = {'‘': "'", '’': "'", '“': '"', '”': '"', '—': '--', '–': '-', '…': '...', ' ': ' '}
CHOICE = re.compile(r'^[一二三四五六七八九]．')


def pixels(s, kind=None):
    return vwf.width(s)


def kind_of(jp, talk=False):
    """kind of an entry from its Japanese display form (snr.show)"""
    if talk:
        return 'talk'
    if '<0d>' not in jp:
        return 'plain'
    return 'choice' if CHOICE.match(jp) else 'narr'


def fold(en):
    return ''.join(FOLD.get(c, c) for c in en)


def check(en, kind='talk'):
    """-> list of problems with an English segment"""
    errs = []
    s = fold(en)
    bad = sorted(set(c for c in s if not ' ' <= c <= '~'))
    if bad:
        errs.append('non-ASCII characters %r' % ''.join(bad))
    if re.search(r'%|\\(?!n)', s):
        errs.append('reserved character (% or \\ other than \\n)')
    if kind in ('plain', 'choice'):
        for ln in lines(s, kind):
            if pixels(ln, kind) > WIDTH[kind]:
                errs.append('%s line too wide (%d > %d px): %r' % (kind, pixels(ln, kind), WIDTH[kind], ln))
        if kind == 'plain' and '\\n' in s:
            errs.append('line break in a one-line entry')
    if kind == 'narr':
        for p in s.split('\\n\\n'):
            n = len(lines(p, kind))
            if n > PAGE[kind] and n % PAGE[kind] == 1:
                errs.append('narration paragraph of %d lines: the last line gets a page of its own '
                            '(shorten it or split it with \\n\\n)' % n)
    if kind == 'dmes':
        if '\\n\\n' in s:
            errs.append('retreat lines have one page (no \\n\\n)')
        elif len(lines(s, kind)) > DMES_LINES:
            errs.append('retreat line of %d lines (max %d)' % (len(lines(s, kind)), DMES_LINES))
    if not errs and len(encode(en, kind)) >= TEXT_MAX:
        errs.append('longer than %d bytes' % (TEXT_MAX - 1))
    return errs


def _wrap(words, width, kind=None):
    out, line = [], []
    for w in words:
        if line and pixels(' '.join(line + [w]), kind) > width:
            out.append(line)
            line = [w]
        else:
            line.append(w)
    out.append(line)
    return [' '.join(x) for x in out]


SENTENCE = re.compile(r'(?<=[.!?])[)"\']*(?=\s+[^a-z\s])')
SMART = ('talk', 'npc', 'narr')         # paragraphs longer than a page: page breaks at sentence ends


def _pages(n, page):
    return -(-n // page)


def _paginate(words, width, kind, page):
    """wrap a paragraph; when it spans pages, start a page at a sentence end where that does not add a
    page to the sentences gathered so far (the game would otherwise page mid-sentence)"""
    plain = _wrap(words, width, kind)
    if len(plain) <= page:
        return plain
    text = ' '.join(words)
    cut = [m.end() for m in SENTENCE.finditer(text)]
    sents = [x.split() for x in (text[a:b] for a, b in zip([0] + cut, cut + [len(text)])) if x.split()]
    out, cur = [], []
    for w in sents:
        if cur and _pages(len(_wrap(cur + w, width, kind)), page) > _pages(len(_wrap(cur, width, kind)), page):
            got = _wrap(cur, width, kind)
            out += got + [' '] * (-len(got) % page)
            cur = []
        cur += w
    out += _wrap(cur, width, kind)
    return out if _pages(len(out), page) <= _pages(len(plain), page) else plain


def lines(en, kind):
    """one tl record -> display lines (pad lines ' ')"""
    s = fold(en)
    if kind == 'choice':
        return ['%d. %s' % (i + 1, p.strip()) for i, p in enumerate(s.split('\\n')) if p.strip()]
    if kind == 'plain':
        return [' '.join(s.split())]
    out, page = [], PAGE[kind]
    for p in s.split('\\n'):
        words = p.split()
        if not words:
            out += [' '] * (-len(out) % page)
            continue
        if kind in SMART and not len(out) % page:
            out += _paginate(words, WIDTH[kind], kind, page)
        else:
            out += _wrap(words, WIDTH[kind], kind)
    while out and out[-1] == ' ':
        out.pop()
    return out


def encode(en, kind):
    ls = lines(en, kind)
    if kind == 'dmes':                   # break bytes and the end at positions the reader checks
        out, check = b'', 0
        for i, x in enumerate(ls):
            out += x.encode('ascii')
            if (len(out) - check) % 2:
                out += b' '
            if i < len(ls) - 1:
                out += bytes((DMES_BREAK,))
                check = len(out)
        return out
    return EOL[kind].join(ls).encode('ascii')
