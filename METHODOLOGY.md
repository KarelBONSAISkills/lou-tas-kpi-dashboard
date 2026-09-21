# Methodology — Lou KPI dashboard

Snapshot language: Dutch, for Logi-Technic management.

## Universe

Website applications on the pool vacancy (PVLT workflow), created in 2026, `cxsrec__Created_from__c = Form`.

Workflow Id: `a167R00000WP9gAQAT`.

## Tab 0 — Lou tasks

All `Ringtime_Task__c` since go-live (10 Aug 2026). Channel from `Campaign_Key__c` (`wa*` vs `voice*`).

## Tab 1 — Lead time

Average `cxsrec__Process_time__c` on the two groups above. Failed Ringtime tasks do **not** put a fiche in “met afronding”.

## Tab 2 — Outcomes

Task `Status__c` + `Outcome__c`. `Failed` / `Cancelled` / `Active` win over outcome. No TAS comparison: voicemails are not logged consistently.

## Tab 3 — Wait until first TAS step

Clock starts at last **Completed** Lou task (`Completed_At__c`) with a Ringtime Id. Clock stops at the first later `cxsrec__cxsStep__c` created by a user with role **TAS** (not Lou, not integration users). Fiches with an Active Lou task are excluded.

## Tab 4 — Funnel + unreachable

Ever-reached ranks from current workflow status and `Lead_Time__c` Previous/Current status:

0 Nieuw → 1 Prescreening → 2 TAS screening → 3 TS screening → 4 Hired (`6.0 Aangeworven (PVLT)` only).

## Tab 5 — Rejection reasons

Job applications with any Ringtime task, currently rejected, last Connexys step event **Afwijzen**, field `cxsrec__Rejection_reason__c`.
