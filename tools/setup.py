"""Check your own disc image and create the working folders extract/ and script/.

extract/ holds the files of the disc, script/ the Japanese text (one file per chapter, same keys
as tl/), so both are generated on each machine and never distributed. Run this once after
cloning, then tools/build.py.

usage: .venv/bin/python tools/setup.py [track1.bin]
"""
import hashlib, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import iso

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACT = os.path.join(ROOT, 'extract')
SCRIPT = os.path.join(ROOT, 'script')
CLEAN = os.path.join(ROOT, 'sangokushi_koumeiden_track1.bin')
CLEAN_SHA1 = 'db5e32a8b879924862e72e3337be2c710da687e2'
# CD audio track 2: copied next to the rebuilt track 1, never patched
AUDIO = [os.path.join(ROOT, 'sangokushi_koumeiden_track2.bin')]
AUDIO_SHA1 = ['7c8508996d34d2a39fd75a8fab58e2c9b766b09b']


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def check_clean(path, want=CLEAN_SHA1):
    digest = sha1(path)
    if digest != want:
        sys.exit('%s: SHA-1 %s does not match the clean dump (%s)' % (path, digest, want))


def extract(disc):
    n = 0
    for name, lba, size in disc.walk():
        if name.endswith(('.DA', '.STR')):
            continue                     # CD-DA entry, Form 2 movies
        p = os.path.join(EXTRACT, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(disc.read(lba, size))
        n += 1
    return n


def export_script():
    """script/snr/SNRcM_k.txt: Japanese of each part, same keys as tl/snr/"""
    import snr
    os.makedirs(os.path.join(SCRIPT, 'snr'), exist_ok=True)
    total = 0
    for name in snr.names():
        for k, entries in enumerate(snr.file_entries(name)):
            with open(os.path.join(SCRIPT, 'snr', '%s_%d.txt' % (name, k)), 'w', encoding='utf-8') as f:
                for n, (_, kind, val) in enumerate(entries):
                    if kind == 'plain':
                        f.write('@%d plain\n%s\n\n' % (n, snr.show(val)))
                        total += 1
                    else:
                        for j, (who, raw) in enumerate(val):
                            f.write('@%d.%d talk [%d]\n%s\n\n' % (n, j, who, snr.show(raw)))
                            total += 1
    return total


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else CLEAN
    check_clean(path)
    if path == CLEAN:
        for p, want in zip(AUDIO, AUDIO_SHA1):
            check_clean(p, want)
    print('extract/: %d files' % extract(iso.Disc(path)))
    print('script/snr: %d segments' % export_script())
    print('ready; now run tools/build.py')


if __name__ == '__main__':
    main()
