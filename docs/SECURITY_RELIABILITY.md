# Security & Reliability

## Security controls

| Control | Implementation |
|---------|----------------|
| Password hashing | bcrypt (12 rounds); legacy Django PBKDF2 hashes upgrade on first login |
| Session | Streamlit `st.session_state` stores only the username; user is re-read from Mongo every run |
| Uploads | Extension allow-list (csv/json/xlsx), size cap, content sniff in `validators.py` |
| Secrets | `.env` gitignored; `.env.example` has no secrets |
| RBAC | `PERMISSIONS` matrix + `require()` inside mutating functions |
| Data scoping | Analysts read only `region_focus` (`weatherpredict.scoping`) |
| PII | username + email + role only — no phone field, no at-rest field encryption needed |

TLS: terminate at a reverse proxy. Mongo production URI form: `mongodb://user:pass@host/?tls=true`.

## Monitoring

- `logs/weatherpredict.log`
- Operations console counters + host disk / PID
- `python -m weatherpredict.health` (exit code 2 if Mongo is down)
- Streamlit `/_stcore/health`
- `MAINTENANCE_MESSAGE` env var for scheduled-maintenance banner
- `pipeline_runs` / `ingestion_jobs` ledgers include `duration_seconds`

## Backup (NFR)

```powershell
python -m weatherpredict.backup
```

Writes `backups/<UTC stamp>/` with Mongo dump (mongodump or JSON fallback), `ml_artifacts/`, and `manifest.json`. Folders older than 14 days are pruned.

**Windows Task Scheduler:** Daily 02:00, action `python -m weatherpredict.backup`, start in the project directory, run whether user is logged on.

## 99% uptime and load balancing

99% is an **operational SLO** of the host (supervised process, restart policy, external uptime check). This repo cannot promise it on a student workstation.

Streamlit holds session state in one process. If you run two instances behind nginx:

- `proxy_set_header Upgrade $http_upgrade;` (WebSocket for Streamlit)
- sticky sessions (`ip_hash`) — round-robin will log users out

A sample `deploy/nginx.conf` is not required for the local demo; document the constraint before adding a second worker.

## Retrain schedule

Weekly: `python -m weatherpredict.retrain` (Task Scheduler). Each run versions `ml_artifacts` documents instead of overwriting `version=1`.
