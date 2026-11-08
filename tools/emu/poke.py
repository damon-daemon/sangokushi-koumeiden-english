"""poke.py ADDR WORD [ADDR WORD ...]: write 32-bit words into the running headless emulator's RAM (shared memory
export). For one-instruction fixes on an old state: code not yet compiled since the state load picks it up."""
import glob, os, struct, sys
f = sorted(glob.glob('/dev/shm/duckstation_*'), key=os.path.getmtime)[-1]
a = [int(x, 0) for x in sys.argv[1:]]
with open(f, 'r+b') as h:
    for va, w in zip(a[::2], a[1::2]):
        h.seek(va & 0x1fffff); h.write(struct.pack('<I', w))
