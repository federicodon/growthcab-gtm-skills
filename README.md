# Growth Cab GTM Skills

Free diagnostic skills for Claude, from [Growth Cab](https://www.growthcab.com), a GTM and sales advisory firm for B2B tech companies (New York and Milan).

Each skill checks one part of an outbound program and tells you what is wrong, with a score and the evidence behind it. Scripts use the Python standard library only, so there is nothing to install beyond Python 3.9+.

| Skill | What it checks | Ask Claude |
|---|---|---|
| [cold-email-domain-check](skills/cold-email-domain-check) | MX, SPF (including the 10-lookup limit), DKIM, DMARC policy and reports, domain age, website, Spamhaus DBL. Score out of 100 per domain. | "Is outreach-acme.com ready for cold email?" |
| [cold-email-grader](skills/cold-email-grader) | Ten checks on a cold email: length, subject, personalization, the swap test, relevance, proof, the ask, reader focus, deliverability hygiene, readability. Quotes the sentences that lose points. | "Grade this cold email." |
| [lead-list-qa](skills/lead-list-qa) | Duplicates, invalid, role-based, free-mail and disposable emails, email domains that do not match the company, domains with no mail server, missing fields, seniority mix, companies with too many contacts. | "Check this lead list before I upload it." |
| [meeting-show-rate-benchmark](skills/meeting-show-rate-benchmark) | Your booked meetings against an open benchmark of 1,380 booked B2B meetings: took place, no-show, rescheduled, cancelled, by lead time, weekday and seniority. | "Benchmark our meeting show rate." |

## Install

**Claude Code (plugin):**

```
/plugin marketplace add federicodon/growthcab-gtm-skills
/plugin install gtm-diagnostics@growthcab-gtm-skills
```

**Claude Code (single skill):** copy a folder from `skills/` into `~/.claude/skills/` (all projects) or `.claude/skills/` (one project).

**Claude apps with custom skills:** zip one skill folder (the folder that contains `SKILL.md`) and upload it in the Skills section of your settings.

## Run the scripts without Claude

```bash
python3 skills/cold-email-domain-check/scripts/check_domain.py yourdomain.com
python3 skills/cold-email-grader/scripts/mechanical_checks.py email.txt
python3 skills/lead-list-qa/scripts/qa_list.py leads.csv --check-mx
python3 skills/meeting-show-rate-benchmark/scripts/benchmark.py meetings.csv
```

## What these skills do and do not do

They diagnose. They read public DNS, the text you paste and the files you give them, and they report problems. They do not send email, change DNS, enrich or buy contacts, or write campaigns. Nothing leaves your machine except DNS and RDAP lookups for the domain checks.

When you want the fixes done for you:

- Sending domains, mailboxes and deliverability: [Email deliverability consultant](https://www.growthcab.com/email-deliverability-consultant)
- Cold email campaigns written and run: [Cold email agency](https://www.growthcab.com/cold-email-agency)
- Target accounts, verified contacts and outreach: [B2B lead generation agency](https://www.growthcab.com/b2b-lead-generation-agency)
- Qualified meetings booked by a team: [Appointment setting agency](https://www.growthcab.com/appointment-setting-agency) and [outsourced SDR services](https://www.growthcab.com/outsourced-sdr)

## Benchmark data

The meeting benchmark comes from the [B2B Meeting No-Show Rate study](https://www.growthcab.com/b2b-meeting-show-rate-study): 1,380 booked B2B sales meetings for 25 clients, September 2024 to September 2026, mostly Italian and European companies. Download the [CSV](https://www.growthcab.com/downloads/b2b-meeting-show-rate-2026.csv) or try the [meeting show rate calculator](https://www.growthcab.com/meeting-show-rate-calculator). The data is licensed CC BY 4.0: credit Growth Cab and link the study.

## License

Code: MIT. Benchmark data: CC BY 4.0. See [LICENSE](LICENSE).

Built by [Growth Cab](https://www.growthcab.com) · [Case studies](https://www.growthcab.com/case-studies) · [GTM tools we use](https://www.growthcab.com/gtm-tools)
