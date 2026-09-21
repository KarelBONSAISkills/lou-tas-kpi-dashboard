# Logi-Technic — Lou KPI dashboard

Static management report for Ringtime (Lou) vs TAS on website pool vacancies.

Karel hands this repo to Laurens / Claude to refresh numbers, restyle, and reconnect Salesforce.

## What this is

- `index.html` + CSS = the report (GitHub Pages).
- Numbers are **aggregates only**. No candidate names, emails, or Salesforce Ids in the HTML.
- Source of truth for **definitions** is this file + `METHODOLOGY.md`.
- Source of truth for **data** is Salesforce **Production** Logi-Technic (read-only).

Public page: https://karelbonsaiskills.github.io/lou-tas-kpi-dashboard/

## Salesforce connection

Karel currently refreshes via Salesforce CLI:

```text
Org alias:   Logi-Technic - Production
Type:        Production (not a sandbox)
Instance:    https://logitechnic.my.salesforce.com
Username:    karel+logitechnic@bonsaiskills.com  (Karel only)
```

Laurens will likely **not** have Karel’s CLI session. Use one of:

1. **Salesforce CLI** (same as Karel): `sf org login web --alias "Logi-Technic - Production"` with a Logi-Technic user that has API + object access.
2. **Claude Salesforce connector / MCP** pointed at **this** org (`logitechnic.my.salesforce.com`), not the Bonsai Skills org. Karel’s Cursor MCP only allowlists Bonsai; Logi-Technic queries go through `sf`.

Never deploy metadata or write records. This project is **read-only**.

## Refresh

```bash
python3 scripts/refresh_kpis.py
```

Writes `data/latest.json`. Then update the hardcoded totals in `index.html` / pie slices in `dashboard.css`. Bump `?v=YYYYMMDD` on the CSS links so Pages is not stuck on cache.

## Two comparison groups (tabs 1 and 4)

Universe: `Created From = Form` + PVLT workflow `a167R00000WP9gAQAT` + job application created in 2026.

| Group | Rule |
|---|---|
| Met afronding | ≥ 1 `Ringtime_Task__c` with `Status__c = Completed` |
| Zonder afronding | never a Completed Ringtime task (Failed-only stays here) |

Funnel = **ever reached** a stage (current status **or** lead-time previous/current status). Last step **Aangeworven only** (not Positive / Job Offer).

**Niet te bereiken:** % of “met afronding” with Completed + `Outcome__c = none` vs % of “zonder afronding” with Afwijzen step `Rejection_reason__c = Unreachable`.

## Never

- Put secrets, session tokens, or candidate PII in git.
- Deploy to Salesforce without the Logi-Technic owner’s explicit approval.
- Empty permission sets.
