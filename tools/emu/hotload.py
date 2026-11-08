"""hotload.py [--dry] [image_track1.bin]: put the built program's patches into the running headless emulator.

A save state keeps the program of the build it was made with. This writes every byte where the built
SLPS_006.88 differs from the clean one and from the RAM (code hooks, moved strings, name tables, the font
space), so an old state runs the new build's code without replaying from boot. Files read from the disc
(SNR, BAKDATA, HEXZ ...) come from the image the emulator has open; records already copied into RAM
(person / NPC / item records) keep their old bytes.
The CPU is stopped in the VSync wait (SAFE) first: hook code moves between builds, and a write while a hook
runs (or with a hook's return address on the stack) crashes the game.
Run from the project root with the headless emulator running (GDB server on).
"""
import os, sys
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tools/emu')
import gdbmem, iso, setup

BASE = 0x80010000
SAFE = 0x8008812c                        # VSync wait loop (main loop idle)
dry = '--dry' in sys.argv
ONLY = os.environ.get('HOT_ONLY')   # debug: 'lo-hi,lo-hi' hex ranges to write
args = [a for a in sys.argv[1:] if a != '--dry']
img = args[0] if args else 'build/sangokushi_koumeiden_en_track1.bin'
d = iso.Disc(img)
new = d.file(iso.EXE_NAME, d.records())[0x800:]
clean = open(os.path.join('extract', iso.EXE_NAME), 'rb').read()[0x800:]
g = gdbmem.G()
g.cmd('?')
gdbmem.wait_break(g, SAFE, 10)
ram = g.read(BASE, len(new))
runs, i = [], 0
while i < len(new):
    if new[i] != ram[i] and new[i] != clean[i]:
        j = i
        while j < len(new) and (new[j] != ram[j] and new[j] != clean[j] or j - i < 16 and new[j] != ram[j]):
            j += 1
        runs.append((i, j)); i = j
    else:
        i += 1
if ONLY:
    rr = [tuple(int(x, 16) - BASE for x in r.split('-')) for r in ONLY.split(',')]
    runs = [(a, b) for a, b in runs if any(lo <= a < hi for lo, hi in rr)]
total = 0
if dry:
    for a, b in runs:
        print('%08x %5d' % (BASE + a, b - a))
    g.resume(); sys.exit()
for a, b in runs:
    for k in range(a, b, 0x200):
        e = min(b, k + 0x200)
        r = g.cmd('M%x,%x:%s' % (BASE + k, e - k, new[k:e].hex()))
        assert r == 'OK', r
    total += b - a
print('%d runs, %d bytes written' % (len(runs), total))
g.resume()
