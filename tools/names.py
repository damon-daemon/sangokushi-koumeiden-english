"""Speaker names of the chapter text (u16 speaker id of each speech, snr.py).

The game holds 512 person records in RAM at 0x80108410 + id * 0x38 (name +6, 6 B SJIS; reading
+13, 8 B half-width kana), filled at chapter start (0x80020a2c ...). Their source on the disc is not
pinned yet (SNR/BAKDATA.E2 holds part of them in 17-B records, not indexed by id), so the Japanese
names are taken from a save state (git-ignored script/speakers.json) and used for display only.

tl/names/speakers.json: one row per line, {"id": speaker, "en": English}. `init` fills it from the
spellings of the earlier projects (Eiketsuden officers, Sangokushi VI officers), matching the
Japanese name, else the reading.

usage:
    names.py snapshot [state.sav]   script/speakers.json from a save state (default sstates/s2_engtest.sav)
    names.py init                   tl/names/speakers.json: add matches for ids without English
    names.py show [--todo]          id, Japanese, reading, English
"""
import json, os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'emu'))
SNAP = os.path.join(ROOT, 'script', 'speakers.json')
TL_NAMES = os.path.join(ROOT, 'tl', 'names')
SPEAKERS = os.path.join(TL_NAMES, 'speakers.json')
RECORDS, COUNT, STRIDE = 0x108410, 512, 0x38
PROJECTS = os.path.expanduser('~/Projects')
EIKETSU = os.path.join(PROJECTS, 'sangokushi_eiketsuden_translation')
S6 = os.path.join(PROJECTS, 'sangokushi_6_puk_translation')


def _sjis(b):
    return b.split(b'\0')[0].decode('cp932', 'replace')


def snapshot(state):
    import ram
    m = ram.state_ram(state)
    rows = []
    for i in range(COUNT):
        r = m[RECORDS + i * STRIDE:RECORDS + (i + 1) * STRIDE]
        rows.append({'id': i, 'jp': _sjis(r[6:12]), 'kana': _sjis(r[13:21])})
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    dump(SNAP, rows)
    print('%s: %d records' % (SNAP, len(rows)))


def dump(path, rows):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('[\n' + ',\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n]\n')


def jp_rows():
    if not os.path.exists(SNAP):
        return {}
    return {r['id']: r for r in json.load(open(SNAP, encoding='utf-8'))}


def en_rows():
    if not os.path.exists(SPEAKERS):
        return {}
    return {r['id']: r['en'] for r in json.load(open(SPEAKERS, encoding='utf-8'))}


_cache = {}


def en_name(i):
    """display name of a speaker: English, else Japanese, else #id"""
    if not _cache:
        _cache['jp'], _cache['en'] = jp_rows(), en_rows()
    if i in _cache['en']:
        return _cache['en'][i]
    r = _cache['jp'].get(i)
    return r['jp'] if r and r['jp'] else '#%d' % i


def known():
    """-> ({Japanese: English}, {reading: English}) from the earlier projects"""
    by_jp, by_kana = {}, {}
    p = os.path.join(EIKETSU, 'extract', 'SNDT', 'BDATA1.DTA')
    if os.path.exists(p):
        d = open(p, 'rb').read()
        en = {r['id']: r['en'] for r in json.load(open(os.path.join(EIKETSU, 'tl', 'names', 'officers.json'),
                                                         encoding='utf-8'))}
        for i in range(384):
            r = d[i * 16:(i + 1) * 16]
            if i in en:
                by_jp.setdefault(_sjis(r[:6]), en[i])
                by_kana.setdefault(_sjis(r[6:14]), en[i])
    p = os.path.join(S6, 'script', 'names', 'officers.json')
    if os.path.exists(p):
        for r in json.load(open(p, encoding='utf-8')):
            if not r.get('en'):
                continue
            e = ' '.join(x for x in r['en'][:2] if x)
            by_jp.setdefault(r['jp'][0] + r['jp'][1], e)
            by_kana.setdefault(r['kana'], e)
    return by_jp, by_kana


def init():
    jp, en = jp_rows(), en_rows()
    if not jp:
        sys.exit('no %s: run names.py snapshot first' % SNAP)
    by_jp, by_kana = known()
    add = 0
    for i, r in jp.items():
        if i in en or not r['jp']:
            continue
        e = by_jp.get(r['jp']) or (by_kana.get(r['kana']) if r['kana'] else None)
        if e:
            en[i] = e
            add += 1
    os.makedirs(TL_NAMES, exist_ok=True)
    dump(SPEAKERS, [{'id': i, 'en': en[i]} for i in sorted(en)])
    print('%d added, %d in %s' % (add, len(en), SPEAKERS))


def show(todo=False):
    jp, en = jp_rows(), en_rows()
    for i, r in sorted(jp.items()):
        if r['jp'] and not (todo and i in en):
            print('%3d  %-6s %-8s %s' % (i, r['jp'], r['kana'], en.get(i, '-')))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == 'snapshot':
        snapshot(a[1] if len(a) > 1 else os.path.join(ROOT, 'sstates', 's2_engtest.sav'))
    elif a[0] == 'init':
        init()
    elif a[0] == 'show':
        show('--todo' in a)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
