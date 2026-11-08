"""Translation files of the game text: show, apply, check, stats; used by build.py.

Sources (tl/<src>/<part>.txt, English only, no Japanese):
  snr   SNR/SNRcM.E2 chapter text, parts SNRcM_k (snr.py)
  ip    SNR/IP.E2 town NPC lines, parts IP_k (ip.py; head shows the NPC label)
  dmes  SNR/DMES.E2 officer retreat lines, part DMES (dmes.py; head shows the officer)

A part file:

    # comment (a line starting with #)
    @<n>        plain entry n (snr.parse order)
    @<n>.<j>    speech j of dialogue entry n (the speaker is kept from the original)
    English text, possibly over several physical lines (joined with spaces); \\n = line break,
    \\n\\n = new page (choices: \\n between options).

See text.py for the kinds, the character set and the wrapping. A segment without English takes the
English of a segment with the same Japanese (translation memory, explicit wins); one with neither
keeps its Japanese.

usage:
    tl.py show  SNR0M_0 [from] [to] [--todo]  # Japanese segments (from/to = entry numbers)
    tl.py apply SNR0M_0 batch.txt             # validate a batch, merge it into tl/snr/SNR0M_0.txt
    tl.py check [SNR0M_0]                     # validate everything in tl/
    tl.py stats
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import dmes, ip, names as speakers, snr, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl')
_REC = re.compile(r'@(\d+)(?:\.(\d+))?\s*$')


class Part:
    """One part (scene) of a chapter file: segments and their kinds."""
    src = 'snr'

    def __init__(self, name, k, entries):
        self.name, self.k, self.entries = name, k, entries
        self.segs, self.kinds, self.who = {}, {}, {}   # (n, j or None) -> Japanese / kind / speaker
        if entries is None:
            return
        for n, (_, kind, val) in enumerate(entries):
            if kind == 'plain':
                jp = snr.show(val)
                self.segs[n, None], self.kinds[n, None] = jp, text.kind_of(jp)
            else:
                for j, (who, raw) in enumerate(val):
                    self.segs[n, j], self.kinds[n, j], self.who[n, j] = snr.show(raw), 'talk', who

    @property
    def id(self):
        return '%s_%d' % (self.name, self.k) if self.k is not None else self.name

    def label(self, k):
        return '[%s]' % speakers.en_name(self.who[k])


_NPC = None


def npc_label(a):
    global _NPC
    if _NPC is None:
        d = open(os.path.join(snr.SNR, 'BAKDATA.E2'), 'rb').read()
        _NPC = [d[9 * i:9 * i + 8].split(b'\0')[0].decode('cp932', 'replace') for i in range(257)]
    return _NPC[a]


class IpPart(Part):
    """IP_k: one string per NPC table entry"""
    src = 'ip'

    def __init__(self, k, labels, strs):
        super().__init__('IP', k, None)
        for n, (a, raw) in enumerate(zip(labels, strs)):
            self.segs[n, None], self.kinds[n, None], self.who[n, None] = snr.show(raw, True), 'npc', a

    def label(self, k):
        return '[%s]' % npc_label(self.who[k])


class DmesPart(Part):
    """DMES: one retreat line per officer; Japanese shown with the padding as line breaks"""
    src = 'dmes'

    def __init__(self, entries):
        super().__init__('DMES', None, None)
        for n, (who, raw) in enumerate(entries):
            jp = raw.decode('cp932', 'replace')
            ls = [jp[i:i + 16].rstrip('\u3000') for i in range(0, len(jp), 16)]
            self.segs[n, None], self.kinds[n, None], self.who[n, None] = '\\n'.join(ls), 'dmes', who


def names():
    return [p.id for p in load_all()]


_parts = None


def load_all():
    global _parts
    if _parts is None:
        _parts = [Part(name, k, es) for name in snr.names() for k, es in enumerate(snr.file_entries(name))]
        _parts += [IpPart(k, a, s) for k, (_, a, s) in enumerate(ip.file_parts())]
        _parts.append(DmesPart(dmes.parse()))
    return _parts


def part(pid):
    for p in load_all():
        if p.id == pid:
            return p
    sys.exit('no part %s (names like SNR0M_0, IP_0, DMES)' % pid)


def key_str(k):
    return '@%d' % k[0] if k[1] is None else '@%d.%d' % k


def order(k):
    return k[0], -1 if k[1] is None else k[1]


def head(p, k):
    if k in p.who:
        return '%s %s %s' % (key_str(k), p.kinds[k], p.label(k))
    return '%s %s' % (key_str(k), p.kinds[k])


def dump(p, f, a=0, z=None, skip=()):
    n = 0
    for k, jp in sorted(p.segs.items(), key=lambda i: order(i[0])):
        if k[0] >= a and (z is None or k[0] <= z) and k not in skip:
            f.write('%s\n%s\n\n' % (head(p, k), jp.replace('<0d>', '')))
            n += 1
    return n


def tl_path(pid):
    return os.path.join(TL, part(pid).src, pid + '.txt')


def parse_tl(path):
    """-> {(n, j or None): English}"""
    out, key, buf = {}, None, []

    def flush():
        if key is not None:
            out[key] = ' '.join(x.strip() for x in buf if x.strip())
    if not os.path.exists(path):
        return out
    for ln in open(path, encoding='utf-8'):
        ln = ln.rstrip('\n')
        if ln.startswith('#'):
            continue
        m = _REC.match(ln)
        if m:
            flush()
            key, buf = (int(m.group(1)), None if m.group(2) is None else int(m.group(2))), []
            if key in out:
                raise ValueError('%s: %s twice' % (path, key_str(key)))
        elif ln.startswith('@'):
            raise ValueError('%s: bad header %r (write only @n or @n.j)' % (path, ln))
        elif key is not None:
            if ln.strip() and buf and not buf[-1].strip():
                raise ValueError('%s: %s: blank line inside an entry (write \\n\\n for a new page)' % (path, key_str(key)))
            buf.append(ln)
        elif ln.strip():
            raise ValueError('%s: text before the first @ line: %r' % (path, ln))
    flush()
    return out


def write_tl(pid, recs):
    os.makedirs(os.path.dirname(tl_path(pid)), exist_ok=True)
    with open(tl_path(pid), 'w', encoding='utf-8') as f:
        for k in sorted(recs, key=order):
            f.write('%s\n%s\n\n' % (key_str(k), recs[k]))


def load_tls():
    return {p.id: parse_tl(tl_path(p.id)) for p in load_all()}


def memory(tls):
    """{(kind, Japanese): English} from every explicit segment"""
    tm = {}
    for p in load_all():
        for k, en in tls.get(p.id, {}).items():
            if k in p.segs:
                tm.setdefault((p.kinds[k], p.segs[k]), en)
    return tm


def lookup(p, k, recs, tm):
    return recs.get(k, tm.get((p.kinds[k], p.segs[k])))


def english(tls=None):
    """-> ({iso path: rebuilt file}, translated count, errors). Every chapter file is rebuilt (moved
    layout + remap tables, see snr.rebuild), also IP.E2 and DMES.E2."""
    tls = tls if tls is not None else load_tls()
    tm = memory(tls)
    by_file, errs, done = {}, [], 0
    for p in load_all():
        recs = tls.get(p.id, {})
        errs += ['%s %s: no such segment' % (p.id, key_str(k)) for k in recs if k not in p.segs]
        en = by_file.setdefault(p.name, ([], {}))
        if p.src == 'snr':
            en[0].append(p.entries)
        for k in p.segs:
            e = lookup(p, k, recs, tm)
            if e is None:
                continue
            es = text.check(e, p.kinds[k])
            if es:
                errs += ['%s %s: %s' % (p.id, key_str(k), x) for x in es]
                continue
            key = {'snr': (p.k,) + k, 'ip': (p.k, k[0]), 'dmes': k[0]}[p.src]
            en[1][key] = text.encode(e, p.kinds[k])
            done += 1
    out = {}
    for name, (pe, en) in by_file.items():
        try:
            if name == 'IP':
                out['SNR/IP.E2'] = ip.rebuild(en)[0]
            elif name == 'DMES':
                out['SNR/DMES.E2'] = dmes.rebuild(en)
            else:
                out['SNR/%s.E2' % name] = snr.rebuild(pe, en)
        except AssertionError as e:
            errs.append('%s: %s' % (name, e))
    return out, done, errs


def show(pid, a=0, z=None, todo=False):
    p, tls = part(pid), load_tls()
    recs, tm = tls[pid], memory(tls)
    skip = {k for k in p.segs if lookup(p, k, recs, tm) is not None} if todo else ()
    dump(p, sys.stdout, a, z, skip)


def apply(pid, batch):
    p = part(pid)
    new = parse_tl(batch)
    errs = []
    for k, en in new.items():
        if k not in p.segs:
            errs.append('%s: no such segment in %s' % (key_str(k), pid))
        else:
            errs += ['%s: %s' % (key_str(k), x) for x in text.check(en, p.kinds[k])]
    if errs:
        sys.exit('\n'.join(errs) + '\n%d errors, nothing written' % len(errs))
    recs = parse_tl(tl_path(pid))
    recs.update(new)
    write_tl(pid, recs)
    print('%s: %d segments merged (%d in file)' % (pid, len(new), len(recs)))


def check(only=None):
    tls = load_tls()
    if only:
        part(only)
        tls = {n: (v if n == only else {}) for n, v in tls.items()}
    out, done, errs = english(tls)
    big = sorted(((len(d), n) for n, d in out.items()), reverse=True)[:3]
    print('largest: ' + ', '.join('%s %d' % (n, s) for s, n in big))
    print('\n'.join(errs))
    print('%d segments translated, %d errors' % (done, len(errs)))
    return not errs


def stats():
    tls = load_tls()
    tm = memory(tls)
    tot = done = 0
    for p in load_all():
        t = len(p.segs)
        d = sum(1 for k in p.segs if lookup(p, k, tls[p.id], tm) is not None)
        tot, done = tot + t, done + d
        if d:
            print('%s: %4d / %4d' % (p.id, d, t))
    print('total: %d / %d segments (%.1f%%)' % (done, tot, 100.0 * done / max(tot, 1)))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == 'show':
        nums = [int(x) for x in a[2:] if not x.startswith('--')]
        show(a[1], *(nums + [0, None])[:2], todo='--todo' in a)
    elif a[0] == 'apply':
        apply(a[1], a[2])
    elif a[0] == 'check':
        sys.exit(0 if check(a[1] if len(a) > 1 else None) else 1)
    elif a[0] == 'stats':
        stats()
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
