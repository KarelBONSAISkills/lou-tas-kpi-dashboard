#!/usr/bin/env python3
"""Refresh Lou KPI numbers from Logi-Technic Production (read-only)."""
import json, subprocess, statistics, collections, time
from datetime import datetime, timezone, timedelta

ORG = "Logi-Technic - Production"
WF = "a167R00000WP9gAQAT"
HIRED = "6.0 Aangeworven (PVLT)"
LIVE = "2026-08-10T00:00:00Z"

SYSTEM = {
    "005Td00000E4rgnIAB",  # Lou
    "005Td00000E4rthIAB",  # Ringtime Integration
    "005Td00000E7bu1IAB",  # Integration deprecated
    "0057R00000DqggNQAR",  # Automated Process
    "0057R00000DqggbQAB",  # Guest
    "005Td000002TTOrIAO",  # Consent guest
    "0057R00000EI2wZQAT",  # Boomi
}


def q(soql, attempts=8):
    last = None
    for i in range(attempts):
        r = subprocess.run(
            ["sf", "data", "query", "--target-org", ORG, "--json", "--query", soql],
            capture_output=True, text=True,
        )
        raw = (r.stdout or r.stderr or "").strip()
        try:
            data = json.loads(raw[raw.find("{"):])
        except Exception:
            last = raw[:800]
            time.sleep(6 * (i + 1))
            continue
        if data.get("status") == 0:
            recs = data["result"]["records"]
            if not data["result"].get("done", True):
                raise SystemExit(f"truncated {len(recs)} / {data['result'].get('totalSize')} :: {soql[:140]}")
            return [{k: v for k, v in rec.items() if k != "attributes"} for rec in recs]
        msg = str(data.get("message") or "")
        if "maintenance" in msg.lower() or data.get("name") == "ERROR_HTTP_503":
            print(f"  503 retry {i+1}", flush=True)
            last = msg[:200]
            time.sleep(12 * (i + 1))
            continue
        raise SystemExit(json.dumps(data, indent=2)[:2500])
    raise SystemExit(last or "503")


def batches(xs, n=80):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso_week_label(dt):
    y, w, _ = dt.isocalendar()
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return w, f"W{w} · {monday.day} {'' if monday.month == sunday.month else ''}{monday.strftime('%-d')}–{sunday.strftime('%-d %b')}".replace("  ", " ")


def fmt_range(monday, sunday):
    months_nl = {8: "aug", 9: "sep", 10: "okt"}
    if monday.month == sunday.month:
        return f"{monday.day}–{sunday.day} {months_nl[monday.month]}"
    return f"{monday.day} {months_nl[monday.month]}–{sunday.day} {months_nl[sunday.month]}"


def status_name(rec):
    return (rec.get("cxsrec__Workflow_status__r") or {}).get("Name")


def rank(status):
    s = status or ""
    if "Aangeworven" in s:
        return 4
    if "Screening TS" in s or "Intake TS" in s:
        return 3
    if "Screening TAS" in s or "Intake TAS" in s:
        return 2
    if "Prescreening" in s:
        return 1
    return 0


def channel(key):
    k = (key or "").lower()
    if k.startswith("wa") or "whatsapp" in k:
        return "wa"
    if "voice" in k:
        return "voice"
    return "other"


def bucket_task(t):
    st = t.get("Status__c") or ""
    oc = (t.get("Outcome__c") or "").strip()
    if st == "Failed":
        return "Failed"
    if st == "Cancelled":
        return "Cancelled"
    if st == "Active":
        return "Active"
    if oc == "Duplicate" or st == "Duplicate":
        return "Duplicate"
    if oc == "screened":
        return "screened"
    if oc == "none":
        return "none"
    if oc:
        return oc
    return st or "other"


print("=== tasks ===", flush=True)
tasks = q(
    "SELECT Id, CreatedDate, Completed_At__c, Status__c, Outcome__c, Campaign_Key__c, "
    "Ringtime_Task_Id__c, Job_Application__c "
    "FROM Ringtime_Task__c"
)
print("tasks", len(tasks), flush=True)

n_rtid = sum(1 for t in tasks if t.get("Ringtime_Task_Id__c"))
n_wa = sum(1 for t in tasks if channel(t.get("Campaign_Key__c")) == "wa")
n_voice = sum(1 for t in tasks if channel(t.get("Campaign_Key__c")) == "voice")
n_active = sum(1 for t in tasks if t.get("Status__c") == "Active")
if tasks:
    first = min(parse_dt(t["CreatedDate"]) for t in tasks)
    last = max(parse_dt(t["CreatedDate"]) for t in tasks)
else:
    first = last = None

weeks = collections.defaultdict(lambda: {"wa": 0, "voice": 0, "other": 0})
for t in tasks:
    dt = parse_dt(t["CreatedDate"])
    if not dt:
        continue
    y, w, _ = dt.isocalendar()
    monday = (dt - timedelta(days=dt.weekday())).date()
    sunday = monday + timedelta(days=6)
    weeks[(y, w, monday, sunday)][channel(t.get("Campaign_Key__c"))] += 1

week_rows = []
for (y, w, monday, sunday), counts in sorted(weeks.items()):
    tot = counts["wa"] + counts["voice"] + counts["other"]
    week_rows.append({
        "week": w,
        "label": f"W{w} · {fmt_range(monday, sunday)}",
        "wa": counts["wa"],
        "voice": counts["voice"],
        "total": tot,
    })

task_buckets = collections.Counter(bucket_task(t) for t in tasks)
wa_buckets = collections.Counter(bucket_task(t) for t in tasks if channel(t.get("Campaign_Key__c")) == "wa")
voice_buckets = collections.Counter(bucket_task(t) for t in tasks if channel(t.get("Campaign_Key__c")) == "voice")

def pie3(counter):
    talk = counter.get("screened", 0)
    none = counter.get("none", 0)
    rest = sum(counter.values()) - talk - none
    n = talk + none + rest
    return {"n": n, "talk": talk, "none": none, "rest": rest}

JA_FIELDS = (
    "SELECT Id, CreatedDate, cxsrec__Process_time__c, "
    "cxsrec__Workflow_status__r.Name, cxsrec__Workflow_status__r.cxsrec__Active__c "
    "FROM cxsrec__cxsJob_application__c "
    "WHERE cxsrec__Created_from__c = 'Form' "
    f"AND cxsrec__Workflow_status__r.cxsrec__Workflow__c = '{WF}' "
    "AND CreatedDate >= 2026-01-01T00:00:00Z "
)

print("=== with completed JAs ===", flush=True)
with_jas = q(JA_FIELDS + "AND Id IN (SELECT Job_Application__c FROM Ringtime_Task__c WHERE Status__c = 'Completed')")
print("with", len(with_jas), flush=True)
time.sleep(1)

without_jas = []
for a, b in [
    ("2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z"),
    ("2026-04-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    ("2026-07-01T00:00:00Z", "2026-10-01T00:00:00Z"),
]:
    chunk = q(
        JA_FIELDS + f"AND CreatedDate >= {a} AND CreatedDate < {b} "
        "AND Id NOT IN (SELECT Job_Application__c FROM Ringtime_Task__c WHERE Status__c = 'Completed')"
    )
    print("without", a[:7], len(chunk), flush=True)
    without_jas += chunk
    time.sleep(1)

print("=== lead times with ===", flush=True)
lt_with = q(
    "SELECT Job_application__c, Current_Status__c, Previous_Status__c FROM Lead_Time__c WHERE "
    "Job_application__r.cxsrec__Created_from__c = 'Form' "
    f"AND Job_application__r.cxsrec__Workflow_status__r.cxsrec__Workflow__c = '{WF}' "
    "AND Job_application__r.CreatedDate >= 2026-01-01T00:00:00Z "
    "AND Job_application__c IN (SELECT Job_Application__c FROM Ringtime_Task__c WHERE Status__c = 'Completed')"
)
print("lt with", len(lt_with), flush=True)
time.sleep(1)

lt_without = []
month_ranges = [
    ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"),
    ("2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z"),
    ("2026-03-01T00:00:00Z", "2026-04-01T00:00:00Z"),
    ("2026-04-01T00:00:00Z", "2026-05-01T00:00:00Z"),
    ("2026-05-01T00:00:00Z", "2026-06-01T00:00:00Z"),
    ("2026-06-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    ("2026-07-01T00:00:00Z", "2026-08-01T00:00:00Z"),
    ("2026-08-01T00:00:00Z", "2026-09-01T00:00:00Z"),
    ("2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z"),
]
for a, b in month_ranges:
    chunk = q(
        "SELECT Job_application__c, Current_Status__c, Previous_Status__c FROM Lead_Time__c WHERE "
        "Job_application__r.cxsrec__Created_from__c = 'Form' "
        f"AND Job_application__r.cxsrec__Workflow_status__r.cxsrec__Workflow__c = '{WF}' "
        f"AND Job_application__r.CreatedDate >= {a} AND Job_application__r.CreatedDate < {b} "
        "AND Job_application__c NOT IN (SELECT Job_Application__c FROM Ringtime_Task__c WHERE Status__c = 'Completed')"
    )
    print("lt without", a[:7], len(chunk), flush=True)
    lt_without += chunk
    time.sleep(1)


def lt_ranks(rows):
    by = collections.defaultdict(int)
    ids = set()
    for r in rows:
        jid = r.get("Job_application__c")
        if not jid:
            continue
        ids.add(jid)
        by[jid] = max(by[jid], rank(r.get("Current_Status__c")), rank(r.get("Previous_Status__c")))
    return by, ids


def process_stats(rows):
    days = [r.get("cxsrec__Process_time__c") for r in rows if r.get("cxsrec__Process_time__c") is not None]
    return {
        "n": len(rows),
        "avg": round(statistics.mean(days), 1) if days else None,
        "min": min(days) if days else None,
        "max": max(days) if days else None,
        "open": sum(1 for r in rows if (r.get("cxsrec__Workflow_status__r") or {}).get("cxsrec__Active__c")),
        "hired": sum(1 for r in rows if status_name(r) == HIRED),
    }


def end_status(rows):
    groups = collections.defaultdict(list)
    for r in rows:
        st = status_name(r) or ""
        days = r.get("cxsrec__Process_time__c")
        if days is None:
            continue
        if "Afgewezen na Nieuw" in st:
            key = "Afgewezen na Nieuw"
        elif "Afgewezen na Prescreening" in st:
            key = "Afgewezen na Prescreening"
        elif "Afgewezen na Screening TAS" in st:
            key = "Afgewezen na Screening TAS"
        elif "Afgewezen na Screening TS" in st:
            key = "Afgewezen na Screening TS"
        elif "teruggetrokken" in st.lower():
            key = "Teruggetrokken"
        elif "Aangeworven" in st:
            key = "Aangeworven"
        else:
            continue
        groups[key].append(days)
    return {k: round(statistics.mean(v), 1) for k, v in groups.items()}


def funnel(rows, lt_rank):
    n = len(rows)
    counts = [n, 0, 0, 0, 0]
    for r in rows:
        rr = max(rank(status_name(r)), lt_rank.get(r["Id"], 0))
        if rr >= 1:
            counts[1] += 1
        if rr >= 2:
            counts[2] += 1
        if rr >= 3:
            counts[3] += 1
        if status_name(r) == HIRED:
            counts[4] += 1
    pct = [round(100 * c / n) if n else 0 for c in counts]
    hire_pct = round(100 * counts[4] / n, 1) if n else 0
    return {"n": n, "counts": counts, "pct": pct, "hire_pct": hire_pct}


with_rank, with_lt_ids = lt_ranks(lt_with)
without_rank, without_lt_ids = lt_ranks(lt_without)
with_ids = {r["Id"] for r in with_jas}
without_ids = {r["Id"] for r in without_jas}

print("=== none / unreachable ===", flush=True)
none_tasks = q("SELECT Job_Application__c FROM Ringtime_Task__c WHERE Status__c = 'Completed' AND Outcome__c = 'none'")
none_ids = {t["Job_Application__c"] for t in none_tasks if t.get("Job_Application__c")}
unreach = q(
    "SELECT cxsrec__Job_application__c FROM cxsrec__cxsStep__c "
    "WHERE cxsrec__Rejection_reason__c = 'Unreachable' AND cxsrec__Workflow_event_name__c = 'Afwijzen'"
)
unreach_ids = {s["cxsrec__Job_application__c"] for s in unreach if s.get("cxsrec__Job_application__c")}
none_in_with = len(with_ids & none_ids)
unreach_in_without = len(without_ids & unreach_ids)

print("=== TAS users + wait ===", flush=True)
tas_users = {u["Id"] for u in q("SELECT Id FROM User WHERE UserRole.Name = 'TAS'")}
print("TAS users", len(tas_users), flush=True)

completed = [t for t in tasks if t.get("Status__c") == "Completed" and t.get("Ringtime_Task_Id__c") and t.get("Job_Application__c")]
active_jas = {t["Job_Application__c"] for t in tasks if t.get("Status__c") == "Active" and t.get("Job_Application__c")}
last_done = {}
for t in completed:
    dt = parse_dt(t.get("Completed_At__c") or t.get("CreatedDate"))
    jid = t["Job_Application__c"]
    if jid in active_jas:
        continue
    if dt and (jid not in last_done or dt > last_done[jid]):
        last_done[jid] = dt
ready_ids = list(last_done)
print("Lou klaar JAs", len(ready_ids), flush=True)

steps = []
for b in batches(ready_ids, 70):
    part = ",".join(f"'{x}'" for x in b)
    steps += q(
        "SELECT CreatedDate, CreatedById, cxsrec__Job_application__c, cxsrec__Workflow_event_name__c "
        "FROM cxsrec__cxsStep__c "
        f"WHERE cxsrec__Job_application__c IN ({part}) "
        "ORDER BY CreatedDate ASC"
    )
    time.sleep(0.35)
print("steps on ready JAs", len(steps), flush=True)

first_tas = {}
first_event = {}
for s in steps:
    jid = s.get("cxsrec__Job_application__c")
    if jid not in last_done:
        continue
    if s.get("CreatedById") not in tas_users or s.get("CreatedById") in SYSTEM:
        continue
    dt = parse_dt(s.get("CreatedDate"))
    if not dt or dt <= last_done[jid]:
        continue
    if jid not in first_tas:
        first_tas[jid] = dt
        first_event[jid] = s.get("cxsrec__Workflow_event_name__c") or ""

waits_h = []
for jid, start in last_done.items():
    stop = first_tas.get(jid)
    if not stop:
        continue
    waits_h.append(((stop - start).total_seconds() / 3600.0, first_event.get(jid) or ""))

n_ready = len(last_done)
n_with_tas = len(waits_h)
hours = [h for h, _ in waits_h]
hours.sort()


def pct(n, d):
    return round(100 * n / d) if d else 0


def classify_event(name):
    n = (name or "").lower()
    if "afwijzen" in n:
        return "Afwijzen"
    if "intake tas" in n:
        return "Intake TAS"
    if "teruggetrokken" in n or "unregist" in n:
        return "Kandidaat trekt zich terug"
    if "screening ts" in n or "talentpool" in n or "intake ts" in n:
        return "Screening TS of talentpool"
    if "assign" in n or "prescreen" in n or "screening tas" in n:
        return "Assign / Prescreening / Screening TAS"
    if not name:
        return "Geen eventnaam"
    return name


ev = collections.Counter(classify_event(e) for _, e in waits_h)
buckets_wait = collections.Counter()
for h, _ in waits_h:
    if h < 4:
        buckets_wait["<4u"] += 1
    elif h < 24:
        buckets_wait["4-24u"] += 1
    elif h < 72:
        buckets_wait["1-3d"] += 1
    elif h < 168:
        buckets_wait["3-7d"] += 1
    else:
        buckets_wait[">7d"] += 1

print("=== rejections ===", flush=True)
rt_ja = sorted({t["Job_Application__c"] for t in tasks if t.get("Job_Application__c")})
lou_jas = []
for b in batches(rt_ja, 80):
    part = ",".join(f"'{x}'" for x in b)
    lou_jas += q(
        "SELECT Id, cxsrec__Workflow_status__r.Name FROM cxsrec__cxsJob_application__c "
        f"WHERE Id IN ({part})"
    )
    time.sleep(0.3)
rejected = [r for r in lou_jas if "Afgewezen" in (status_name(r) or "")]
withdrawn = [r for r in lou_jas if "teruggetrokken" in (status_name(r) or "").lower()]
rej_ids = [r["Id"] for r in rejected]
status_by = {r["Id"]: status_name(r) for r in rejected}
rej_steps = []
for b in batches(rej_ids, 80):
    part = ",".join(f"'{x}'" for x in b)
    rej_steps += q(
        "SELECT CreatedDate, cxsrec__Job_application__c, cxsrec__Rejection_reason__c "
        "FROM cxsrec__cxsStep__c "
        f"WHERE cxsrec__Job_application__c IN ({part}) "
        "AND cxsrec__Workflow_event_name__c = 'Afwijzen' "
        "ORDER BY CreatedDate ASC"
    )
    time.sleep(0.3)
last_reason = {}
for s in rej_steps:
    last_reason[s["cxsrec__Job_application__c"]] = s.get("cxsrec__Rejection_reason__c")
rc = collections.Counter(last_reason.get(j) or "(leeg)" for j in rej_ids)
grid = collections.Counter()
for jid, status in status_by.items():
    reason = last_reason.get(jid) or "(leeg)"
    if "Nieuw" in (status or ""):
        st = "Na Nieuw"
    elif "Prescreening" in (status or ""):
        st = "Na Prescreening"
    elif "Screening TAS" in (status or ""):
        st = "Na Screening TAS"
    elif "Screening TS" in (status or ""):
        st = "Na Screening TS"
    else:
        st = status
    grid[(reason, st)] += 1

out = {
    "as_of": datetime.now(timezone.utc).date().isoformat(),
    "overview": {
        "tasks": len(tasks),
        "with_rtid": n_rtid,
        "without_rtid": len(tasks) - n_rtid,
        "wa": n_wa,
        "voice": n_voice,
        "active": n_active,
        "first": first.date().isoformat() if first else None,
        "last": last.date().isoformat() if last else None,
        "weeks": week_rows,
        "wa_pie": pie3(wa_buckets),
        "voice_pie": pie3(voice_buckets),
        "task_buckets": dict(task_buckets),
    },
    "with": {
        **process_stats(with_jas),
        "end": end_status(with_jas),
        "funnel": funnel(with_jas, with_rank),
        "with_lead_time": len(with_lt_ids),
        "none": none_in_with,
        "none_pct": round(100 * none_in_with / len(with_ids), 1) if with_ids else 0,
    },
    "without": {
        **process_stats(without_jas),
        "end": end_status(without_jas),
        "funnel": funnel(without_jas, without_rank),
        "with_lead_time": len(without_lt_ids),
        "unreachable": unreach_in_without,
        "unreachable_pct": round(100 * unreach_in_without / len(without_ids), 1) if without_ids else 0,
    },
    "tas_wait": {
        "ready": n_ready,
        "with_step": n_with_tas,
        "no_step": n_ready - n_with_tas,
        "median_days": round(statistics.median(hours) / 24, 1) if hours else None,
        "avg_days": round(statistics.mean(hours) / 24, 1) if hours else None,
        "max_days": round(max(hours) / 24, 1) if hours else None,
        "within_4h": pct(buckets_wait["<4u"], n_with_tas),
        "within_24h": pct(buckets_wait["<4u"] + buckets_wait["4-24u"], n_with_tas),
        "hours_buckets": dict(buckets_wait),
        "first_events": ev.most_common(),
        "reject_first": ev.get("Afwijzen", 0),
    },
    "rejections": {
        "lou_jas": len(lou_jas),
        "rejected": len(rejected),
        "withdrawn": len(withdrawn),
        "reasons": rc.most_common(),
        "grid": [[k[0], k[1], v] for k, v in grid.items()],
    },
}
path = "/tmp/lou_kpi_20260921.json"
json.dump(out, open(path, "w"), indent=2, ensure_ascii=False, default=str)
print("wrote", path)
print(json.dumps({k: out[k] if k != "rejections" else {**out[k], "grid": "…"} for k in out}, indent=2, ensure_ascii=False, default=str)[:8000])
