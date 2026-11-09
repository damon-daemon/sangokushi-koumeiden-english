"""Name tokens: full English names in fields too small for them.

Name fields the game copies into fixed-size RAM records:
  officers  EXE table 0x800a5a40, 525 x 0x1c {u32 name, u32 reading, data}; 0x8002e66c / 0x8002e848 copy
            name[6] to the person record (0x80108410 + id * 0x38) +6 and the reading[8] to +13
  npcs      SNR/BAKDATA.E2 0x000, 256 x 9 B (name 8, kind): town NPC labels (0x8002ee18 -> 16-B records)
  items     SNR/BAKDATA.E2 0x900, 255 x 16 B (name 10 + NUL, data) (0x800209ac -> 0x14-B records)
  places    EXE 0x800a4948 and 0x800a4c08, 64 x 11 B (name 8 + NUL, x, y) (0x80022000 -> 12-B records)
  battles   HEX/HEXZ.BIN entry 55 (EXE offset table 0x800abeac; 0x6239c-0x6263c): battle names, SJIS lines
            ending CR LF; 0x80065e04 copies 0x29e bytes, then line n (0x8013207e) 2-byte characters while the
            lead is >= 0x80 (ASCII would be cut: a token fits). The build writes one token per line.

Each name field gets a 2-byte token instead of the name:

    lead 0xf1 + (n >> 7), trail 0x80 | (n & 0x7f)      (0xf0 = the gaiji codes, kept)

n < 525: officer n (the copy routines are patched to write the token; the English is the officer table's
name string, which progstr.py already translated and moved). n >= 525: entry n - 525 of TABLE, a u32
pointer per distinct English string (tl/names/<kind>.json, rows {"id", "en"}), stored with the strings in
the level-1 kanji of the 16x16 font (NAMES .. build.STRINGS; Japanese left that uses them draws garbage).

The token looks like one 2-byte character to everything that counts bytes. The putchar 0x80022e50 calls
the glyph routine 0x8002330c in one place (0x80023168); that call goes to `glyph` here, which for a token
prints the English with the string printer 0x80023410 and steps the column back by the 2-byte advance
putchar adds afterwards. The message formatter's %s (0x8003ce1c, message boxes sized by the longest line in
bytes) copies the argument through `expand` (tokens -> English), so box widths count the English name.
The officer reading at +13 (half-width kana, officer screen) is blanked. `vstrlen` (vwf.py) replaces strlen where a line is placed from its length (STRLEN_CALLS).

usage:
    tokens.py show KIND      index, Japanese, English (KIND: npcs items places battles)
    tokens.py check
"""
import json, os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, snr, text, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL_NAMES = os.path.join(ROOT, 'tl', 'names')
BAKDATA = 'SNR/BAKDATA.E2'
OFFICERS, OFFICER_COUNT, OFFICER_STRIDE = 0x800a5a40, 525, 0x1c
TOKEN, LEADS = 0xf1, 12                  # leads 0xf1-0xfc (putchar takes 0xe0-0xfc as SJIS leads)
GLYPH, PUTS, GLYPH_CALL = 0x8002330c, 0x80023410, 0x80023168
FMT_S, STRLEN = 0x8003cefc, 0x80094320   # message formatter's %s: jal strcat; jal strlen
NAMES = 0x800b4f2c                       # level-1 kanji glyphs (SJIS 0x88a2 ..) up to build.STRINGS
COPIES = [  # (start of the name loop, first instruction after the reading loop, register with the index)
    (0x8002e69c, 0x8002e744, 'a1'),
    (0x8002e87c, 0x8002e924, 'a1'),
]
# kind: (where, [table bases], count, stride, name field bytes incl. the NUL the copy writes)
KINDS = {
    'npcs': (BAKDATA, [0x000], 256, 9, 8),
    'items': (BAKDATA, [0x900], 255, 16, 10),
    'places': ('EXE', [0x800a4948, 0x800a4c08], 64, 11, 8),
}
EXE_BASE = 0x80010000 - 0x800
HEXZ, BATTLES, BATTLES_END, BATTLE_COUNT = 'HEX/HEXZ.BIN', 0x6239c, 0x6263c, 50
ALL_KINDS = list(KINDS) + ['battles']
# jal strlen whose result places a line in 8-px cells -> jal vstrlen (vwf.py: cells of the widest line in
# pixels, a token counting as its English)
STRLEN_CALLS = [
    0x80040e9c,   # battle banner "<unit> Move/Attack/Strat" (0x80040d24: sprintf "%s %s", col = 20 - len / 2)
    0x8003d0bc,   # caption box (message box mode 3, 0x8003d0a4): col = 20 - len / 2, width len * 8 + 32
    0x800234c4,   # centred printer 0x800234a4(ctx, width, text)
    0x8001cbcc, 0x8001cbf0, 0x8001e3d4, 0x8001e404, 0x8001e590, 0x8001e5c0,   # right-aligned: col = x / 8 - len
    # (ring-menu labels 0x80030060 0x80030524 0x8005f2c4 0x8005f714: vwf.patch centres them to the pixel)
    0x80058c14, 0x800624b4,   # centred in 8 cells: col = (8 - len) / 2
]


def token(n):
    assert 0 <= n < LEADS << 7
    return bytes([TOKEN + (n >> 7), 0x80 | (n & 0x7f)])


def _off(where, base):
    return base - EXE_BASE if where == 'EXE' else base


def battle_lines(hexz):
    return hexz[BATTLES:BATTLES_END].split(b'\r\n')


def jp_names(kind, exe, bak, hexz=None):
    if kind == 'battles':
        return [snr.show(l, True) for l in battle_lines(hexz)[:BATTLE_COUNT]]
    where, bases, count, stride, field = KINDS[kind]
    d = exe if where == 'EXE' else bak
    o = _off(where, bases[0])
    return [snr.show(d[o + i * stride:o + i * stride + field].split(b'\0')[0], True) for i in range(count)]


def rows(kind):
    p = os.path.join(TL_NAMES, kind + '.json')
    if not os.path.exists(p):
        return {}
    return {r['id']: r['en'] for r in json.load(open(p, encoding='utf-8'))}


def hook(table):
    return [
        'tokptr:',                           # a3 = token code -> v0 = English string (t0, t1)
        ('srl', 't0', 'a3', 8),
        ('addiu', 't0', 't0', -TOKEN),
        ('sll', 't0', 't0', 7),
        ('andi', 't1', 'a3', 0x7f),
        ('or', 't0', 't0', 't1'),            # n
        ('sltiu', 't1', 't0', OFFICER_COUNT),
        ('beqz', 't1', 'table'),
        ('sll', 't1', 't0', 5),              # officer: name pointer at OFFICERS + n * 0x1c
        ('sll', 't0', 't0', 2),
        ('subu', 't0', 't1', 't0'),
        ('lui', 't1', asm.hi(OFFICERS)),
        ('addu', 't1', 't1', 't0'),
        ('lw', 'v0', asm.lo(OFFICERS), 't1'),
        ('jr', 'ra'),
        ('nop',),
        'table:',
        ('sll', 't0', 't0', 2),              # TABLE[n - OFFICER_COUNT]
        ('lui', 't1', asm.hi(table - 4 * OFFICER_COUNT)),
        ('addu', 't1', 't1', 't0'),
        ('lw', 'v0', asm.lo(table - 4 * OFFICER_COUNT), 't1'),
        ('jr', 'ra'),
        ('nop',),

        'glyph:',                            # putchar's glyph call (ctx, col, y, code)
        ('ori', 't0', 'zero', TOKEN << 8),   # (sltiu would sign-extend 0xf100)
        ('sltu', 't0', 'a3', 't0'),
        ('beqz', 't0', 'tok'),
        ('nop',),
        ('j', 'vglyph'),                     # vwf.py (the game's glyph routine for non-ASCII)
        ('nop',),
        'tok:',
        ('addiu', 'sp', 'sp', -0x20),
        ('sw', 'ra', 0x1c, 'sp'),
        ('sw', 's0', 0x18, 'sp'),
        ('sw', 's1', 0x14, 'sp'),
        ('sw', 's2', 0x10, 'sp'),
        ('addu', 's0', 'a0', 'zero'),
        ('jal', 'vslot'),                    # the run the name continues (or starts)
        ('sw', 'a3', 0x0c, 'sp'),
        ('addu', 's1', 'v0', 'zero'),
        ('lw', 's2', vwf.S_BCOL, 'v0'),
        ('jal', 'tokptr'),
        ('lw', 'a3', 0x0c, 'sp'),
        ('addu', 'a1', 'v0', 'zero'),
        ('jal', PUTS),
        ('addu', 'a0', 's0', 'zero'),
        ('addiu', 's2', 's2', 2),            # the token's 2 bytes in the fixed-width layout
        ('sw', 's2', vwf.S_BCOL, 's1'),
        ('lbu', 't0', 0, 's0'),              # putchar adds 2 columns (4 if double width) after us
        ('lw', 't1', 4, 's0'),
        ('andi', 't0', 't0', 0x40),
        ('srl', 't0', 't0', 5),
        ('addiu', 't0', 't0', 2),
        ('subu', 't1', 't1', 't0'),
        ('sw', 't1', 4, 's0'),
        ('addu', 'v0', 'zero', 'zero'),
        ('lw', 'ra', 0x1c, 'sp'),
        ('lw', 's0', 0x18, 'sp'),
        ('lw', 's1', 0x14, 'sp'),
        ('lw', 's2', 0x10, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x20),

        'expand:',                           # strcpy(a0, a1) with tokens replaced by their English
        ('addiu', 'sp', 'sp', -0x18),
        ('sw', 'ra', 0x14, 'sp'),
        ('addu', 't2', 'a0', 'zero'),
        ('addu', 't3', 'a1', 'zero'),
        'x_loop:',
        ('lbu', 't4', 0, 't3'),
        ('nop',),
        ('beqz', 't4', 'x_end'),
        ('sltiu', 't5', 't4', TOKEN),
        ('beqz', 't5', 'x_tok'),
        ('sltiu', 't5', 't4', 0x80),
        ('bnez', 't5', 'x_one'),
        ('sltiu', 't5', 't4', 0xa0),
        ('bnez', 't5', 'x_two'),
        ('sltiu', 't5', 't4', 0xe0),
        ('beqz', 't5', 'x_two'),
        ('nop',),
        'x_one:',                            # ASCII, half-width kana
        ('sb', 't4', 0, 't2'),
        ('addiu', 't3', 't3', 1),
        ('b', 'x_loop'),
        ('addiu', 't2', 't2', 1),
        'x_two:',                            # SJIS pair
        ('lbu', 't5', 1, 't3'),
        ('sb', 't4', 0, 't2'),
        ('sb', 't5', 1, 't2'),
        ('addiu', 't3', 't3', 2),
        ('b', 'x_loop'),
        ('addiu', 't2', 't2', 2),
        'x_tok:',
        ('lbu', 't5', 1, 't3'),
        ('sll', 't4', 't4', 8),
        ('jal', 'tokptr'),
        ('or', 'a3', 't4', 't5'),
        'x_copy:',
        ('lbu', 't4', 0, 'v0'),
        ('nop',),
        ('beqz', 't4', 'x_next'),
        ('sb', 't4', 0, 't2'),
        ('addiu', 'v0', 'v0', 1),
        ('b', 'x_copy'),
        ('addiu', 't2', 't2', 1),
        'x_next:',
        ('b', 'x_loop'),
        ('addiu', 't3', 't3', 2),
        'x_end:',
        ('sb', 'zero', 0, 't2'),
        ('lw', 'ra', 0x14, 'sp'),
        ('nop',),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x18)] + vwf.lines('tokptr')


def copy_patch(cont, reg):
    """name loop + reading loop -> token at +6, empty reading at +13"""
    return [
        ('srl', 'v0', reg, 7),
        ('addiu', 'v0', 'v0', TOKEN),
        ('sb', 'v0', 6, 's0'),
        ('andi', 'v0', reg, 0x7f),
        ('ori', 'v0', 'v0', 0x80),
        ('sb', 'v0', 7, 's0'),
        ('sb', 'zero', 8, 's0'),
        ('j', cont),
        ('sb', 'zero', 0xd, 's0')]


def strings_blob(base, limit):
    """-> (blob at base: TABLE then the strings, {English: n}); TABLE = u32 per distinct string"""
    ens = []
    for kind in ALL_KINDS:
        for i, en in sorted(rows(kind).items()):
            if en != '-' and en not in ens:
                ens.append(en)
    assert OFFICER_COUNT + len(ens) <= LEADS << 7, 'too many names'
    table = bytearray(4 * len(ens))
    blob, at = bytearray(), base + len(table)
    for k, en in enumerate(ens):
        struct.pack_into('<I', table, 4 * k, at + len(blob))
        blob += en.encode('ascii') + b'\0'
    out = table + blob
    assert base + len(out) <= limit, 'names: %d bytes, room %d' % (len(out), limit - base)
    return out, {en: OFFICER_COUNT + k for k, en in enumerate(ens)}


def patch_fields(exe, bak, numbers):
    """write the tokens into the name fields (EXE bytearray, BAKDATA bytearray)"""
    for kind, (where, bases, count, stride, field) in KINDS.items():
        d = exe if where == 'EXE' else bak
        for i, en in rows(kind).items():
            if en == '-':
                continue
            for b in bases:
                o = _off(where, b) + i * stride
                d[o:o + field] = token(numbers[en]).ljust(field, b'\0')


def patch_hexz(hexz, numbers):
    """battle-name lines -> one token each (same entry size, zero padded)"""
    lines = battle_lines(hexz)
    en = rows('battles')
    for i in range(BATTLE_COUNT):
        if en.get(i, '-') != '-':
            lines[i] = token(numbers[en[i]])
    blob = b'\r\n'.join(lines)
    n = BATTLES_END - BATTLES
    assert len(blob) <= n
    out = bytearray(hexz)
    out[BATTLES:BATTLES_END] = blob.ljust(n, b'\0')
    return out


def patch(exe, bak, at, put, expect, peek, limit):
    """hook code at `at` (pool), names at NAMES .. limit; returns the end of the code"""
    blob, numbers = strings_blob(NAMES, limit)
    put(exe, NAMES, blob)
    assert NAMES + len(blob) <= vwf.DATA and vwf.DATA_END <= limit
    put(exe, vwf.DATA, vwf.data())
    patch_fields(exe, bak, numbers)
    lines = hook(NAMES)
    code = asm.assemble(at, lines)
    lab = asm.labels(at, lines)
    put(exe, at, code)
    expect(exe, GLYPH_CALL, [0x0c000000 | (GLYPH >> 2 & 0x3ffffff)])
    put(exe, GLYPH_CALL, asm.assemble(GLYPH_CALL, [('jal', lab['glyph'])]))
    # message formatter 0x8003ce1c, %s: strcat(out, arg); out += strlen(arg) -> expand(out, arg);
    # out += strlen(out), so the box width (longest line in bytes) counts the English name
    expect(exe, FMT_S, [0x0c01c1d1, 0x02002821, 0x0c0250c8, 0x02002021])
    put(exe, FMT_S, asm.assemble(FMT_S, [('jal', lab['expand']), ('addu', 'a1', 's0', 'zero'),
                                         ('jal', STRLEN), ('addu', 'a0', 's1', 'zero')]))
    vwf.patch(exe, lab, put, expect)
    for a in STRLEN_CALLS:
        expect(exe, a, [0x0c000000 | (STRLEN >> 2 & 0x3ffffff)])
        put(exe, a, asm.assemble(a, [('jal', lab['vstrlen'])]))
    for start, cont, reg in COPIES:
        # both loops start: lw a1|a0, 0(t0|s1); addiu a3|a1, s0, 6
        assert peek(exe, start + 4, 1)[0] in (0x26070006, 0x26050006), hex(start)
        put(exe, start, asm.assemble(start, copy_patch(cont, reg)))
    print('names: %d strings, %d bytes at %#x' % (len(numbers), len(blob), NAMES))
    return at + len(code)


def clean():
    sys.path.insert(0, os.path.dirname(__file__))
    import iso
    exe = open(os.path.join(ROOT, 'extract', iso.EXE_NAME), 'rb').read()
    bak = open(os.path.join(ROOT, 'extract', BAKDATA), 'rb').read()
    hexz = open(os.path.join(ROOT, 'extract', HEXZ), 'rb').read()
    return exe, bak, hexz


def check():
    exe, bak, hexz = clean()
    errs = []
    for kind in ALL_KINDS:
        count = BATTLE_COUNT if kind == 'battles' else KINDS[kind][2]
        en = rows(kind)
        jp = jp_names(kind, exe, bak, hexz)
        errs += ['%s %d: no row' % (kind, i) for i in range(count) if i not in en and jp[i]]
        for i, e in en.items():
            if not 0 <= i < count:
                errs.append('%s %d: no such record' % (kind, i))
            elif e != '-':
                errs += ['%s %d: %s' % (kind, i, x) for x in text.check(e, 'plain')]
                if not e.isascii():
                    errs.append('%s %d: not ASCII' % (kind, i))
    return errs


def main():
    a = sys.argv[1:]
    if a[:1] == ['show'] and len(a) == 2:
        exe, bak, hexz = clean()
        en = rows(a[1])
        for i, jp in enumerate(jp_names(a[1], exe, bak, hexz)):
            print('%d\t%s\t%s' % (i, jp, en.get(i, '')))
    elif a[:1] == ['check']:
        errs = check()
        print('\n'.join(errs + ['%d errors' % len(errs)]))
        sys.exit(1 if errs else 0)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
