"""jump.py CHAPTER PART: at the game's next part load (0x80023b60(ctx): reads ctx+0 chapter byte -> SNRcD/M names,
ctx+4 u16 part -> D part to the script buffer, M part base), set chapter + part first. Test shortcut: flags, party and
the scene set-up stay as they are. Headless emulator running; start this, then trigger a part load (e.g. NEW GAME and a
choice at the prologue menu, or end the current scene).
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdbmem import G, wait_break

PART_LOAD = 0x80023b60
ch, part = int(sys.argv[1]), int(sys.argv[2])
g = G()
g.cmd('?')
pkt, r = wait_break(g, PART_LOAD, 120)
ctx = r['r4']
old = struct.unpack('<BxxxH', g.read(ctx, 6))
print('part load: ctx %08x, chapter %d part %d -> %d %d' % (ctx, old[0], old[1], ch, part))
g.cmd('M%x,1:%02x' % (ctx, ch))
g.cmd('M%x,2:%s' % (ctx + 4, struct.pack('<H', part).hex()))
g.resume()
