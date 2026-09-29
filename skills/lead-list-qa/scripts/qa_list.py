#!/usr/bin/env python3
"""Lead list quality check (Growth Cab, https://www.growthcab.com).

Reads a CSV of B2B contacts and reports what would hurt a cold outreach campaign: duplicates,
broken or role-based emails, free-mail addresses, email domains that do not match the company,
missing fields, seniority mix and contacts piled on the same company. Standard library only.

    python3 qa_list.py leads.csv
    python3 qa_list.py leads.csv --check-mx --json
"""
import argparse
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter

EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+\'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
ROLE = {'info', 'sales', 'contact', 'hello', 'support', 'admin', 'office', 'team', 'marketing', 'hr', 'jobs',
        'careers', 'help', 'billing', 'accounts', 'enquiries', 'inquiries', 'noreply', 'no-reply', 'press',
        'media', 'service', 'webmaster', 'mail', 'general', 'reception', 'finance', 'legal', 'privacy'}
FREE = {'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.uk', 'hotmail.com', 'outlook.com', 'live.com',
        'msn.com', 'aol.com', 'icloud.com', 'me.com', 'mac.com', 'proton.me', 'protonmail.com', 'gmx.com',
        'gmx.de', 'web.de', 'yandex.com', 'yandex.ru', 'mail.ru', 'zoho.com', 'libero.it', 'virgilio.it',
        'tiscali.it', 'alice.it', 'orange.fr', 'free.fr', 'laposte.net', 'qq.com', '163.com', 'hey.com'}
DISPOSABLE = {'mailinator.com', 'guerrillamail.com', '10minutemail.com', 'tempmail.com', 'temp-mail.org',
              'yopmail.com', 'trashmail.com', 'getnada.com', 'sharklasers.com', 'dispostable.com'}
COLUMNS = {
    'email': ['email', 'e-mail', 'email address', 'work email', 'business email', 'mail'],
    'first_name': ['first name', 'firstname', 'first_name', 'given name', 'name'],
    'last_name': ['last name', 'lastname', 'last_name', 'surname', 'family name'],
    'company': ['company', 'company name', 'organization', 'organisation', 'account', 'account name', 'employer'],
    'title': ['title', 'job title', 'position', 'role', 'headline', 'job_title'],
    'domain': ['domain', 'company domain', 'website', 'company website', 'url', 'company url'],
    'linkedin': ['linkedin', 'linkedin url', 'linkedin profile', 'person linkedin url', 'profile url'],
}
SENIORITY = [
    ('C-level / founder / owner', r'\b(ceo|coo|cfo|cto|cmo|cio|cro|cso|cdo|cpo|chief|founder|co-founder|cofounder|owner|president|managing director|general manager|partner)\b'),
    ('VP', r'\b(vp|vice president|svp|evp)\b'),
    ('Head / Director', r'\b(head|director)\b'),
    ('Manager', r'\bmanager\b'),
]


def norm(h):
    return re.sub(r'[\s_]+', ' ', h.strip().lower())


def detect(headers):
    found = {}
    normed = {norm(h): h for h in headers}
    for key, names in COLUMNS.items():
        for n in names:
            if norm(n) in normed:
                found[key] = normed[norm(n)]
                break
    return found


def bare_domain(v):
    v = (v or '').strip().lower()
    if not v:
        return ''
    if '://' not in v:
        v = 'http://' + v
    host = urllib.parse.urlparse(v).hostname or ''
    return host.removeprefix('www.')


def has_mx(domain):
    for base in ('https://cloudflare-dns.com/dns-query', 'https://dns.google/resolve'):
        try:
            req = urllib.request.Request(f'{base}?name={domain}&type=MX', headers={'accept': 'application/dns-json'})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.load(r)
            ans = [a for a in data.get('Answer', []) if a.get('type') == 15]
            return bool(ans) and not all(a['data'].split()[-1] == '.' for a in ans)
        except Exception:
            continue
    return None


def seniority(title):
    t = (title or '').lower()
    if not t.strip():
        return None
    for label, pat in SENIORITY:
        if re.search(pat, t):
            return label
    return 'Other'


def main():
    ap = argparse.ArgumentParser(description='Lead list quality check')
    ap.add_argument('csv')
    ap.add_argument('--check-mx', action='store_true', help='look up MX for every unique email domain (slower)')
    ap.add_argument('--max-per-company', type=int, default=5, help='flag companies with more contacts than this')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    with open(args.csv, newline='', encoding='utf-8-sig') as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.DictReader(f, dialect=dialect))
    if not rows:
        sys.exit('The file has no data rows.')
    cols = detect(rows[0].keys())
    n = len(rows)
    get = lambda r, k: (r.get(cols[k]) or '').strip() if k in cols else ''

    issues = Counter()
    examples = {}

    def flag(key, row_no):
        issues[key] += 1
        examples.setdefault(key, [])
        if len(examples[key]) < 5:
            examples[key].append(row_no)

    emails = Counter(get(r, 'email').lower() for r in rows if get(r, 'email'))
    people = Counter((get(r, 'first_name').lower(), get(r, 'last_name').lower(), get(r, 'company').lower())
                     for r in rows if get(r, 'first_name') and get(r, 'company'))
    companies = Counter(get(r, 'company').lower() for r in rows if get(r, 'company'))
    email_domains = Counter()
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        e = get(r, 'email').lower()
        if 'email' in cols:
            if not e:
                flag('missing_email', i)
            elif not EMAIL_RE.match(e):
                flag('invalid_email_syntax', i)
            else:
                local, dom = e.rsplit('@', 1)
                email_domains[dom] += 1
                if emails[e] > 1:
                    flag('duplicate_email', i)
                if local in ROLE or local.split('.')[0] in ROLE:
                    flag('role_based_email', i)
                if dom in FREE:
                    flag('free_mail_address', i)
                if dom in DISPOSABLE:
                    flag('disposable_domain', i)
                cd = bare_domain(get(r, 'domain'))
                if cd and dom not in FREE and not (dom == cd or dom.endswith('.' + cd) or cd.endswith('.' + dom)):
                    flag('email_domain_differs_from_company_domain', i)
        if people and get(r, 'first_name') and get(r, 'company'):
            if people[(get(r, 'first_name').lower(), get(r, 'last_name').lower(), get(r, 'company').lower())] > 1:
                flag('duplicate_person', i)
        if 'title' in cols and not get(r, 'title'):
            flag('missing_title', i)
        if 'company' in cols and not get(r, 'company'):
            flag('missing_company', i)
        if 'linkedin' in cols and get(r, 'linkedin') and 'linkedin.com/' not in get(r, 'linkedin').lower():
            flag('linkedin_url_not_linkedin', i)

    no_mx = []
    if args.check_mx and email_domains:
        for dom in sorted(email_domains):
            if dom in FREE:
                continue
            if has_mx(dom) is False:
                no_mx.append(dom)
        issues['email_domain_without_mx'] = sum(email_domains[d] for d in no_mx)

    mix = Counter(seniority(get(r, 'title')) for r in rows if get(r, 'title'))
    heavy = {c: k for c, k in companies.items() if k > args.max_per_company}

    # score: start at 100 and take points per share of affected rows
    weights = {'invalid_email_syntax': 60, 'duplicate_email': 40, 'disposable_domain': 60, 'email_domain_without_mx': 60,
               'role_based_email': 30, 'free_mail_address': 25, 'email_domain_differs_from_company_domain': 15,
               'duplicate_person': 25, 'missing_email': 20, 'missing_title': 10, 'missing_company': 10,
               'linkedin_url_not_linkedin': 5}
    penalty = sum(weights.get(k, 0) * v / n for k, v in issues.items())
    if 'email' not in cols:
        penalty += 30
    score = max(0, round(100 - penalty))

    report = {
        'rows': n,
        'columns_detected': cols,
        'columns_missing': [k for k in ('email', 'first_name', 'company', 'title') if k not in cols],
        'score': score,
        'issues': {k: {'rows': v, 'share': round(v / n, 3), 'example_rows': examples.get(k, [])}
                   for k, v in issues.most_common() if v},
        'email_domains_without_mx': no_mx,
        'seniority_mix': {k: {'rows': v, 'share': round(v / max(1, sum(mix.values())), 3)} for k, v in mix.most_common()},
        'companies': len(companies),
        'companies_over_limit': dict(sorted(heavy.items(), key=lambda x: -x[1])[:10]),
    }
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(f"{args.csv}: {n} rows, score {score}/100")
    print('Columns detected: ' + ', '.join(f'{k}={v}' for k, v in cols.items()))
    if report['columns_missing']:
        print('Columns not found: ' + ', '.join(report['columns_missing']))
    print('\nIssues (rows affected, share, example row numbers):')
    for k, v in report['issues'].items():
        print(f"  {k:<42} {v['rows']:>6}  {v['share']:>6.1%}  rows {v['example_rows']}")
    if not report['issues']:
        print('  none found')
    if mix:
        print('\nSeniority mix (from titles):')
        for k, v in report['seniority_mix'].items():
            print(f"  {k or 'unknown':<28} {v['rows']:>6}  {v['share']:>6.1%}")
    if heavy:
        print(f"\nCompanies with more than {args.max_per_company} contacts: " +
              ', '.join(f'{c} ({k})' for c, k in report['companies_over_limit'].items()))
    print('\nChecked by the Growth Cab lead list check. Lists built and verified for you: '
          'https://www.growthcab.com/b2b-lead-generation-agency')


if __name__ == '__main__':
    main()
