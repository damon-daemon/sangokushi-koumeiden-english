"""Redraw the Japanese graphics in English at build time (own fonts; no Koei pixels stored).

- SNR/MARK.BIN TIM 2 (system sheet, 4bpp 256x256 px, VRAM (960, 0)): stat plates at rows 112-126,
  8 cells of 24 px (攻撃 防御 耐久 策略 知力 武力 統率 経験) + 4 of 16 px (移 速 金 Lv; Lv kept).
- NL.BIN TIM 15 (title config, blue, with 難易度) and TIM 16 (battle config, green): labels redrawn on a clean
  background: TIM 17 is TIM 16 without text; for TIM 15 it is TIM 17 histogram-matched to TIM 15's colours.
  Options keep their JP left edge (the cursor/highlight positions).

  python tools/gfx.py preview OUTDIR     before/after PNGs
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import pixfont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = 'SNR/MARK.BIN'
NL = 'NL.BIN'


# ---------------------------------------------------------------- TIM helpers

def tims(d):
    """[(offset, pixel offset, w px, h, bpp)] of back-to-back TIMs"""
    out, o = [], 0
    while o + 8 <= len(d):
        m, f = struct.unpack_from('<2I', d, o)
        if m != 0x10:
            break
        p = o + 8
        if f & 8:
            p += struct.unpack_from('<I', d, p)[0]
        ln, x, y, w, h = struct.unpack_from('<I4H', d, p)
        out.append((o, p + 12, w * (4 if f & 3 == 0 else 2), h, 4 if f & 3 == 0 else 8, o + 8 + 12))
        o = (p + ln + 3) & ~3
    return out


class Img4:
    """4bpp pixel view into a bytearray"""

    def __init__(self, buf, off, w, h):
        self.b, self.o, self.w, self.h = buf, off, w, h

    def get(self, x, y):
        v = self.b[self.o + y * (self.w // 2) + x // 2]
        return v >> 4 if x & 1 else v & 15

    def put(self, x, y, i):
        a = self.o + y * (self.w // 2) + x // 2
        v = self.b[a]
        self.b[a] = (v & 0x0f) | (i << 4) if x & 1 else (v & 0xf0) | i


# ---------------------------------------------------------------- fonts

MINI = r"""
M 5
#...#
##.##
#.#.#
#.#.#
#...#
#...#
#...#
O 3
.#.
#.#
#.#
#.#
#.#
#.#
.#.
V 3
#.#
#.#
#.#
#.#
#.#
#.#
.#.
S 3
.##
#..
#..
.#.
..#
..#
##.
P 3
##.
#.#
#.#
##.
#..
#..
#..
D 3
##.
#.#
#.#
#.#
#.#
#.#
##.
G 3
.##
#..
#..
#.#
#.#
#.#
.##
L 3
#..
#..
#..
#..
#..
#..
###
"""


def mini():
    """7-row caps for the 16-px plates: {char: (rows as bit lists, width)}"""
    g, lines = {}, [s for s in MINI.strip().split('\n')]
    for i in range(0, len(lines), 8):
        c, w = lines[i].split()
        g[c] = ([[ch == '#' for ch in r] for r in lines[i + 1:i + 8]], int(w))
    return g


def pix_bits(s, g=None):
    """pixfont text -> (set of (x, y) ink, width); y 0 = cap top"""
    g = g or pixfont.glyphs()
    ink, x = set(), 0
    for c in s:
        if c == ' ':
            x += pixfont.SPACE_ADV
            continue
        rows, adv = g[c]
        for r, bits in enumerate(rows):
            for b in range(8):
                if bits & (0x80 >> b):
                    ink.add((x + b, r))
        x += adv
    return ink, x - pixfont.SPACING


def mini_bits(s):
    g, ink, x = mini(), set(), 0
    for c in s:
        rows, w = g[c]
        for r, row in enumerate(rows):
            for b, on in enumerate(row):
                if on:
                    ink.add((x + b, r))
        x += w + 1
    return ink, x - 1


# ---------------------------------------------------------------- MARK.BIN stat plates

PLATE_Y0, PLATE_Y1 = 113, 125             # interior rows (112 / 126 = texture edges, 127 = separator)
PLATE_FILL, PLATE_EDGE, PLATE_INK, PLATE_HI = 6, 5, 1, 7
# (x, width incl. separator column, English, font); 攻撃 防御 耐久 策略 知力 武力 統率 経験 移 速 金 (Lv kept); 金 = gold: 'GOLD' is 15 px > 13
PLATES = [(0, 24, 'Atk'), (24, 24, 'Def'), (48, 24, 'HP'), (72, 24, 'SP'), (96, 24, 'Int'), (120, 24, 'Str'),
          (144, 24, 'Ldr'), (168, 24, 'Exp'), (192, 16, 'MOV'), (208, 16, 'SPD'), (224, 16, 'G')]


def plates(data):
    """MARK.BIN -> the same with English stat plates"""
    u = bytearray(data)
    t = tims(u)[2]
    im = Img4(u, t[1], t[2], t[3])
    for x0, w, s in PLATES:
        small = w == 16
        lo, hi = (x0 + 1, x0 + 13) if small else (x0, x0 + 22)     # interior columns
        for y in range(PLATE_Y0, PLATE_Y1 + 1):
            for x in range(lo, hi + 1):
                im.put(x, y, PLATE_EDGE if x == x0 and not small else PLATE_FILL)
        ink, tw = mini_bits(s) if small else pix_bits(s)
        assert tw <= hi - lo + 1, s
        ox = lo + (hi - lo + 1 - tw + 1) // 2
        oy = PLATE_Y0 + (4 if small else 2)
        pts = {(ox + a, oy + b) for a, b in ink}
        for x, y in pts:                    # emboss as Koei's Lv plate: highlight up and left of the ink
            for hx, hy in ((x - 1, y), (x, y - 1)):
                if (hx, hy) not in pts and lo <= hx <= hi and PLATE_Y0 <= hy <= PLATE_Y1:
                    im.put(hx, hy, PLATE_HI)
        for x, y in pts:
            im.put(x, y, PLATE_INK)
    return bytes(u)


# ---------------------------------------------------------------- NL.BIN config screens

CFG_TITLE, CFG_BATTLE, CFG_CLEAN = 15, 16, 17
TEXT_IDX = (1, 2, 3, 14)                 # outline/shadow 1, label 2, option 3, label outline 14
LABEL_X0, LABEL_X1 = 22, 96              # label column (labels centred in it)
# rows: label, [(option JP left x, English)]; TIM 15 rows start y 17 pitch 22, TIM 16 rows y 17 pitch 24
OPT3 = (121, 185, 249)
CFG_ROWS = [
    ('Difficulty', list(zip(OPT3, ('Easy', 'Normal', 'Hard')))),
    ('Sound', [(122, 'Stereo'), (217, 'Mono')]),
    ('Menus', [(121, 'D-Pad'), (217, 'Row')]),
    ('Subtitles', [(123, 'On'), (218, 'Off')]),
    ('Animation', list(zip(OPT3, ('Full', 'Short', 'Off')))),
    ('Battle Info', [(122, 'Show'), (217, 'Hide')]),
    ('Confirm Wait', [(122, 'On'), (219, 'Off')]),
    ('Enemy Moves', [(122, 'Show'), (217, 'Skip')]),
]
COLOURS = list(zip((121, 160, 201, 241, 280), ('Red', 'Blue', 'Green', 'Purple', 'Black')))
CFG_COLOUR_LABELS = ('Ally Text', 'Foe Text')


def _clean_title(nl, ts):
    """TIM 17's texture with TIM 15's colours: map indices by brightness quantiles"""
    def idx(t):
        return [(nl[t[1] + i // 2] >> (4 * (i & 1))) & 15 for i in range(t[2] * t[3])]

    def pal(t):
        return struct.unpack_from('<16H', nl, t[5])

    def lum(v):
        return 2 * (v & 31) + 5 * ((v >> 5) & 31) + ((v >> 10) & 31)

    src, dst = idx(ts[CFG_CLEAN]), idx(ts[CFG_TITLE])
    sp, dp = pal(ts[CFG_CLEAN]), pal(ts[CFG_TITLE])
    sbg = sorted(range(4, 14), key=lambda i: lum(sp[i]))
    dbg = sorted(range(4, 14), key=lambda i: lum(dp[i]))
    sc = [src.count(i) for i in range(16)]
    dc = [sum(1 for v in dst if v == i) for i in range(16)]
    # cumulative share of each source level -> destination level at the same quantile
    total_s, total_d = sum(sc[i] for i in sbg), sum(dc[i] for i in dbg)
    m, acc = {}, 0
    for i in sbg:
        mid = (acc + sc[i] / 2) / total_s
        acc += sc[i]
        a2, pick = 0, dbg[-1]
        for j in dbg:
            a2 += dc[j]
            if a2 / total_d >= mid:
                pick = j
                break
        m[i] = pick
    return [m.get(v, dbg[0]) for v in src]


def _draw(im, ink, ox, oy, fg, shadow, outline):
    pts = {(ox + a, oy + b) for a, b in ink}
    sh = {(x + 1, y + 1) for x, y in pts} - pts
    if outline is not None:
        allp = pts | sh
        ring = {(x + dx, y + dy) for x, y in allp for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - allp
        for x, y in ring:
            im.put(x, y, outline)
    for x, y in sh:
        im.put(x, y, shadow)
    for x, y in pts:
        im.put(x, y, fg)


def config(nl):
    """NL.BIN -> the same with English config screens"""
    u = bytearray(nl)
    ts = tims(u)
    g = pixfont.glyphs()
    clean16 = [(u[ts[CFG_CLEAN][1] + i // 2] >> (4 * (i & 1))) & 15 for i in range(320 * 240)]
    clean15 = _clean_title(u, ts)
    for n, clean, rows, y0, pitch in ((CFG_TITLE, clean15, CFG_ROWS, 17, 22),
                                      (CFG_BATTLE, clean16, CFG_ROWS[1:], 17, 24)):
        t = ts[n]
        im = Img4(u, t[1], t[2], t[3])
        for y in range(240):
            for x in range(320):
                im.put(x, y, clean[y * 320 + x])
        lines = [(lab, opts) for lab, opts in rows] + [(CFG_COLOUR_LABELS[0], COLOURS), (CFG_COLOUR_LABELS[1], COLOURS)]
        for r, (lab, opts) in enumerate(lines):
            y = y0 + r * pitch + 2
            if n == CFG_TITLE and r == len(lines) - 1:
                y -= 6                          # JP: the two colour rows are 16 px apart on the title screen
            ink, w = pix_bits(lab, g)
            assert w <= LABEL_X1 - LABEL_X0, lab
            _draw(im, ink, LABEL_X0 + (LABEL_X1 - LABEL_X0 - w) // 2, y, 2, 1, 14)
            for i, (x, s) in enumerate(opts):
                ink, w = pix_bits(s, g)
                nxt = opts[i + 1][0] if i + 1 < len(opts) else 318
                assert x + w < nxt - 2, s
                _draw(im, ink, x, y, 3, 1, None)
    return bytes(u)


# ---------------------------------------------------------------- build / preview

def build(files):
    """{iso path: bytes} (clean or already rebuilt) -> adds the redrawn files"""
    return {MARK: plates(files[MARK]), NL: config(files[NL])}


def _png(data, t, path, scale=1):
    from PIL import Image
    pal = struct.unpack_from('<16H', data, t[5])
    c = [((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3) for v in pal]
    im = Img4(bytearray(data), t[1], t[2], t[3])
    img = Image.new('RGB', (t[2], t[3]))
    img.putdata([c[im.get(x, y)] for y in range(t[3]) for x in range(t[2])])
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), 0)
    img.save(path)


def preview(outdir):
    os.makedirs(outdir, exist_ok=True)
    mark = open(os.path.join(ROOT, 'extract', MARK), 'rb').read()
    nl = open(os.path.join(ROOT, 'extract', NL), 'rb').read()
    new = build({MARK: mark, NL: nl})
    for tag, d in (('old', mark), ('new', new[MARK])):
        _png(d, tims(d)[2], os.path.join(outdir, 'mark_%s.png' % tag), 3)
    for tag, d in (('old', nl), ('new', new[NL])):
        for n in (CFG_TITLE, CFG_BATTLE):
            _png(d, tims(d)[n], os.path.join(outdir, 'config%d_%s.png' % (n, tag)), 2)


if __name__ == '__main__':
    if sys.argv[1:2] == ['preview']:
        preview(sys.argv[2])
    else:
        print(__doc__)
