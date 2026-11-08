"""Variable-width English: our proportional font (pixfont.py) and a pixel pen in the glyph routine.

The game draws text INTO VRAM: putchar 0x80022e50 calls the glyph routine 0x8002330c(ctx, col, y, code)
once (0x80023168, already hooked by tokens.py), which fetches a 1bpp glyph, expands it to 4bpp and
uploads one 8-px (16-px for 2-byte codes) cell with LoadImage at VRAM x 0x280 + px / 4. A cell upload
writes its background too, so proportional glyphs at any x would erase their left neighbour.

Here (`glyph` below, reached from tokens.py's hook for codes < 0x100): ASCII 0x20-0x7e draws in a *run*
per text context. A run keeps the pen in pixels and a 1bpp copy of the line drawn so far (RUN_ROWS rows of
LB bytes, row 0 always empty for the shadow). Each glyph is ORed into that copy at the pen, then the
4-px-aligned span from the pen to the new pen is expanded from the copy (foreground / background colours
0x800a53e4 / 0x800a53e8; shadow mode when ctx+0x34: colour ctx+0x20 where the pixel to the left or
up-left has ink, as the game's expander 0x800237a0) and uploaded with 0x8002324c. Then ctx col (+4) =
ceil(pen / 8) - 1 (putchar adds 1), so code that counts 8-px cells stays true and never sees text wider
than the Japanese layout.

A glyph continues the run of its ctx when y (+8) and col are what the run left; else the run restarts at
col * 8. SLOTS runs (by ctx) so interleaved boxes keep their pens. Other glyphs (kanji, half-width kana,
double width / vertical ctx flags 0x60, putchar flag 1) take the game's path and end the run.

Spaces are SPACE_ADV px. Padding (Eiketsuden's rule): a digit after spaces moves right so the spaces
count as digit width (all of them at the run start, else all but one word space), so right-aligned
"%3u" fields line up; another glyph after 2+ spaces (1+ at the run start) moves to its cell in the
fixed-width layout (bcol = col at the run start + bytes drawn; a name token counts its 2 bytes), so
menus padded with spaces ("  Yes    No") keep their columns. The upload starts where the spaces began.
The set-position routine 0x80022c20 ends the run of its ctx (a field placed right after a name is a new run).
The officer list's level and HP columns move 1 cell right (names get 8 cells).

  width(s) -> pixels (build-time wrapping, text.py); lines(...) -> asm for tokens.hook; DATA layout below.
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, pixfont

GLYPH, UPLOAD = 0x8002330c, 0x8002324c
CUT = 0x8003b870                   # message box line cutter (vcut)
CTX, SET_COLOUR, SET_POS, PRINTF, FMT_S = 0x8012ec74, 0x80022d3c, 0x80022c20, 0x80023520, 0x800dd7b0
MSG_WIDTH, MSG_TEXT = 0x8003d324, 0x8011fc3c
CUT_MAX = 0x50 - 4                 # line buffer 0x50 B (ESC copies 3)
TOKEN = 0xf1                       # tokens.TOKEN (name tokens: 0xf1xx-0xfcxx)
FG, BG = 0x800a53e4, 0x800a53e8
FONT_LEFT = 1                      # blank column left of each glyph (else text touches the box edge)
FONT_TOP = 2                       # pixfont rows 0-11 (cap 0, baseline 8) -> cell rows 2-13
SPACE_ADV = pixfont.SPACE_ADV
# data in the level-1 kanji of the 16x16 font (after tokens.NAMES' strings)
DATA = 0x800bb000
FONT = DATA                        # 95 glyphs x 16 rows (0x20-0x7e)
WIDTHS = FONT + 95 * 16            # 95 advances
SLOTS, LB, RUN_ROWS = 4, 64, 17    # 64 B = 512 px per row
HEAD = 0x20                        # ctx, y, ecol, pen, bcol, spaces, base px, lead
S_CTX, S_Y, S_ECOL, S_PEN, S_BCOL, S_SPACES, S_BASE, S_LEAD = range(0, 32, 4)
SLOT_SIZE = HEAD + LB * RUN_ROWS
RUNS = ((WIDTHS + 95 + 3) & ~3) + 4 # u32 round-robin counter, then the slots
RR = RUNS - 4
DATA_END = RUNS + SLOTS * SLOT_SIZE
CHUNK = 32                         # px per upload (4bpp buffer on the stack: 16 rows x 16 B)

_G = pixfont.glyphs()
DIGIT_ADV = 6
ADV = {c: (SPACE_ADV if c == ' ' else _G[c][1]) for c in map(chr, range(0x20, 0x7f))}


def width(s):
    """Pixel width of an ASCII line drawn as one run from a cell boundary (padding rules as the runtime)."""
    px, k, lead = 0, 0, True
    for i, c in enumerate(s):
        if c == ' ':
            px += SPACE_ADV
            k += 1
            continue
        if k:
            if c.isdigit():
                px += (DIGIT_ADV - SPACE_ADV) * (k if lead else k - 1)
            elif k >= 2 or lead:
                px = max(px, 8 * i)
        k, lead = 0, False
        px += ADV.get(c, 8)
    return px


def cells(s):
    return (width(s) + 7) // 8


def data():
    """bytes at DATA: font, widths (the slots are zeroed by the build: in the EXE image)"""
    out = bytearray()
    for c in map(chr, range(0x20, 0x7f)):
        rows = bytes(12) if c == ' ' else _G[c][0]
        assert not any(r & 1 for r in rows), 'glyph %r too wide' % c
        rows = bytes(r >> FONT_LEFT for r in rows)
        out += bytes(FONT_TOP) + rows + bytes(16 - FONT_TOP - len(rows))
    out += bytes(ADV[c] for c in map(chr, range(0x20, 0x7f)))
    out += bytes(DATA_END - DATA - len(out))
    return bytes(out)


def lines(tok_label):
    """asm listing; labels: vglyph (glyph routine replacement for codes < 0xf100), vslot, vstrlen"""
    H = lambda a: asm.hi(a)
    L = lambda a: asm.lo(a)
    return [
        'vslot:',                            # (a0 ctx, a1 col, a2 y) -> v0 slot, v1 1 if the run continues
        ('lui', 'v0', H(RUNS)),
        ('addiu', 'v0', 'v0', L(RUNS)),
        ('ori', 't0', 'zero', SLOTS),
        's_find:',
        ('lw', 't1', S_CTX, 'v0'),
        ('nop',),
        ('beq', 't1', 'a0', 's_have'),
        ('addiu', 't0', 't0', -1),
        ('bnez', 't0', 's_find'),
        ('addiu', 'v0', 'v0', SLOT_SIZE),
        ('lui', 't1', H(RR)),                # none: the next slot round robin
        ('lw', 't0', L(RR), 't1'),
        ('nop',),
        ('addiu', 't2', 't0', 1),
        ('sw', 't2', L(RR), 't1'),
        ('andi', 't0', 't0', SLOTS - 1),
        ('ori', 't1', 'zero', SLOT_SIZE),
        ('multu', 't0', 't1'),
        ('mflo', 't0'),
        ('lui', 'v0', H(RUNS)),
        ('addiu', 'v0', 'v0', L(RUNS)),
        ('b', 's_fresh'),
        ('addu', 'v0', 'v0', 't0'),
        's_have:',
        ('lw', 't1', S_Y, 'v0'),
        ('lw', 't2', S_ECOL, 'v0'),
        ('bne', 't1', 'a2', 's_fresh'),
        ('nop',),
        ('bne', 't2', 'a1', 's_fresh'),
        ('nop',),
        ('jr', 'ra'),
        ('ori', 'v1', 'zero', 1),
        's_fresh:',
        ('sw', 'a0', S_CTX, 'v0'),
        ('sw', 'a2', S_Y, 'v0'),
        ('sw', 'a1', S_ECOL, 'v0'),
        ('sll', 't0', 'a1', 3),
        ('sw', 't0', S_PEN, 'v0'),
        ('addiu', 't0', 't0', -8),
        ('sw', 't0', S_BASE, 'v0'),
        ('sw', 'a1', S_BCOL, 'v0'),
        ('sw', 'zero', S_SPACES, 'v0'),
        ('ori', 't0', 'zero', 1),
        ('sw', 't0', S_LEAD, 'v0'),
        ('addiu', 't0', 'v0', HEAD),         # clear the line copy
        ('addiu', 't1', 't0', LB * RUN_ROWS),
        's_clr:',
        ('sw', 'zero', 0, 't0'),
        ('addiu', 't0', 't0', 4),
        ('bne', 't0', 't1', 's_clr'),
        ('nop',),
        ('jr', 'ra'),
        ('addu', 'v1', 'zero', 'zero'),

        'vglyph:',                           # glyph(a0 ctx, a1 col, a2 y, a3 code), putchar flag at 0x10(sp)
        ('sltiu', 't0', 'a3', 0x20),
        ('bnez', 't0', 'v_orig'),
        ('sltiu', 't0', 'a3', 0x7f),
        ('beqz', 't0', 'v_orig'),
        ('lw', 't0', 0x10, 'sp'),
        ('lbu', 't1', 0, 'a0'),
        ('addiu', 't0', 't0', -1),
        ('beqz', 't0', 'v_orig'),
        ('andi', 't1', 't1', 0x60),
        ('bnez', 't1', 'v_orig'),
        ('nop',),
        ('addiu', 'sp', 'sp', -0x150),       # 0x10 args, 0x20.. 4bpp buffer 0x100, saved regs 0x120..
        ('sw', 'ra', 0x14c, 'sp'),
        ('sw', 's0', 0x148, 'sp'),
        ('sw', 's1', 0x144, 'sp'),
        ('sw', 's2', 0x140, 'sp'),
        ('sw', 's3', 0x13c, 'sp'),
        ('sw', 's4', 0x138, 'sp'),
        ('sw', 's5', 0x134, 'sp'),
        ('sw', 's6', 0x130, 'sp'),
        ('sw', 's7', 0x12c, 'sp'),
        ('addu', 's0', 'a0', 'zero'),
        ('addu', 's2', 'a3', 'zero'),
        ('jal', 'vslot'),
        ('addu', 's3', 'a2', 'zero'),        # s3 = y
        ('addu', 's1', 'v0', 'zero'),        # s1 = slot
        ('lw', 's4', S_PEN, 's1'),           # s4 = pen
        ('lw', 't9', S_BASE, 's1'),
        ('lw', 't1', S_SPACES, 's1'),        # spaces since the last other glyph
        ('lw', 't2', S_BCOL, 's1'),
        ('lw', 'v1', S_LEAD, 's1'),          # 1: no other glyph yet in this run
        ('addu', 's6', 's4', 'zero'),        # s6 = pen before padding (the upload starts there)
        ('subu', 't0', 's4', 't9'),          # line copy full: no drawing (cannot happen in the layouts)
        ('sltiu', 't0', 't0', LB * 8 - 2 * CHUNK),
        ('beqz', 't0', 'v_done'),
        ('addu', 's5', 's4', 'zero'),
        ('addiu', 't3', 's2', -0x20),
        ('bnez', 't3', 'v_ink'),
        ('addiu', 's5', 's4', SPACE_ADV),    # space: s5 = new pen
        ('b', 'v_adv'),
        ('addiu', 't1', 't1', 1),
        'v_ink:',
        ('beqz', 't1', 'v_nopad'),
        ('addiu', 't0', 's2', -0x30),
        ('sltiu', 't0', 't0', 10),
        ('beqz', 't0', 'v_snap'),
        ('nop',),
        ('bnez', 'v1', 'v_padk'),            # digit after spaces: padding spaces as wide as a digit
        ('nop',),                            # (all of them at the run start, else all but a word space)
        ('addiu', 't1', 't1', -1),
        'v_padk:',
        ('sll', 't0', 't1', 1),
        ('addu', 't0', 't0', 't1'),          # * (DIGIT - SPACE_ADV) = 3
        ('b', 'v_nopad'),
        ('addu', 's4', 's4', 't0'),
        'v_snap:',                           # other glyph after padding: to its cell in the fixed layout
        ('sltiu', 't0', 't1', 2),
        ('beqz', 't0', 'v_snap2'),
        ('nop',),
        ('beqz', 'v1', 'v_nopad'),
        ('nop',),
        'v_snap2:',
        ('sll', 't0', 't2', 3),
        ('sltu', 't4', 's4', 't0'),
        ('beqz', 't4', 'v_nopad'),
        ('nop',),
        ('addu', 's4', 't0', 'zero'),
        'v_nopad:',
        ('addu', 'v1', 'zero', 'zero'),
        ('lui', 't4', H(WIDTHS)),
        ('addu', 't4', 't4', 't3'),
        ('lbu', 't4', L(WIDTHS), 't4'),
        ('nop',),
        ('addu', 's5', 's4', 't4'),
        ('sll', 't3', 't3', 4),              # OR the glyph rows into the line copy at the pen
        ('lui', 't4', H(FONT)),
        ('addiu', 't4', 't4', L(FONT)),
        ('addu', 't3', 't3', 't4'),          # t3 = glyph rows
        ('subu', 't4', 's4', 't9'),
        ('srl', 't5', 't4', 3),
        ('andi', 't4', 't4', 7),             # t4 = shift
        ('addu', 't5', 't5', 's1'),
        ('addiu', 't5', 't5', HEAD + LB),    # t5 = row 1 byte of the pen
        ('ori', 't6', 'zero', 8),
        ('subu', 't6', 't6', 't4'),          # t6 = 8 - shift
        ('addiu', 't7', 't3', 16),
        'v_or:',
        ('lbu', 't0', 0, 't3'),
        ('lbu', 't8', 0, 't5'),
        ('srlv', 'v0', 't0', 't4'),
        ('or', 't8', 't8', 'v0'),
        ('sb', 't8', 0, 't5'),
        ('lbu', 't8', 1, 't5'),
        ('sllv', 'v0', 't0', 't6'),
        ('or', 't8', 't8', 'v0'),
        ('sb', 't8', 1, 't5'),
        ('addiu', 't3', 't3', 1),
        ('bne', 't3', 't7', 'v_or'),
        ('addiu', 't5', 't5', LB),
        ('addu', 't1', 'zero', 'zero'),
        'v_adv:',
        ('sw', 't1', S_SPACES, 's1'),
        ('sw', 'v1', S_LEAD, 's1'),
        ('addiu', 't2', 't2', 1),
        ('sw', 't2', S_BCOL, 's1'),
        ('srl', 's6', 's6', 2),              # s6 = x0 = pen before padding & ~3
        ('sll', 's6', 's6', 2),
        ('addiu', 's7', 's5', 3),            # s7 = x1 = (new pen + 3) & ~3
        ('srl', 's7', 's7', 2),
        ('sll', 's7', 's7', 2),
        'v_chunk:',
        ('addiu', 'a1', 's6', CHUNK),
        ('sltu', 't0', 's7', 'a1'),
        ('bnez', 't0', 'v_last'),
        ('nop',),
        ('b', 'v_draw'),
        ('nop',),
        'v_last:',
        ('addu', 'a1', 's7', 'zero'),
        'v_draw:',
        ('jal', 'vrender'),                  # (s6 x0, a1 x1)
        ('addu', 'a0', 's6', 'zero'),
        ('addiu', 's6', 's6', CHUNK),
        ('sltu', 't0', 's6', 's7'),
        ('bnez', 't0', 'v_chunk'),
        ('nop',),
        'v_done:',
        ('sw', 's5', S_PEN, 's1'),
        ('addiu', 't0', 's5', 7),
        ('srl', 't0', 't0', 3),
        ('sw', 't0', S_ECOL, 's1'),
        ('addiu', 't0', 't0', -1),           # putchar adds 1
        ('sw', 't0', 4, 's0'),
        ('addu', 'v0', 'zero', 'zero'),
        ('lw', 'ra', 0x14c, 'sp'),
        ('lw', 's0', 0x148, 'sp'),
        ('lw', 's1', 0x144, 'sp'),
        ('lw', 's2', 0x140, 'sp'),
        ('lw', 's3', 0x13c, 'sp'),
        ('lw', 's4', 0x138, 'sp'),
        ('lw', 's5', 0x134, 'sp'),
        ('lw', 's6', 0x130, 'sp'),
        ('lw', 's7', 0x12c, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x150),

        'vsetpos:',                          # set position 0x80022c20(ctx, col, y): the run of this ctx ends
        ('lui', 't0', H(RUNS)),
        ('addiu', 't0', 't0', L(RUNS)),
        ('ori', 't1', 'zero', SLOTS),
        'p_loop:',
        ('lw', 't2', S_CTX, 't0'),
        ('addiu', 't1', 't1', -1),
        ('bne', 't2', 'a0', 'p_next'),
        ('nop',),
        ('sw', 'zero', S_CTX, 't0'),
        'p_next:',
        ('bnez', 't1', 'p_loop'),
        ('addiu', 't0', 't0', SLOT_SIZE),
        ('addiu', 'sp', 'sp', -0x20),        # the two instructions replaced by the jump
        ('j', SET_POS + 8),
        ('sw', 'ra', 0x18, 'sp'),

        'v_orig:',                           # the game's glyph; the run of this ctx ends
        ('lui', 't0', H(RUNS)),
        ('addiu', 't0', 't0', L(RUNS)),
        ('ori', 't1', 'zero', SLOTS),
        'o_loop:',
        ('lw', 't2', S_CTX, 't0'),
        ('addiu', 't1', 't1', -1),
        ('bne', 't2', 'a0', 'o_next'),
        ('nop',),
        ('sw', 'zero', S_CTX, 't0'),
        'o_next:',
        ('bnez', 't1', 'o_loop'),
        ('addiu', 't0', 't0', SLOT_SIZE),
        ('j', GLYPH),
        ('nop',),

        # vrender(a0 x0, a1 x1): expand [x0, x1) of the line copy of slot s1 to 4bpp at sp+0x20 (caller's
        # frame: called from vglyph only) and upload at y s3. Pixel x: byte (x - base) >> 3 of a row.
        'vrender:',
        ('addiu', 'sp', 'sp', -0x28),
        ('sw', 'ra', 0x24, 'sp'),
        ('sw', 'a0', 0x20, 'sp'),
        ('sw', 'a1', 0x1c, 'sp'),
        ('lui', 't0', H(FG)),
        ('lbu', 'a2', L(FG), 't0'),          # a2 fg
        ('lui', 't0', H(BG)),
        ('lbu', 'a3', L(BG), 't0'),          # a3 bg
        ('lw', 't0', 0x34, 's0'),
        ('lbu', 't8', 0x20, 's0'),           # t8 shadow colour, t7 = shadow on
        ('sltu', 't7', 'zero', 't0'),
        ('lw', 't9', S_BASE, 's1'),
        ('addiu', 'v1', 'sp', 0x28 + 0x20),  # v1 = output (caller's sp + 0x20)
        ('addiu', 't6', 's1', HEAD + LB),    # t6 = row r (1..16) of the copy
        ('addiu', 'v0', 't6', 16 * LB),      # end
        'r_row:',
        ('addu', 't5', 'a0', 'zero'),        # t5 = x
        'r_px:',
        ('jal', 'vpix'),                     # -> t4 colour of x (t5)
        ('nop',),
        ('addu', 't3', 't4', 'zero'),
        ('jal', 'vpix'),
        ('addiu', 't5', 't5', 1),
        ('sll', 't4', 't4', 4),
        ('or', 't3', 't3', 't4'),
        ('sb', 't3', 0, 'v1'),
        ('addiu', 'v1', 'v1', 1),
        ('addiu', 't5', 't5', 1),
        ('bne', 't5', 'a1', 'r_px'),
        ('nop',),
        ('addiu', 't6', 't6', LB),
        ('bne', 't6', 'v0', 'r_row'),
        ('nop',),
        ('addiu', 't0', 'sp', 0x28 + 0x20),
        ('sw', 't0', 0x10, 'sp'),
        ('subu', 'a2', 'a1', 'a0'),
        ('addu', 'a1', 's3', 'zero'),
        ('jal', UPLOAD),                     # (x px, y, w px, h, buf)
        ('ori', 'a3', 'zero', 16),
        ('lw', 'ra', 0x24, 'sp'),
        ('nop',),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x28),

        'vpix:',                             # colour of pixel t5 in row t6 -> t4 (t0-t2 scratch)
        ('subu', 't0', 't5', 't9'),          # xr (>= 8: base is 8 px left of the run start)
        ('srl', 't1', 't0', 3),
        ('addu', 't1', 't1', 't6'),
        ('lbu', 't2', 0, 't1'),
        ('andi', 't1', 't0', 7),
        ('sllv', 't2', 't2', 't1'),          # bit 7 - (xr & 7) -> bit 7
        ('andi', 't2', 't2', 0x80),
        ('bnez', 't2', 'p_ret'),
        ('addu', 't4', 'a2', 'zero'),        # ink: fg
        ('beqz', 't7', 'p_bg'),
        ('addiu', 't0', 't0', -1),
        ('srl', 't1', 't0', 3),              # shadow: ink left or up-left
        ('addu', 't1', 't1', 't6'),
        ('lbu', 't2', 0, 't1'),
        ('lbu', 't4', -LB, 't1'),
        ('andi', 't1', 't0', 7),
        ('or', 't2', 't2', 't4'),
        ('sllv', 't2', 't2', 't1'),
        ('andi', 't2', 't2', 0x80),
        ('bnez', 't2', 'p_ret'),
        ('addu', 't4', 't8', 'zero'),
        'p_bg:',
        ('addu', 't4', 'a3', 'zero'),
        'p_ret:',
        ('jr', 'ra'),
        ('nop',),

        'vstrlen:',                          # (a0 text) -> v0 = 8-px cells of its widest line as drawn
        ('addiu', 'sp', 'sp', -0x20),        # (padding rules of vglyph; tokens as English; ESC + 2 bytes
        ('sw', 'ra', 0x1c, 'sp'),            # none; LF / CR end a line)
        ('sw', 's0', 0x18, 'sp'),
        ('sw', 's1', 0x14, 'sp'),
        ('sw', 's2', 0x10, 'sp'),
        ('addu', 's0', 'a0', 'zero'),
        ('addu', 's2', 'zero', 'zero'),      # widest
        'w_line:',
        ('addu', 's1', 'zero', 'zero'),      # px of this line
        ('addu', 't6', 'zero', 'zero'),      # spaces since the last other glyph
        ('ori', 't7', 'zero', 1),            # lead: no other glyph yet
        ('addu', 't8', 'zero', 'zero'),      # bytes drawn (cells in the fixed layout)
        'w_loop:',
        ('lbu', 't4', 0, 's0'),
        ('nop',),
        ('beqz', 't4', 'w_lf'),
        ('ori', 't5', 'zero', 0x20),
        ('beq', 't4', 't5', 'w_space'),
        ('sltiu', 't5', 't4', 0x20),
        ('bnez', 't5', 'w_ctl'),
        ('nop',),
        ('beqz', 't6', 'w_go'),              # a glyph after spaces: padding as vglyph
        ('addiu', 't5', 't4', -0x30),
        ('sltiu', 't5', 't5', 10),
        ('beqz', 't5', 'w_snap'),
        ('nop',),
        ('bnez', 't7', 'w_padk'),
        ('addu', 't5', 't6', 'zero'),
        ('addiu', 't5', 't6', -1),
        'w_padk:',
        ('sll', 't0', 't5', 1),
        ('addu', 't0', 't0', 't5'),
        ('b', 'w_go'),
        ('addu', 's1', 's1', 't0'),
        'w_snap:',
        ('sltiu', 't5', 't6', 2),
        ('beqz', 't5', 'w_snap2'),
        ('nop',),
        ('beqz', 't7', 'w_go'),
        ('nop',),
        'w_snap2:',
        ('sll', 't0', 't8', 3),
        ('sltu', 't5', 's1', 't0'),
        ('beqz', 't5', 'w_go'),
        ('nop',),
        ('addu', 's1', 't0', 'zero'),
        'w_go:',
        ('addu', 't6', 'zero', 'zero'),
        ('addu', 't7', 'zero', 'zero'),
        ('sltiu', 't5', 't4', TOKEN),
        ('beqz', 't5', 'w_tok'),
        ('sltiu', 't5', 't4', 0x7f),
        ('bnez', 't5', 'w_one'),
        ('sltiu', 't5', 't4', 0xa0),
        ('bnez', 't5', 'w_two'),
        ('sltiu', 't5', 't4', 0xe0),
        ('beqz', 't5', 'w_two'),
        ('nop',),
        ('addiu', 's0', 's0', 1),            # half-width kana: one cell
        ('addiu', 't8', 't8', 1),
        ('b', 'w_loop'),
        ('addiu', 's1', 's1', 8),
        'w_two:',
        ('addiu', 's0', 's0', 2),
        ('addiu', 't8', 't8', 2),
        ('b', 'w_loop'),
        ('addiu', 's1', 's1', 16),
        'w_space:',
        ('addiu', 't6', 't6', 1),
        ('addiu', 's0', 's0', 1),
        ('addiu', 't8', 't8', 1),
        ('b', 'w_loop'),
        ('addiu', 's1', 's1', SPACE_ADV),
        'w_one:',
        ('lui', 't5', H(WIDTHS - 0x20)),
        ('addu', 't5', 't5', 't4'),
        ('lbu', 't5', L(WIDTHS - 0x20), 't5'),
        ('addiu', 's0', 's0', 1),
        ('addiu', 't8', 't8', 1),
        ('b', 'w_loop'),
        ('addu', 's1', 's1', 't5'),
        'w_tok:',
        ('lbu', 't5', 1, 's0'),
        ('sll', 't4', 't4', 8),
        ('jal', 'vtokw'),                    # (t0 t1 t4 t5 v0 only)
        ('or', 'a3', 't4', 't5'),
        ('addu', 's1', 's1', 'v0'),
        ('addiu', 't8', 't8', 2),
        ('b', 'w_loop'),
        ('addiu', 's0', 's0', 2),
        'w_ctl:',
        ('ori', 't5', 'zero', 0x1b),
        ('bne', 't4', 't5', 'w_nesc'),
        ('ori', 't5', 'zero', 0x0a),
        ('b', 'w_loop'),
        ('addiu', 's0', 's0', 3),
        'w_nesc:',
        ('beq', 't4', 't5', 'w_lf'),
        ('addiu', 's0', 's0', 1),
        ('ori', 't5', 'zero', 0x0d),
        ('bne', 't4', 't5', 'w_loop'),
        ('nop',),
        'w_lf:',                             # end of a line (LF, CR or NUL)
        ('sltu', 't5', 's2', 's1'),
        ('beqz', 't5', 'w_lf2'),
        ('nop',),
        ('addu', 's2', 's1', 'zero'),
        'w_lf2:',
        ('bnez', 't4', 'w_line'),
        ('nop',),
        ('addiu', 'v0', 's2', 7),
        ('srl', 'v0', 'v0', 3),
        ('lw', 'ra', 0x1c, 'sp'),
        ('lw', 's0', 0x18, 'sp'),
        ('lw', 's1', 0x14, 'sp'),
        ('lw', 's2', 0x10, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x20),

        'vtokw:',                            # (a3 token) -> v0 px of its English (t0, t1, t4, t5)
        ('addiu', 'sp', 'sp', -0x18),
        ('sw', 'ra', 0x14, 'sp'),
        ('jal', tok_label),
        ('nop',),
        ('addu', 't1', 'v0', 'zero'),
        ('addu', 'v0', 'zero', 'zero'),
        't_loop:',
        ('lbu', 't4', 0, 't1'),
        ('nop',),
        ('beqz', 't4', 't_end'),
        ('lui', 't5', H(WIDTHS - 0x20)),
        ('addu', 't5', 't5', 't4'),
        ('lbu', 't5', L(WIDTHS - 0x20), 't5'),
        ('addiu', 't1', 't1', 1),
        ('b', 't_loop'),
        ('addu', 'v0', 'v0', 't5'),
        't_end:',
        ('lw', 'ra', 0x14, 'sp'),
        ('nop',),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x18),

        # vcut(a0 col, a1 y, a2 text, a3 width in 8-px cells, 0x10(sp) centre): replaces the message box line
        # cutter 0x8003b870 (cut by bytes): the line up to LF / NUL / width * 8 px goes to a buffer and is
        # printed at (col, y) in colour 7 (centred by cells if asked) -> v0 = bytes used (+ the LF / CR LF).
        'vcut:',
        ('addiu', 'sp', 'sp', -0x80),
        ('sw', 'ra', 0x78, 'sp'),
        ('sw', 's3', 0x74, 'sp'),
        ('sw', 's2', 0x70, 'sp'),
        ('sw', 's1', 0x6c, 'sp'),
        ('sw', 's0', 0x68, 'sp'),
        ('sw', 's4', 0x64, 'sp'),
        ('sw', 's5', 0x60, 'sp'),
        ('addu', 's1', 'a0', 'zero'),
        ('addu', 's3', 'a1', 'zero'),
        ('addu', 's2', 'a3', 'zero'),
        ('lw', 't9', 0x90, 'sp'),
        ('addu', 's0', 'zero', 'zero'),      # bytes
        ('addu', 's4', 'zero', 'zero'),      # px
        ('sll', 's5', 'a3', 3),              # limit px
        ('addiu', 't7', 'sp', 0x10),         # buffer (0x10..0x5f)
        'c_loop:',
        ('lbu', 'v1', 0, 'a2'),
        ('ori', 'v0', 'zero', 0x0a),
        ('beq', 'v1', 'v0', 'c_end'),
        ('sltiu', 'v0', 's0', CUT_MAX),
        ('beqz', 'v0', 'c_end'),
        ('nop',),
        ('beqz', 'v1', 'c_end'),
        ('ori', 'v0', 'zero', 0x1b),
        ('beq', 'v1', 'v0', 'c_esc'),
        ('sltiu', 'v0', 'v1', 0x20),
        ('bnez', 'v0', 'c_ctl'),             # CR ...: copied, no width
        ('sltiu', 'v0', 'v1', 0x7f),
        ('bnez', 'v0', 'c_ascii'),
        ('sltiu', 'v0', 'v1', 0xa0),
        ('bnez', 'v0', 'c_two'),
        ('sltiu', 'v0', 'v1', 0xe0),
        ('bnez', 'v0', 'c_one'),             # half-width kana
        ('addiu', 't0', 's4', 8),
        ('sltiu', 'v0', 'v1', TOKEN),
        ('beqz', 'v0', 'c_tok'),
        ('nop',),
        'c_two:',                            # SJIS pair: 16 px; line-start punctuation may overhang
        ('addiu', 't0', 's4', 16),
        ('sltu', 'v0', 's5', 't0'),
        ('beqz', 'v0', 'c_two_ok'),
        ('ori', 'v0', 'zero', 0x81),
        ('bne', 'v1', 'v0', 'c_end'),
        ('lbu', 'v0', 1, 'a2'),
        ('nop',),
        ('addiu', 't1', 'v0', -0x41),
        ('sltiu', 't1', 't1', 0x0b),
        ('beqz', 't1', 'c_end'),
        ('ori', 't1', 'zero', 0x48),
        ('beq', 'v0', 't1', 'c_end'),
        ('nop',),
        'c_two_ok:',
        ('addu', 's4', 't0', 'zero'),
        ('lbu', 'v0', 1, 'a2'),
        ('sb', 'v1', 0, 't7'),
        ('sb', 'v0', 1, 't7'),
        ('addiu', 'a2', 'a2', 2),
        ('addiu', 't7', 't7', 2),
        ('b', 'c_loop'),
        ('addiu', 's0', 's0', 2),
        'c_tok:',
        ('lbu', 'v0', 1, 'a2'),
        ('sll', 'a3', 'v1', 8),
        ('jal', 'vtokw'),
        ('or', 'a3', 'a3', 'v0'),
        ('addu', 't0', 's4', 'v0'),
        ('sltu', 'v0', 's5', 't0'),
        ('bnez', 'v0', 'c_end'),
        ('nop',),
        ('b', 'c_two_ok'),
        ('nop',),
        'c_ascii:',
        ('lui', 't0', H(WIDTHS - 0x20)),
        ('addu', 't0', 't0', 'v1'),
        ('lbu', 't0', L(WIDTHS - 0x20), 't0'),
        ('nop',),
        ('addu', 't0', 's4', 't0'),
        'c_one:',
        ('sltu', 'v0', 's5', 't0'),
        ('bnez', 'v0', 'c_end'),
        ('nop',),
        ('addu', 's4', 't0', 'zero'),
        'c_ctl:',
        ('sb', 'v1', 0, 't7'),
        ('addiu', 'a2', 'a2', 1),
        ('addiu', 't7', 't7', 1),
        ('b', 'c_loop'),
        ('addiu', 's0', 's0', 1),
        'c_esc:',                            # ESC + 2 bytes: no width
        ('lbu', 'v0', 1, 'a2'),
        ('lbu', 't0', 2, 'a2'),
        ('sb', 'v1', 0, 't7'),
        ('sb', 'v0', 1, 't7'),
        ('sb', 't0', 2, 't7'),
        ('addiu', 'a2', 'a2', 3),
        ('addiu', 't7', 't7', 3),
        ('b', 'c_loop'),
        ('addiu', 's0', 's0', 3),
        'c_end:',
        ('sb', 'zero', 0, 't7'),
        ('lbu', 'v1', 0, 'a2'),
        ('ori', 'v0', 'zero', 0x0a),
        ('bne', 'v1', 'v0', 'c_nolf'),
        ('ori', 'v0', 'zero', 0x0d),
        ('b', 'c_centre'),
        ('addiu', 's0', 's0', 1),
        'c_nolf:',
        ('bne', 'v1', 'v0', 'c_centre'),
        ('nop',),
        ('addiu', 's0', 's0', 2),
        'c_centre:',
        ('beqz', 't9', 'c_print'),
        ('addiu', 't0', 's4', 7),
        ('srl', 't0', 't0', 3),
        ('subu', 't0', 's2', 't0'),
        ('sra', 't0', 't0', 1),
        ('addu', 's1', 's1', 't0'),
        'c_print:',
        ('lui', 'a0', H(CTX)),
        ('addiu', 'a0', 'a0', L(CTX)),
        ('jal', SET_COLOUR),
        ('ori', 'a1', 'zero', 7),
        ('lui', 'a0', H(CTX)),
        ('addiu', 'a0', 'a0', L(CTX)),
        ('addu', 'a1', 's1', 'zero'),
        ('jal', SET_POS),
        ('addu', 'a2', 's3', 'zero'),
        ('lui', 'a0', H(CTX)),
        ('addiu', 'a0', 'a0', L(CTX)),
        ('lui', 'a1', H(FMT_S)),
        ('addiu', 'a1', 'a1', L(FMT_S)),
        ('jal', PRINTF),
        ('addiu', 'a2', 'sp', 0x10),
        ('addu', 'v0', 's0', 'zero'),
        ('lw', 'ra', 0x78, 'sp'),
        ('lw', 's3', 0x74, 'sp'),
        ('lw', 's2', 0x70, 'sp'),
        ('lw', 's1', 0x6c, 'sp'),
        ('lw', 's0', 0x68, 'sp'),
        ('lw', 's4', 0x64, 'sp'),
        ('lw', 's5', 0x60, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x80),
    ]


H, L = asm.hi, asm.lo


def patch(exe, lab, put, expect):
    """message box line cutter -> vcut; message box width from the widest line in pixels"""
    expect(exe, SET_POS, [0x27bdffe0, 0xafbf0018])
    put(exe, SET_POS, asm.assemble(SET_POS, [('j', lab['vsetpos']), ('nop',)]))
    expect(exe, CUT, [0x27bdff80, 0xafbf0078])
    put(exe, CUT, asm.assemble(CUT, [('j', lab['vcut']), ('nop',)]))
    # 0x8003d19c: s1 = longest line in bytes of the formatted text 0x8011fc3c (box = s1 * 8 + 32 px)
    expect(exe, MSG_WIDTH, [0x8c420000, 0, 0x02021823, 0x0223102b, 0x10400003, 0x32220001, 0x00608821])
    put(exe, MSG_WIDTH, asm.assemble(MSG_WIDTH, [
        ('lui', 'a0', H(MSG_TEXT)), ('jal', lab['vstrlen']), ('addiu', 'a0', 'a0', L(MSG_TEXT)),
        ('addu', 's1', 'v0', 'zero'), ('nop',), ('nop',), ('nop',)]))
    # officer list rows: page 1 0x8007704c: level col 9 -> 10 (the name at col 2 gets 8 cells), HP 12 -> 13;
    # page 2 0x80076b80: level 9 -> 10, intelligence / war / command 23 / 27 / 31 -> 24 / 28 / 32 (the class
    # name at col 14 gets 10 cells; experience stays at 35)
    for va, old, new in ((0x800770a0, 9, 10), (0x800770d4, 12, 13), (0x80076bd0, 9, 10),
                         (0x80076c68, 23, 24), (0x80076c9c, 27, 28), (0x80076cd0, 31, 32)):
        expect(exe, va, [0x34050000 | old])
        put(exe, va, asm.assemble(va, [('ori', 'a1', 'zero', new)]))
    # battle Units list rows (0x80054700..): name col +0 (7 cells, names reach 89 px), level +7, HP +10 "/" +14
    # max +15, SP "%3d/%3d" +20 with a grey "/" overlaid at +23, attack +28, defence +32 (ends +35; the window
    # has 2 spare cells) -> name 10 cells: level +10 (also "-Retreated-"), HP +13 / +16 / +17, SP +21 / +24,
    # attack +29, defence +33. SP format -> "%3d%6d" (same 8 bytes): by the digit-space rules both numbers
    # right-align (ends +18 / +51 px), the overlaid slash (+24 px) falls in the gap.
    for va, old, new in ((0x80054790, 7, 10), (0x80054994, 7, 10), (0x800547d4, 10, 13), (0x8005493c, 14, 16),
                         (0x80054814, 15, 17), (0x80054858, 20, 21), (0x80054968, 23, 24), (0x800548a4, 28, 29),
                         (0x800548e8, 32, 33)):
        expect(exe, va, [0x26450000 | old])
        put(exe, va, asm.assemble(va, [('addiu', 'a1', 's2', new)]))
    # current HP "%4d" (0x800ddb58) -> the "%3d" at 0x800ddb64: " 145" would end on the slash's cell
    expect(exe, 0x800547fc, [0x24a5db58])
    put(exe, 0x800547fc, asm.assemble(0x800547fc, [('addiu', 'a1', 'a1', -0x249c)]))
    expect(exe, 0x800ddb5c, list(struct.unpack('<2I', b'%3d/%3d\0')))
    put(exe, 0x800ddb5c, b'%3d%6d\0\0')
    # strategy list SP "%3d/%3d" (0x800dda4c, at cell 31 after the SP icon) rendered "44/ 44" -> "%3d/%d" (" 44/44";
    # "%d / %d" would touch the icon and "999 / 999" would not fit)
    expect(exe, 0x800dda4c, list(struct.unpack('<2I', b'%3d/%3d\0')))
    put(exe, 0x800dda4c, b'%3d/%d\0\0')
    # officer screen HP "%4d/%4d" (0x800dc868) and SP "%3d/%3d" (0x800dc870) rendered "54/ 54" -> max as "%d"
    expect(exe, 0x800dc868, list(struct.unpack('<4I', b'%4d/%4d\0%3d/%3d\0')))
    put(exe, 0x800dc868, b'%4d/%d\0\0%3d/%d\0\0')
    # battle officer screen 0x8007b5c0 (HP / SP at col 29: "%3u/%3u" 0x800ddd94) and the officer list page 1
    # (0x80077100 HP "%4u/%4u" 0x800ddd8c, 0x80077144 SP 0x800ddd94): same gap
    expect(exe, 0x800ddd8c, list(struct.unpack('<4I', b'%4u/%4u\0%3u/%3u\0')))
    put(exe, 0x800ddd8c, b'%4u/%u\0\0%3u/%u\0\0')
    # battle officer screen as reached from the Units list (Square; 0x80062120.., HP and SP both "%4u/%4u"
    # 0x800ddc94) and the list at 0x800405c0 (HP/SP "%4u/%4u" 0x800dd810): same gap ("54/ 54" seen, session 13)
    for va in (0x800ddc94, 0x800dd810):
        expect(exe, va, list(struct.unpack('<2I', b'%4u/%4u\0')))
        put(exe, va, b'%4u/%u\0')
    # Units list page 2 (0x80054a80..): level +7, class icon +10 (sprite), class "%-8s" +12, INT/WAR/CMD/EXP +21
    # +25 +29 +33 -> level +10, icon +12, class +14 (80 px to INT; class names kept <= 80 px), stats 3 cells
    # apart: +24 +27 +30, EXP stays +33.
    for va, old, new in ((0x80054adc, 7, 10), (0x80054b18, 10, 12), (0x80054b38, 12, 14), (0x80054b80, 21, 24),
                         (0x80054bb4, 25, 27), (0x80054be8, 29, 30)):
        expect(exe, va, [0x26450000 | old])
        put(exe, va, asm.assemble(va, [('addiu', 'a1', 's2', new)]))
    # page 3: 3 equipment + 10 item icons (or "-") at absolute cells 9 + 2i (i < 3) / 10 + 2i -> 11 + 2i (no gap;
    # ends at cell 37 inside the frame; names get 72 px); headers "Equip" 9 -> 12, "Items" 22 -> 25
    for va, old in ((0x80054dd4, 0x24620009), (0x80054dd8, 0x2462000a), (0x80054e04, 0x24a50009),
                    (0x80054e08, 0x24a5000a)):
        expect(exe, va, [old])
        put(exe, va, struct.pack('<I', old & 0xffff0000 | 11))
    for va, old, new in ((0x8005507c, 9, 12), (0x800550a8, 0x16, 25)):
        expect(exe, va, [0x34050000 | old])
        put(exe, va, asm.assemble(va, [('ori', 'a1', 'zero', new)]))
    # header plates (sprites 0x80086318(index, x px, y, slot); 24-px plates redrawn by gfx.py) follow the moved
    # columns. Battle Units list page 1: Lv/HP/SP/Atk/Def 72/120/192/240/272 -> 96/136/200/248/280 (HP centred
    # on "cur/max", SP on the overlaid slash); page 2: Lv/Int/Str/Ldr 72/184/216/248 -> 96/208/232/256 (Exp 280
    # kept). Officer list page 1: Lv/HP 72/120 -> 80/128; page 2: Lv/Int/Str/Ldr 72/184/216/248 -> 80/192/224/256.
    for va, old, new in ((0x800550d8, 0x48, 96), (0x800550ec, 0x78, 136), (0x80055100, 0xc0, 200),
                         (0x80055114, 0xf0, 248), (0x80055128, 0x110, 280),
                         (0x80054fc0, 0x48, 96), (0x80054fd4, 0xb8, 208), (0x80054fe8, 0xd8, 232),
                         (0x80054ffc, 0xf8, 256),
                         (0x80077218, 0x48, 80), (0x8007722c, 0x78, 128),
                         (0x80076d8c, 0x48, 80), (0x80076da0, 0xb8, 192), (0x80076db4, 0xd8, 224),
                         (0x80076dc8, 0xf8, 256)):
        expect(exe, va, [0x34050000 | old])
        put(exe, va, asm.assemble(va, [('ori', 'a1', 'zero', new)]))
    # Sortie lists (pre-battle "Units n/6" screens 0x80028900.. and 0x80029050.., session 14: "Zhuge Liang" was cut
    # by the level at +7) use their own row printers with the old Units-list columns: page 1 0x80028078 (name +0,
    # level +7, HP "%4d/%d" +10, SP "%3d/%d" +20, attack +28, defence +32), page 2 0x80028244 (level +7, class icon
    # +10, class +12, INT/WAR/CMD +21 +25 +29, EXP +33), page 3 0x80028460 (icons at 9 + 2i / 10 + 2i). Same new
    # layout as the battle Units list: names 10 cells (HP "%4d" at +12 puts the slash at +16 as there).
    for va, old, new in ((0x80028108, 7, 10), (0x8002813c, 10, 12), (0x80028180, 20, 21), (0x800281c4, 28, 29),
                         (0x800281f8, 32, 33),
                         (0x800282d8, 7, 10), (0x8002830c, 10, 12), (0x8002832c, 12, 14), (0x80028374, 21, 24),
                         (0x800283a8, 25, 27), (0x800283dc, 29, 30)):
        expect(exe, va, [0x26450000 | old])
        put(exe, va, asm.assemble(va, [('addiu', 'a1', 's2', new)]))
    for va, old in ((0x800285e4, 0x24620009), (0x800285e8, 0x2462000a), (0x80028614, 0x24a50009),
                    (0x80028618, 0x24a5000a)):
        expect(exe, va, [old])
        put(exe, va, struct.pack('<I', old & 0xffff0000 | 11))
    # their headers, and the second battle Units-list screen 0x800557f0 (same rows as the first, own headers): page 1
    # plates 72/120/192/240/272 -> 96/136/200/248/280 (the delay-slot "ori a1, 72" before the page-1 jump too),
    # page 2 72/184/216/248 -> 96/208/232/256, page 3 "Equip"/"Items" cells 9/22 -> 12/25.
    hdr = []
    for p1, p2, p3 in (((0x8002892c, 0x80028a50, 0x80028a64, 0x80028a78, 0x80028a8c, 0x80028aa0),
                        (0x8002893c, 0x80028950, 0x80028964, 0x80028978), (0x800289f8, 0x80028a24)),
                       ((0x800291ac, 0x800291c0, 0x800291d4, 0x800291e8, 0x800291fc),
                        (0x80029094, 0x800290a8, 0x800290bc, 0x800290d0), (0x80029150, 0x8002917c)),
                       ((0x800559cc, 0x80055af0, 0x80055b04, 0x80055b18, 0x80055b2c, 0x80055b40),
                        (0x800559dc, 0x800559f0, 0x80055a04, 0x80055a18), (0x80055a98, 0x80055ac4))):
        if len(p1) == 6:
            hdr.append((p1[0], 0x48, 96))
            p1 = p1[1:]
        hdr += list(zip(p1, (0x48, 0x78, 0xc0, 0xf0, 0x110), (96, 136, 200, 248, 280)))
        hdr += list(zip(p2, (0x48, 0xb8, 0xd8, 0xf8), (96, 208, 232, 256)))
        hdr += list(zip(p3, (9, 0x16), (12, 25)))
    for va, old, new in hdr:
        expect(exe, va, [0x34050000 | old])
        put(exe, va, asm.assemble(va, [('ori', 'a1', 'zero', new)]))
    # Yes/No row in a mode-1 message box (0x8003d740(col, row)): col = box right / 8 - 16 (the JP row is 15 cells;
    # the box is at least 120 px) -> a short English question puts the icon on the left frame. "  Yes    No" ends
    # at cell 11: right / 8 - 13 leaves ~12 px left / ~24 px right in the narrowest box.
    expect(exe, 0x8003d574, [0x2484fff0])
    put(exe, 0x8003d574, asm.assemble(0x8003d574, [('addiu', 'a0', 'a0', -13)]))
    # shop price prompt (0x80032540..): lines 2-3 at x 10, line 1 ("「%sでしたら") at x 8 -> the JP indent past the
    # quote mark; English has no quote -> all at x 8
    for va in (0x80032580, 0x800325d0):
        expect(exe, va, [0x3405000a])
        put(exe, va, asm.assemble(va, [('ori', 'a1', 'zero', 8)]))
