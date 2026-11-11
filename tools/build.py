"""Rebuild track 1 of the disc with the translation and produce a patch.

Output: build/sangokushi_koumeiden_en_track1.bin, a copy of the audio track 2 and a .cue next to
them (boots in an emulator), and build/sangokushi_koumeiden_en.xdelta (clean track 1 -> English
track 1; the audio track is not changed).

usage: .venv/bin/python tools/build.py [--test] [clean_track1.bin] [out_track1.bin]
  --test   chapter text = "<chapter>.<part>.<entry>" tags + the start of the Japanese
           (checks the remap hooks in the emulator)
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, tokens, dmes, gfx, ip, iso, progstr, setup, snr, tl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'build', 'sangokushi_koumeiden_en_track1.bin')
EXE_BASE = 0x80010000 - 0x800            # file offset of an address = va - EXE_BASE
FIXED = (iso.EXE_NAME,)                  # must keep its place
# Free space: the level-2 kanji of the 16x16 font (glyph 1961 = SJIS 0x989f .. the code table
# 0x800c436c; rare kanji and the custom name glyphs 0xf0xx). All of the font is free once no
# Japanese is left.
POOL, POOL_END = 0x800c294c, 0x800c3700
# moved EXE strings (progstr.py): level-1 kanji glyphs below POOL (Japanese still shown that uses them
# draws garbage: names phase pending)
STRINGS = 0x800c094c                     # 8 KB below POOL (2.2 KB used, session 7)
REMAP = POOL_END                         # one part's remap table (snr.rebuild), up to the code table
assert REMAP + snr.REMAP_MAX <= 0x800c436c
# game functions
FILE_INIT, FILE_OPEN, FILE_READ, FILE_CLOSE = 0x8006f608, 0x8006bb20, 0x8006f760, 0x8006f620
M_NAME, CD_DIR = 0x800a5408, 0x800dd780  # "\SNR\SNRxM.E2;1", argument of the open
TALK, TALK_END = 0x80026a3c, 0x80026b48  # dialogue block reader (frame 0x828: block 0x400 at sp+0x10, speech at sp+0x410)


def poke(exe, va, words):
    for i, w in enumerate(words):
        struct.pack_into('<I', exe, va - EXE_BASE + 4 * i, w)


def peek(exe, va, n):
    return list(struct.unpack_from('<%dI' % n, exe, va - EXE_BASE))


def expect(exe, va, words):
    assert peek(exe, va, len(words)) == words, 'unexpected code at %#x' % va


def put(exe, va, code):
    exe[va - EXE_BASE:va - EXE_BASE + len(code)] = code


def text_read(at):
    """(ctx, old offset, dst, len) -> dst: open M, find the entry in the part's remap table, read len B.
    Entry 'big' sets len = snr.BLOCK_MAX (dialogue blocks), 'read' takes a3."""
    return [
        'big:',
        ('ori', 'a3', 'zero', snr.BLOCK_MAX),
        'read:',
        ('addiu', 'sp', 'sp', -0x48),
        ('sw', 'ra', 0x44, 'sp'),
        ('sw', 's0', 0x40, 'sp'),
        ('sw', 's2', 0x38, 'sp'),
        ('sw', 's3', 0x34, 'sp'),
        ('andi', 's0', 'a1', 0xffff),
        ('addu', 's2', 'a2', 'zero'),
        ('addu', 's3', 'a3', 'zero'),
        ('jal', FILE_INIT),
        ('addiu', 'a0', 'sp', 0x10),
        ('lui', 'a1', asm.hi(M_NAME)),
        ('addiu', 'a1', 'a1', asm.lo(M_NAME)),
        ('lui', 'a2', asm.hi(CD_DIR)),
        ('lw', 'a2', asm.lo(CD_DIR), 'a2'),
        ('jal', FILE_OPEN),
        ('addiu', 'a0', 'sp', 0x10),
        ('beqz', 'v0', 'fail'),
        ('lui', 't0', asm.hi(REMAP)),
        ('addiu', 't0', 't0', asm.lo(REMAP)),
        ('lhu', 't1', 0, 't0'),
        ('addiu', 't2', 't0', 4),            # old[]
        ('addu', 'v0', 'zero', 'zero'),
        ('addu', 'v1', 't1', 'zero'),
        ('addu', 'a1', 's0', 'zero'),        # not found: read at the old offset
        'loop:',
        ('beq', 'v0', 'v1', 'got'),
        ('addu', 't3', 'v0', 'v1'),
        ('srl', 't3', 't3', 1),
        ('sll', 't4', 't3', 1),
        ('addu', 't4', 't4', 't2'),
        ('lhu', 't4', 0, 't4'),
        ('nop',),
        ('beq', 't4', 's0', 'found'),
        ('sltu', 't4', 't4', 's0'),
        ('beqz', 't4', 'less'),
        ('nop',),
        ('b', 'loop'),
        ('addiu', 'v0', 't3', 1),
        'less:',
        ('b', 'loop'),
        ('addu', 'v1', 't3', 'zero'),
        'found:',
        ('sll', 't5', 't1', 1),              # new[] = old[] + align4(2n)
        ('addiu', 't5', 't5', 3),
        ('srl', 't5', 't5', 2),
        ('sll', 't5', 't5', 2),
        ('addu', 't5', 't5', 't2'),
        ('sll', 't3', 't3', 2),
        ('addu', 't5', 't5', 't3'),
        ('lw', 'a1', 0, 't5'),
        'got:',
        ('addiu', 'a0', 'sp', 0x10),
        ('addu', 'a2', 's2', 'zero'),
        ('jal', FILE_READ),
        ('addu', 'a3', 's3', 'zero'),
        ('jal', FILE_CLOSE),
        ('addiu', 'a0', 'sp', 0x10),
        ('b', 'done'),
        ('addu', 'v0', 's2', 'zero'),
        'fail:',
        ('addu', 'v0', 'zero', 'zero'),
        'done:',
        ('lw', 'ra', 0x44, 'sp'),
        ('lw', 's0', 0x40, 'sp'),
        ('lw', 's2', 0x38, 'sp'),
        ('lw', 's3', 0x34, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x48)]


def part_load():
    """(file, part, tmp[8]): read the part's header entry, then its remap table to REMAP"""
    return [
        'part:',
        ('addiu', 'sp', 'sp', -0x20),
        ('sw', 'ra', 0x1c, 'sp'),
        ('sw', 's0', 0x18, 'sp'),
        ('sw', 's1', 0x14, 'sp'),
        ('addu', 's0', 'a0', 'zero'),
        ('addu', 's1', 'a2', 'zero'),
        ('sll', 'a1', 'a1', 3),
        ('jal', FILE_READ),
        ('ori', 'a3', 'zero', 8),
        ('lw', 'a1', 0, 's1'),
        ('lw', 'a3', 4, 's1'),
        ('addu', 'a0', 's0', 'zero'),
        ('lui', 'a2', asm.hi(REMAP)),
        ('jal', FILE_READ),
        ('addiu', 'a2', 'a2', asm.lo(REMAP)),
        ('lw', 'ra', 0x1c, 'sp'),
        ('lw', 's0', 0x18, 'sp'),
        ('lw', 's1', 0x14, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x20)]


def grow_talk_frame(exe):
    """dialogue block reader: block buffer 0x400 -> BLOCK_MAX (sp offsets >= 0x410 move up)"""
    grow = snr.BLOCK_MAX - 0x400
    for va in range(TALK, TALK_END, 4):
        w = peek(exe, va, 1)[0]
        op, rs, imm = w >> 26, w >> 21 & 31, w & 0xffff
        if rs != 29:
            continue
        if va in (TALK, TALK_END - 0x0c):  # addiu sp, sp, -/+0x828
            assert op == 0x09 and imm in (0xf7d8, 0x828), hex(va)
            imm = (imm - grow if imm & 0x8000 else imm + grow) & 0xffff
        elif op in (0x09, 0x23, 0x2b) and imm >= 0x410:  # addiu rt, sp / lw / sw
            assert imm < 0x828, hex(va)
            imm += grow
        else:
            assert imm < 0x410, hex(va)
            continue
        poke(exe, va, [w & 0xffff0000 | imm])


SPRITE_SET, SPRITE_HIDE = 0x8006893c, 0x8006902c
MAP_COLS, MAP_ROWS = 0x800de114, 0x800de115      # u8 map size in cells (8 texels each)
MAP_QUADS = (0x80057d38, 0x80057d88, 0x80057ddc, 0x80057e3c, 0x80057e88, 0x80057edc,
             0x80057f58, 0x80057fa4, 0x80058004, 0x80058050, 0x800580d0, 0x8005811c)


def map_quad():
    """sprite_set(slot, x, y, w, h, vram x, vram y, tw, th, ...) for the battle map picture (uploaded at VRAM
    864,256; 8bpp). The game draws the right-hand quads over a whole 256-texel page and all quads over
    96/192 rows whatever the map size; the texels beyond the map are transparent. Limit each quad to the
    map (hide it when nothing is left), so the quad's texture area stays inside the map upload: DuckStation's
    texture cache (texture replacements) is bypassed when that area touches VRAM that was drawn to."""
    def clamp(size, org, shift, o_pos, o_len, reg, o_reg):
        """reg / o_reg: the screen length in a register or in a stack slot"""
        out = [
            ('lui', 'v0', asm.hi(size)),
            ('lbu', 'v0', asm.lo(size), 'v0'),
            ('lw', 'v1', o_pos, 'sp'),
            ('lw', 't0', o_len, 'sp'),
            ('sll', 'v0', 'v0', 3),
            ('addiu', 'v1', 'v1', -org),
            ('sll', 'v1', 'v1', shift),
            ('subu', 'v0', 'v0', 'v1'),              # texels left from this quad's origin
            ('blez', 'v0', 'hide'),
            ('addiu', 't0', 't0', -1),               # the quad spans len - 1 texels over length - 1 pixels
            ('slt', 'v1', 'v0', 't0'),
            ('beqz', 'v1', 'ok%d' % o_pos),
            ('addiu', 'v1', 'v0', 1)]                # -> texels 0..left: the same scale, last texel = map edge
        if reg is None:
            out += [('lw', 't1', o_reg, 'sp'), ('nop',)]
            reg = 't1'
        out += [
            ('addiu', reg, reg, -1),
            ('mult', reg, 'v0'),
            ('sw', 'v1', o_len, 'sp'),
            ('mflo', reg),
            ('nop',), ('nop',),                      # R3000: no mult/div within two instructions of mflo
            ('div', reg, 't0'),
            ('mflo', reg),
            ('addiu', reg, reg, 1)]
        if o_reg is not None:
            out += [('sw', reg, o_reg, 'sp')]
        return out + ['ok%d:' % o_pos]
    return (['mapquad:'] + clamp(MAP_COLS, 0x360, 1, 0x14, 0x1c, 'a3', None)
            + clamp(MAP_ROWS, 0x100, 0, 0x18, 0x20, None, 0x10)
            + [('j', SPRITE_SET), ('nop',), 'hide:', ('j', SPRITE_HIDE), ('nop',)])


def patch_exe(exe, bak):
    # decompressor 0x80023cf4: single bytes 0x20-0x72 stood for hiragana, 0x73-0x76 for
    # punctuation; copy every single byte < 0x80 so ASCII reaches the printer
    expect(exe, 0x80023d10, [0x2c420020])
    poke(exe, 0x80023d10, [0x2c420080])
    lines = text_read(POOL) + part_load()
    code = asm.assemble(POOL, lines)
    lab = asm.labels(POOL, lines)
    put(exe, POOL, code)
    at = tokens.patch(exe, bak, POOL + len(code), put, expect, peek, STRINGS)
    lines = map_quad()
    for a in MAP_QUADS:
        expect(exe, a, [0x0c000000 | (SPRITE_SET >> 2 & 0x3ffffff)])
        put(exe, a, asm.assemble(a, [('jal', at)]))
    code = asm.assemble(at, lines)
    put(exe, at, code)
    at += len(code)
    assert at <= POOL_END
    # text read 0x80023c64(ctx, offset, dst): was base (u16 at ctx+0x920) + offset, 0x400 B
    expect(exe, 0x80023c64, [0x27bdffc0, 0xafbf003c])
    put(exe, 0x80023c64, asm.assemble(0x80023c64, [('j', lab['read']), ('ori', 'a3', 'zero', 0x400)]))
    # the dialogue block reader reads BLOCK_MAX into its grown frame
    expect(exe, 0x80026a64, [0x0c008f19, 0x27a60010])
    put(exe, 0x80026a64, asm.assemble(0x80026a64, [('jal', lab['big'])]))
    grow_talk_frame(exe)
    # part load 0x80023b60: read the remap table instead of the u16 part base
    expect(exe, 0x80023c10, [0x8e450004, 0, 0x00052840, 0x27a60050, 0x0c01bdd8, 0x34070002, 0x93a30050, 0x93a20051,
                             0, 0x00021200, 0x00621821, 0xa6430920])
    put(exe, 0x80023c10, asm.assemble(0x80023c10, [
        ('lw', 'a1', 4, 's2'),
        ('addiu', 'a0', 'sp', 0x10),
        ('jal', lab['part']),
        ('addiu', 'a2', 'sp', 0x50)] + [('nop',)] * 8))
    return at


def patch_data(exe, out):
    """EXE values that depend on the rebuilt IP.E2 / DMES.E2"""
    d = out.get('SNR/IP.E2')
    if d is not None:                    # u32 part lengths (the loader reads exactly that many bytes)
        base = list(struct.unpack_from('<%dH' % ip.PARTS, d)) + [len(d)]
        expect(exe, ip.SIZES, [0x287d, 0x1ad7, 0x1dc8, 0x19cb, 0x255b])
        poke(exe, ip.SIZES, [base[k + 1] - base[k] for k in range(ip.PARTS)])
    d = out.get('SNR/DMES.E2')
    if d is not None:
        # 0x8003dc54 ori a2, zero, 0x9f6: read length; 0x8003dc88 ori a3, zero, 0x73: the byte that
        # stood for a line break (an 's' in English) -> 0x01 (never in the text)
        expect(exe, 0x8003dc54, [0x340609f6])
        poke(exe, 0x8003dc54, [0x34060000 | len(d)])
        expect(exe, 0x8003dc88, [0x34070073])
        poke(exe, 0x8003dc88, [0x34070001])
        # the loop that skips the entries of other officers steps 2 bytes and ignores break bytes (an odd
        # number of breaks misaligned every later entry: no line shown, session 13) -> 1 byte (LF is never
        # a byte of SJIS or of the 1-byte kana): addiu a0, a0, 2 / 2 / -2 -> 1 / 1 / -1
        expect(exe, 0x8003dd24, [0x24840002])
        poke(exe, 0x8003dd24, [0x24840001])
        expect(exe, 0x8003dd34, [0x24840002, 0x2484fffe])
        poke(exe, 0x8003dd34, [0x24840001, 0x2484ffff])


def cut(b, n):
    """first n bytes of SJIS text, not splitting a pair"""
    i = 0
    while i < len(b) and i < n:
        i += 2 if b[i] >= 0x80 else 1
    return b[:i]


def chapter_files(test=False):
    if not test:
        out, done, errs = tl.english()
        if errs:
            sys.exit('\n'.join(errs) + '\n%d errors in tl/ (tools/tl.py check)' % len(errs))
        print('chapter text: %d segments translated' % done)
        return out
    out = {}
    for c, name in enumerate(snr.names()):
        pe = snr.file_entries(name)
        en = {}
        if test:
            for k, entries in enumerate(pe):
                for n, (_, kind, val) in enumerate(entries):
                    segs = [(None, val)] if kind == 'plain' else list(enumerate(r for _, r in val))
                    for j, raw in segs:
                        tag = '%d.%d.%d%s ' % (c, k, n, '' if j is None else '.%d' % j)
                        en[k, n, j] = tag.encode() + cut(snr.expand(raw), 24)
        out['SNR/%s.E2' % name] = snr.rebuild(pe, en)
    return out


def build_files(disc, recs, test=False):
    """{iso path: bytes} of every rebuilt file"""
    out = chapter_files(test)
    exe = bytearray(disc.file(iso.EXE_NAME, recs))
    n, moved, pool, extra = progstr.apply({'PROG': exe}, {'PROG': bytes(exe)}, (STRINGS, POOL - STRINGS))
    put(exe, STRINGS, extra)
    print('program strings: %d written, %d moved, %d bytes in the font space (%d free there and in slots)'
          % (n, moved, len(extra), pool.room()))
    bak = bytearray(disc.file(tokens.BAKDATA, recs))
    at = patch_exe(exe, bak)
    out[tokens.BAKDATA] = bytes(bak)
    _, numbers = tokens.strings_blob(tokens.NAMES, STRINGS)
    out[tokens.HEXZ] = bytes(tokens.patch_hexz(disc.file(tokens.HEXZ, recs), numbers))
    out.update(gfx.build({f: disc.file(f, recs) for f in (gfx.MARK, gfx.NL)}))
    patch_data(exe, out)
    print('pool: %d bytes free' % (POOL_END - at))
    out[iso.EXE_NAME] = bytes(exe)
    return out


def write(clean, out, files):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    moved = iso.write_image(clean, out, files)
    print('rebuilt %s%s' % (out, ' (moved: %s)' % ', '.join(moved) if moved else ''))
    if set(moved) & set(FIXED):
        sys.exit('%s moved on the disc' % ', '.join(set(moved) & set(FIXED)))
    iso.verify(out, files)
    audio = []
    for t, src in enumerate(setup.AUDIO, 2):
        dst = out.replace('_track1.bin', '_track%d.bin' % t)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
        audio.append(dst)
    iso.write_cue(out.replace('_track1.bin', '.cue'), out, audio)
    patch = os.path.join(os.path.dirname(out), 'sangokushi_koumeiden_en.xdelta')
    try:
        subprocess.run(['xdelta3', '-e', '-f', '-9', '-S', 'djw', '-B', str(1 << 28), '-s', clean, out, patch], check=True)
        print('patch %s (%d bytes)' % (patch, os.path.getsize(patch)))
    except FileNotFoundError:
        print('xdelta3 not installed; skipped patch')
    return moved


def main():
    args = sys.argv[1:]
    test = '--test' in args
    args = [a for a in args if a != '--test']
    clean = args[0] if args else setup.CLEAN
    out = args[1] if len(args) > 1 else OUT
    disc = iso.Disc(clean)
    write(clean, out, build_files(disc, disc.records(), test))


if __name__ == '__main__':
    main()
