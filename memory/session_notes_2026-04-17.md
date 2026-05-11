# Session Notes — April 17, 2026 (Compressed)

## Deployed Features
- **Revenue Dashboard** (`/revenue`): Admin-only, commit `7eb7a65`. KPI cards, bar charts, monthly table, practice area breakdown.
- **User Provisioning**: 13 accounts created (1 admin: mattusa, 1 admin: john@jcsattorney.com, 11 attorneys). Script: `provision_users.sql`.
- **Attorney-Routed Screen Pops**: Commit `77ca086`. RingCentral webhook active (expires 2036).

## Open Issues (Carried Forward)
- **Jen Kusmer login**: Username `jen@jcsattorney.com` — password was regenerated twice but still fails. Suspect `is_active = FALSE` in DB. Debug: `SELECT username, is_active, role FROM dashboard_users WHERE firm_id = 'jcs_law' AND username ILIKE '%jen%';`
- **Stale service**: `mycase-dashboard.service` crash-looping on prod (port conflict). Fix: `sudo systemctl stop mycase-dashboard.service && sudo systemctl disable mycase-dashboard.service`

## Production Quick Reference
- **Server**: root@jcs-dashboard, code at `/opt/jcs-mycase`
- **Service**: `jcs-dashboard.service`, port 3000
- **URL**: `https://jcs.lawmetrics.ai`
- **Deploy**: `cd /opt/jcs-mycase && git pull && find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; sudo systemctl restart jcs-dashboard`
