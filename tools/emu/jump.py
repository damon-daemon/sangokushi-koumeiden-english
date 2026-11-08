"""jump.py CHAPTER PART: at the game's next part load (0x80023b60(ctx): reads ctx+0 chapter byte -> SNRcD/M names,
ctx+4 u16 part -> D part to the script buffer, M part base), set chapter + part first. Test shortcut: flags, party and
the scene set-up stay as they are. Headless emulator running; start this, then trigger a part load (e.g. NEW GAME and a
choice at the prologue menu, or end the current scene).
Optional START (default 0): script offset in the D part to start at (ctx+8, set by the "go to part" opcode
0x8002593c; the prologue's "Skip" choice passes a mid-part offset that only fits SNR0D part 0: session 23).
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdbmem import G, wait_break

PART_LOAD = 0x80023b60
ch, part = int(sys.argv[1]), int(sys.argv[2])
start = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
g = G()
g.cmd('?')
pkt, r = wait_break(g, PART_LOAD, 120)
ctx = r['r4']
old = struct.unpack('<BxxxHxxI', g.read(ctx, 12))
print('part load: ctx %08x, chapter %d part %d start %#x -> %d %d %#x' % (ctx, old[0], old[1], old[2], ch, part, start))
g.cmd('M%x,1:%02x' % (ctx, ch))
g.cmd('M%x,2:%s' % (ctx + 4, struct.pack('<H', part).hex()))
g.cmd('M%x,4:%s' % (ctx + 8, struct.pack('<I', start).hex()))
g.resume()
