#!/usr/bin/env python3
"""Mechanical checks for a cold email (Growth Cab, https://www.growthcab.com).

Counts the things a script can count reliably: length, links, merge tags, trigger words,
capitals, exclamation marks, reader focus and readability. The judgment checks live in SKILL.md.

    python3 mechanical_checks.py email.txt
    pbpaste | python3 mechanical_checks.py -

A first line starting with "Subject:" is read as the subject line.
"""
import json
import re
import sys

TRIGGERS = [
    'act now', 'amazing', 'apply now', 'as seen on', 'buy now', 'cash', 'click here', 'congratulations',
    'dear friend', 'discount', 'double your', 'earn', 'exclusive deal', 'free', 'guarantee', 'guaranteed',
    'increase sales', 'limited time', 'lowest price', 'make money', 'miracle', 'no cost', 'no obligation',
    'offer expires', 'once in a lifetime', 'order now', 'promise', 'risk-free', 'risk free', 'special promotion',
    'this is not spam', 'urgent', 'winner', '100%', '$$$', 'best price', 'cheap', 'instant', 'unsubscribe',
]
MERGE = re.compile(r'\{\{[^}]*\}\}|\{[A-Za-z_ ]+\}|\[(?:first ?name|company|name|firstname)[^\]]*\]|%[A-Z_]+%', re.I)
LINK = re.compile(r'https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:com|io|ai|co|net|org|app)(?:/\S*)?\b', re.I)


def syllables(word):
    w = re.sub(r'[^a-z]', '', word.lower())
    if not w:
        return 0
    groups = re.findall(r'[aeiouy]+', w)
    n = len(groups)
    if w.endswith('e') and n > 1 and not w.endswith(('le', 'ee')):
        n -= 1
    return max(1, n)


def analyze(text):
    lines = text.strip().splitlines()
    subject = ''
    if lines and lines[0].lower().startswith('subject:'):
        subject = lines[0].split(':', 1)[1].strip()
        lines = lines[1:]
    body = '\n'.join(lines).strip()
    words = re.findall(r"[A-Za-z0-9'’$%]+", body)
    sentences = [s for s in re.split(r'(?<=[.!?])\s+|\n{2,}', body) if re.search(r'[A-Za-z]', s)]
    low = body.lower()
    you = len(re.findall(r"\b(you|your|yours|you're|you’ve|you've)\b", low))
    we = len(re.findall(r"\b(i|we|our|us|my|i'm|we're|i’m|we’re)\b", low))
    syl = sum(syllables(w) for w in words)
    n_w, n_s = max(1, len(words)), max(1, len(sentences))
    flesch = round(206.835 - 1.015 * (n_w / n_s) - 84.6 * (syl / n_w), 1)
    caps = [w for w in re.findall(r'\b[A-Z]{4,}\b', body) if w not in ('B2B', 'SaaS', 'CEO', 'CFO', 'CTO', 'CRO', 'CMO', 'COO')]
    found_triggers = sorted({t for t in TRIGGERS if re.search(r'(?<![a-z])' + re.escape(t) + r'(?![a-z])', low + ' ' + subject.lower())})
    return {
        'subject': subject,
        'subject_words': len(subject.split()) if subject else 0,
        'body_words': len(words),
        'sentences': len(sentences),
        'avg_sentence_words': round(len(words) / n_s, 1),
        'longest_sentence_words': max((len(re.findall(r"[A-Za-z0-9'’$%]+", s)) for s in sentences), default=0),
        'links': LINK.findall(body),
        'unresolved_merge_tags': MERGE.findall(subject + '\n' + body),
        'trigger_words': found_triggers,
        'all_caps_words': caps,
        'exclamation_marks': body.count('!') + subject.count('!'),
        'questions': body.count('?'),
        'you_words': you,
        'i_we_words': we,
        'flesch_reading_ease': flesch,
        'mentions_attachment_or_image': bool(re.search(r'\b(attached|attachment|see the image|screenshot below|pdf)\b', low)),
        'fake_reply_or_forward_subject': bool(re.match(r'^(re|fw|fwd):', subject.strip(), re.I)),
    }


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else '-'
    text = sys.stdin.read() if src == '-' else open(src, encoding='utf-8').read()
    print(json.dumps(analyze(text), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
