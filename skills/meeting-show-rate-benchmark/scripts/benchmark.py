#!/usr/bin/env python3
"""Compare your booked B2B meetings with Growth Cab's open dataset of 1,380 meetings.

Standard library only. The benchmark (CC BY 4.0) is in benchmark.json next to this script.

    python3 benchmark.py meetings.csv                  # one row per booked meeting
    python3 benchmark.py meetings.csv --dayfirst       # dates like 31/12/2026
    python3 benchmark.py --booked 120 --held 78 --noshow 22 --rescheduled 14 --cancelled 6
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

BENCH = json.loads((Path(__file__).parent / 'benchmark.json').read_text())
OUTCOMES = ['held', 'noshow', 'rescheduled', 'cancelled']
WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
BUCKETS = ['0-2 days', '3-7 days', '8-14 days', '15-30 days', '31+ days']
COLS = {
    'booked': ['booked', 'booked at', 'booked on', 'booking date', 'date booked', 'created', 'created at',
               'scheduled on', 'set on', 'date set'],
    'meeting': ['meeting date', 'meeting', 'meeting at', 'start', 'start time', 'event date', 'date of meeting',
                'appointment date', 'date'],
    'outcome': ['outcome', 'status', 'result', 'meeting status', 'meeting outcome'],
    'title': ['title', 'job title', 'role', 'position', 'prospect title'],
}
MAP = [
    ('noshow', r'no.?show|didn.?t show|did not show|ghost'),
    ('rescheduled', r'resched|moved|postpon'),
    ('cancelled', r'cancel'),
    ('held', r'held|done|complete|attended|showed|took place|happened|yes|occurred|fatto'),
]
SENIORITY = [
    ('C-level / founder / owner', r'\b(ceo|coo|cfo|cto|cmo|cio|cro|cso|cdo|cpo|chief|founder|co-founder|cofounder|owner|president|managing director|general manager|partner)\b'),
    ('VP', r'\b(vp|vice president|svp|evp)\b'),
    ('Head / Director', r'\b(head|director)\b'),
    ('Manager', r'\bmanager\b'),
]


def norm(h):
    return re.sub(r'[\s_]+', ' ', h.strip().lower())


def pick_columns(headers):
    normed = {norm(h): h for h in headers}
    found = {}
    for key, names in COLS.items():
        for n in names:
            if norm(n) in normed and normed[norm(n)] not in found.values():
                found[key] = normed[norm(n)]
                break
    return found


def parse_date(s, dayfirst):
    s = (s or '').strip()
    if not s:
        return None
    s = re.split(r'[T ]', s)[0] if re.match(r'^\d{4}-\d{2}-\d{2}', s) else s.split(' ')[0]
    fmts = ['%Y-%m-%d', '%Y/%m/%d'] + (['%d/%m/%Y', '%d/%m/%y', '%d.%m.%Y', '%d-%m-%Y'] if dayfirst
                                        else ['%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%d.%m.%Y'])
    for f in fmts:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def outcome(v):
    v = (v or '').strip().lower()
    for key, pat in MAP:
        if re.search(pat, v):
            return key
    return None


def seniority(t):
    t = (t or '').lower()
    if not t.strip():
        return None
    for label, pat in SENIORITY:
        if re.search(pat, t):
            return label
    return 'Other'


def bucket(days):
    return '0-2 days' if days <= 2 else '3-7 days' if days <= 7 else '8-14 days' if days <= 14 else \
        '15-30 days' if days <= 30 else '31+ days'


def rates(items):
    c = Counter(items)
    n = sum(c.values())
    return n, {k: (c[k] / n if n else 0.0) for k in OUTCOMES}


def pct(x):
    return f'{100 * x:.1f}%'


def table(title, rows):
    print(f'\n{title}')
    print(f"  {'Segment':<28}{'Your n':>8}{'You':>9}{'Benchmark':>11}{'Diff':>9}{'Bench n':>9}")
    for seg, n, mine, bench, bn in rows:
        diff = '' if bench is None or n == 0 else f'{100 * (mine - bench):+.1f}'
        small = ' (small)' if 0 < n < 30 else ''
        print(f"  {seg:<28}{n:>8}{pct(mine) if n else '-':>9}{pct(bench) if bench is not None else '-':>11}{diff:>9}{bn if bn else '-':>9}{small}")


def summary_mode(a):
    total = a.held + a.noshow + a.rescheduled + a.cancelled
    booked = a.booked or total
    if not booked:
        sys.exit('Give at least --booked and --held.')
    o = BENCH['overall']
    print(f"Your {booked} booked meetings compared with {BENCH['n']:,} booked B2B meetings (Growth Cab open data)")
    rows = []
    for k, label in zip(OUTCOMES, ['Took place', 'No-show', 'Rescheduled', 'Cancelled']):
        mine = getattr(a, k) / booked
        rows.append((label, booked, mine, o[k], o['n']))
    table('Outcome shares', rows)


def csv_mode(a):
    with open(a.csv, newline='', encoding='utf-8-sig') as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.DictReader(f, dialect=dialect))
    if not rows:
        sys.exit('The file has no data rows.')
    cols = pick_columns(rows[0].keys())
    if 'outcome' not in cols:
        sys.exit('No outcome/status column found. Rename it to "outcome" (values: held, no-show, rescheduled, cancelled).')
    skipped = Counter()
    recs = []
    for r in rows:
        oc = outcome(r.get(cols['outcome']))
        if not oc:
            skipped['unknown or pending outcome'] += 1
            continue
        b = parse_date(r.get(cols.get('booked', ''), ''), a.dayfirst) if 'booked' in cols else None
        m = parse_date(r.get(cols.get('meeting', ''), ''), a.dayfirst) if 'meeting' in cols else None
        recs.append({'o': oc, 'b': b, 'm': m, 't': seniority(r.get(cols['title'])) if 'title' in cols else None})
    if not recs:
        sys.exit('No meeting with a recognizable outcome.')

    n, mine = rates(r['o'] for r in recs)
    o = BENCH['overall']
    print(f"{a.csv}: {n} meetings with a known outcome"
          + (f", {sum(skipped.values())} skipped ({', '.join(f'{k}: {v}' for k, v in skipped.items())})" if skipped else ''))
    print('Columns used: ' + ', '.join(f'{k}={v}' for k, v in cols.items()))
    table('Outcome shares vs benchmark', [(lbl, n, mine[k], o[k], o['n']) for k, lbl in
                                          zip(OUTCOMES, ['Took place', 'No-show', 'Rescheduled', 'Cancelled'])])

    by_lead = defaultdict(list)
    lead_days = []
    for r in recs:
        if r['b'] and r['m'] and 0 <= (r['m'] - r['b']).days <= 365:
            d = (r['m'] - r['b']).days
            lead_days.append(d)
            by_lead[bucket(d)].append(r['o'])
    if lead_days:
        bl = BENCH['by_lead']
        table('Took place, by days from booking to meeting',
              [(bk, len(by_lead[bk]), rates(by_lead[bk])[1]['held'], bl[bk]['held'], bl[bk]['n']) for bk in BUCKETS])
        lead_days.sort()
        med = lead_days[len(lead_days) // 2] if len(lead_days) % 2 else (lead_days[len(lead_days) // 2 - 1] + lead_days[len(lead_days) // 2]) / 2
        within7 = sum(1 for d in lead_days if d <= 7) / len(lead_days)
        expected = sum(len(by_lead[bk]) * bl[bk]['held'] for bk in BUCKETS) / len(lead_days)
        actual = sum(1 for bk in BUCKETS for x in by_lead[bk] if x == 'held') / len(lead_days)
        print(f"\n  Median days from booking to meeting: you {med:g}, benchmark {BENCH['lead']['median']:g}")
        print(f"  Scheduled within 7 days: you {pct(within7)}, benchmark {pct(BENCH['lead']['within_7'])}")
        print(f"  With your lead-time mix, the benchmark expects {pct(expected)} to take place; you got {pct(actual)} "
              f"({100 * (actual - expected):+.1f} points).")

    by_wd = defaultdict(list)
    for r in recs:
        if r['m']:
            by_wd[WD[r['m'].weekday()]].append(r['o'])
    if by_wd:
        bw = BENCH['by_weekday']
        table('Took place, by weekday of the meeting',
              [(d, len(by_wd[d]), rates(by_wd[d])[1]['held'], bw[d]['held'] if d in bw else None,
                bw[d]['n'] if d in bw else None) for d in WD if by_wd[d]])

    by_sen = defaultdict(list)
    for r in recs:
        if r['t']:
            by_sen[r['t']].append(r['o'])
    if by_sen:
        bs = BENCH['by_seniority']
        table('No-show rate, by seniority of the prospect',
              [(s, len(by_sen[s]), rates(by_sen[s])[1]['noshow'], bs[s]['noshow'] if s in bs else None,
                bs[s]['n'] if s in bs else None) for s in list(bs) + ['VP'] if by_sen[s]])


def main():
    ap = argparse.ArgumentParser(description='Benchmark your B2B meeting show rate')
    ap.add_argument('csv', nargs='?')
    ap.add_argument('--dayfirst', action='store_true', help='dates are day/month/year')
    for k in ['booked'] + OUTCOMES:
        ap.add_argument(f'--{k}', type=int, default=0)
    a = ap.parse_args()
    if a.csv:
        csv_mode(a)
    else:
        summary_mode(a)
    print(f"\nBenchmark: {BENCH['n']:,} booked B2B sales meetings, {BENCH['clients']} clients, "
          f"{BENCH['period'][0]} to {BENCH['period'][1]}, mostly Italian and European companies. "
          f"Data CC BY 4.0, Growth Cab: {BENCH['url']}")
    print(f"Interactive version: {BENCH['calculator']}")


if __name__ == '__main__':
    main()
