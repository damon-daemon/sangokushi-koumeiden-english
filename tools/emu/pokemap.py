"""pokemap.py: write the map-quad clamp (build.py map_quad + its 12 call sites) from the built disc's program into the
running emulator's RAM, for testing on a state that holds an older program (run before the battle code is compiled)."""
import os, struct, subprocess, sys
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(R, 'tools')); import build
LBA = 287522
with open(build.OUT, 'rb') as f:
    def rd(va, n):
        out, off = b'', va - 0x80010000 + 0x800
        while len(out) < n:
            f.seek((LBA + off // 2048) * 2352 + 24 + off % 2048); k = min(n - len(out), 2048 - off % 2048)
            out += f.read(k); off += k
        return out
    tgt = (struct.unpack('<I', rd(build.MAP_QUADS[0], 4))[0] & 0x3ffffff) << 2 | 0x80000000
    args = []
    for a in build.MAP_QUADS:
        args += [a, struct.unpack('<I', rd(a, 4))[0]]
    code = rd(tgt, 4 * len([l for l in build.map_quad() if not isinstance(l, str)]))
    for i in range(0, len(code), 4):
        args += [tgt + i, struct.unpack_from('<I', code, i)[0]]
print('mapquad at %#x, %d words' % (tgt, len(args) // 2))
subprocess.run([sys.executable, os.path.join(R, 'tools/emu/poke.py')] + ['%#x' % x for x in args], check=True)
