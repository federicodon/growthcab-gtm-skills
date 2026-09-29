#!/usr/bin/env python3
"""Cold email domain health check (Growth Cab, https://www.growthcab.com).

Checks the public DNS setup of one or more sending domains and prints a score out of 100.
Standard library only. DNS lookups go through DNS over HTTPS (Cloudflare, Google as fallback);
the Spamhaus DBL lookup uses your system resolver, because Spamhaus refuses public resolvers.

    python3 check_domain.py example.com
    python3 check_domain.py example.com example.net --selector s2024 --json
"""
import argparse
import json
import socket
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DOH = ['https://cloudflare-dns.com/dns-query', 'https://dns.google/resolve']
UA = 'growthcab-domain-check/1.0 (+https://www.growthcab.com)'
COMMON_SELECTORS = [
    'google', 'selector1', 'selector2', 'default', 'k1', 'k2', 'k3', 's1', 's2', 'mail', 'dkim',
    'smtp', 'mx', 'zoho', 'zmail', 'protonmail', 'protonmail2', 'protonmail3', 'mandrill', 'mailjet',
    'sendgrid', 'smtpapi', 'everlytickey1', 'everlytickey2', 'mxvault', 'sig1', 'key1', 'key2',
]
TYPES = {'A': 1, 'MX': 15, 'TXT': 16, 'AAAA': 28, 'CNAME': 5}


def doh(name, rtype):
    """Return (status, [answer data]) for name/rtype. status 0 = NOERROR, 3 = NXDOMAIN."""
    last_error = None
    for base in DOH:
        url = f'{base}?name={urllib.parse.quote(name)}&type={rtype}'
        req = urllib.request.Request(url, headers={'accept': 'application/dns-json', 'user-agent': UA})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.load(r)
        except Exception as e:  # try the next resolver
            last_error = e
            continue
        answers = [a['data'] for a in data.get('Answer', []) if a.get('type') == TYPES.get(rtype)]
        return data.get('Status', 2), answers
    raise RuntimeError(f'DNS lookup failed for {name} {rtype}: {last_error}')


def txt_records(name):
    status, answers = doh(name, 'TXT')
    # TXT data comes quoted and sometimes split into several strings
    out = []
    for a in answers:
        parts = [p for p in a.split('"') if p.strip() and p != ' ']
        out.append(''.join(parts) if parts else a)
    return status, out


def spf_lookups(record, depth=0, seen=None):
    """Count DNS-querying SPF terms (RFC 7208 limit: 10), following include/redirect."""
    seen = seen if seen is not None else set()
    if depth > 10:
        return 0
    count = 0
    for term in record.split()[1:]:
        t = term.lstrip('+-~?').lower()
        if t.startswith(('include:', 'redirect=')):
            count += 1
            target = t.split(':', 1)[1] if t.startswith('include:') else t.split('=', 1)[1]
            if target in seen:
                continue
            seen.add(target)
            try:
                _, recs = txt_records(target)
            except RuntimeError:
                continue
            for r in recs:
                if r.lower().startswith('v=spf1'):
                    count += spf_lookups(r, depth + 1, seen)
        elif t.startswith(('a', 'mx', 'ptr', 'exists:')) and not t.startswith('all'):
            count += 1
    return count


def domain_age_days(domain):
    try:
        req = urllib.request.Request(f'https://rdap.org/domain/{domain}', headers={'user-agent': UA,
                                                                                  'accept': 'application/rdap+json'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
    except Exception:
        return None
    for ev in data.get('events', []):
        if ev.get('eventAction') == 'registration':
            try:
                created = datetime.fromisoformat(ev['eventDate'].replace('Z', '+00:00'))
                return (datetime.now(timezone.utc) - created).days
            except (KeyError, ValueError):
                return None
    return None


def spamhaus_dbl(domain):
    """'listed', 'not listed' or 'unknown' (the resolver was refused or failed)."""
    try:
        ip = socket.gethostbyname(f'{domain}.dbl.spamhaus.org')
    except socket.gaierror:
        return 'not listed'
    except Exception:
        return 'unknown'
    if ip.startswith('127.0.1.'):
        return 'listed'
    return 'unknown'  # 127.255.255.x: query refused (public or open resolver)


def check(domain, selectors):
    domain = domain.strip().lower().removeprefix('http://').removeprefix('https://').split('/')[0]
    domain = domain.removeprefix('www.')
    checks = []

    def add(key, label, points, got, status, detail):
        checks.append({'check': key, 'label': label, 'max': points, 'points': got, 'status': status,
                       'detail': detail})

    # MX: without it replies bounce
    _, mx = doh(domain, 'MX')
    if mx and all(m.split()[-1] == '.' for m in mx):
        add('mx', 'MX records', 10, 0, 'fail', 'Null MX (RFC 7505): this domain accepts no mail, so replies bounce.')
    else:
        add('mx', 'MX records', 10, 10 if mx else 0, 'pass' if mx else 'fail',
            ', '.join(sorted(mx)) if mx else 'No MX record: replies to this domain cannot be delivered.')

    # SPF
    _, txts = txt_records(domain)
    spf = [t for t in txts if t.lower().startswith('v=spf1')]
    if len(spf) == 1:
        add('spf', 'SPF record', 15, 15, 'pass', spf[0])
        rec = spf[0].lower()
        redirect = next((t.split('=', 1)[1] for t in rec.split() if t.startswith('redirect=')), None)
        if redirect and not rec.rstrip().endswith('all'):
            try:
                target = [r.lower() for r in txt_records(redirect)[1] if r.lower().startswith('v=spf1')]
            except RuntimeError:
                target = []
            if target:
                rec = target[0]
        if rec.rstrip().endswith(('-all', '~all')):
            add('spf_all', 'SPF ends with ~all or -all', 5, 5, 'pass', rec.split()[-1])
        elif '+all' in rec.split():
            add('spf_all', 'SPF ends with ~all or -all', 5, 0, 'fail', '+all lets anyone send as this domain.')
        else:
            add('spf_all', 'SPF ends with ~all or -all', 5, 2, 'warn', 'No ~all or -all at the end of the record.')
        n = spf_lookups(spf[0])
        add('spf_lookups', 'SPF DNS lookups (limit 10)', 5, 5 if n <= 10 else 0, 'pass' if n <= 10 else 'fail',
            f'{n} lookups' + ('' if n <= 10 else ': over the limit, receivers treat SPF as a permanent error.'))
    elif len(spf) > 1:
        add('spf', 'SPF record', 15, 0, 'fail', f'{len(spf)} SPF records: there must be exactly one.')
    else:
        add('spf', 'SPF record', 15, 0, 'fail', 'No SPF record.')

    # DMARC
    _, dm = txt_records(f'_dmarc.{domain}')
    dmarc = [t for t in dm if t.lower().startswith('v=dmarc1')]
    if dmarc:
        rec = dmarc[0]
        tags = {k.strip().lower(): v.strip() for k, _, v in (p.partition('=') for p in rec.split(';')) if k.strip()}
        add('dmarc', 'DMARC record', 15, 15, 'pass', rec)
        p = tags.get('p', '').lower()
        if p in ('quarantine', 'reject'):
            add('dmarc_policy', 'DMARC policy', 5, 5, 'pass', f'p={p}')
        else:
            add('dmarc_policy', 'DMARC policy', 5, 2, 'warn',
                f'p={p or "missing"}: monitoring only. Move to quarantine once reports look clean.')
        add('dmarc_rua', 'DMARC reports (rua)', 5, 5 if tags.get('rua') else 0, 'pass' if tags.get('rua') else 'warn',
            tags.get('rua') or 'No rua address: you receive no aggregate reports.')
    else:
        add('dmarc', 'DMARC record', 15, 0, 'fail', 'No DMARC record at _dmarc.' + domain)

    # DKIM on the given or common selectors
    found = []
    for sel in selectors:
        try:
            _, recs = txt_records(f'{sel}._domainkey.{domain}')
        except RuntimeError:
            continue
        for r in recs:
            tags = {k.strip().lower(): v.strip() for k, _, v in (x.partition('=') for x in r.split(';')) if k.strip()}
            if tags.get('p') and (tags.get('v', 'DKIM1').upper() == 'DKIM1'):
                found.append(sel)
                break
        if len(found) >= 3:
            break
    if found:
        add('dkim', 'DKIM key', 20, 20, 'pass', 'Selector(s): ' + ', '.join(found))
    else:
        add('dkim', 'DKIM key', 20, 0, 'warn',
            'No DKIM key on common selectors. If you use a custom selector, run again with --selector NAME.')

    # Domain age
    age = domain_age_days(domain)
    if age is None:
        add('age', 'Domain age', 10, None, 'unknown', 'Registration date not available from RDAP.')
    elif age < 30:
        add('age', 'Domain age', 10, 3, 'warn', f'{age} days old: very new domains get less trust from inbox providers.')
    else:
        add('age', 'Domain age', 10, 10, 'pass', f'{age} days old')

    # Website: an A record (a site or a redirect) makes the domain look like a real business
    _, a = doh(domain, 'A')
    add('web', 'Website or redirect (A record)', 5, 5 if a else 0, 'pass' if a else 'warn',
        ', '.join(a[:3]) if a else 'No A record: the domain has no website or redirect.')

    # Spamhaus DBL
    dbl = spamhaus_dbl(domain)
    add('dbl', 'Spamhaus DBL', 15, {'listed': 0, 'not listed': 15}.get(dbl), {'listed': 'fail', 'not listed': 'pass'}.get(dbl, 'unknown'),
        {'listed': 'Listed on the Spamhaus Domain Block List.', 'not listed': 'Not listed.'}.get(
            dbl, 'Could not query Spamhaus from this network (public resolvers are refused). Check at spamhaus.org.'))

    scored = [c for c in checks if c['points'] is not None]
    total = sum(c['points'] for c in scored)
    possible = sum(c['max'] for c in scored)
    score = round(100 * total / possible) if possible else 0
    return {'domain': domain, 'score': score, 'checks': checks,
            'not_scored': [c['check'] for c in checks if c['points'] is None]}


def main():
    ap = argparse.ArgumentParser(description='Cold email domain health check')
    ap.add_argument('domains', nargs='+')
    ap.add_argument('--selector', action='append', default=[], help='DKIM selector to test (repeatable)')
    ap.add_argument('--json', action='store_true', help='print JSON only')
    args = ap.parse_args()
    selectors = args.selector + [s for s in COMMON_SELECTORS if s not in args.selector]
    results = []
    for d in args.domains:
        try:
            results.append(check(d, selectors))
        except RuntimeError as e:
            results.append({'domain': d, 'error': str(e)})
    if args.json:
        print(json.dumps(results, indent=2))
        return
    for r in results:
        if 'error' in r:
            print(f"\n{r['domain']}: {r['error']}")
            continue
        print(f"\n{r['domain']}  score {r['score']}/100")
        for c in r['checks']:
            pts = '  -' if c['points'] is None else f"{c['points']:>3}"
            print(f"  [{c['status']:^8}] {pts}/{c['max']:<3} {c['label']}: {c['detail']}")
    print('\nChecked by the Growth Cab domain check. Sending setup and management: '
          'https://www.growthcab.com/email-deliverability-consultant')


if __name__ == '__main__':
    sys.exit(main())
