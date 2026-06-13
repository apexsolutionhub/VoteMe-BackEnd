# voteMe Backend (Django)

## Git — nested repo (same as hotcol-user)

`BackEnd/` is its **own git repo** inside the frontend monorepo.

- From **`BackEnd/`** → `git push origin main` → [VoteMe-BackEnd](https://github.com/apexsolutionhub/VoteMe-BackEnd) (Django only)
- From **repo root** → `git push frontend main` → [VoteMe](https://github.com/apexsolutionhub/VoteMe) (full project; `BackEnd` is stored as a folder link to a commit)

### One-time setup

**1. Create the backend repo inside `BackEnd/`**

```powershell
cd C:\Users\abdur\Documents\Projects\voteme\BackEnd
git init
git remote add origin https://github.com/apexsolutionhub/VoteMe-BackEnd.git
git add .
git commit -m "Initial backend"
git push -u origin main
```

**2. Point the root repo at the nested folder (not individual BackEnd files)**

```powershell
cd C:\Users\abdur\Documents\Projects\voteme
git rm -r --cached BackEnd
git add BackEnd
git commit -m "Track BackEnd as nested repo"
git remote add frontend https://github.com/apexsolutionhub/VoteMe.git
git push -u frontend main
```

After this, `git ls-tree HEAD BackEnd` should show mode `160000` (commit link), like hotcol-user.

### Daily workflow

```powershell
# Backend changes
cd BackEnd
git add .
git commit -m "backend change"
git push origin main

cd ..
git add BackEnd
git commit -m "Update BackEnd pointer"
git push frontend main
```

When you only change backend, you still commit in `BackEnd/` first, then update the pointer in the root repo so the frontend repo knows which backend commit to use.

## Setup

```bash
cd BackEnd
python -m venv venv
.\venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Configure `BackEnd/venv/.env` (see `.env.example`).

## Database

Uses MySQL (Aiven). Required env vars:

- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

## Commands

```bash
python manage.py migrate
python manage.py seed_admin      # creates ellaVote / 12345678
python manage.py runserver
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/signup/` | POST | Create organization + owner admin |
| `/api/auth/login/` | POST | Login (`username`, `password`, `role`, `organization_slug`) |
| `/api/auth/refresh/` | POST | Refresh access token |
| `/api/auth/me/` | GET/PATCH | Current user |
| `/api/auth/change-password/` | POST | Change password |
| `/api/organizations/me/` | GET | Organization + competition context |
| `/api/organizations/competition/` | GET/PATCH | Competition settings |
| `/api/organizations/competition/status/` | POST | Set competition status |
| `/api/organizations/competition/sync/` | POST | Sync engagement metrics |
| `/api/organizations/candidates/` | GET/POST | Org-scoped candidates |
| `/api/organizations/candidates/<id>/` | DELETE | Delete candidate profile |
| `/api/candidate/me/profile/` | GET/PATCH | Candidate profile |
| `/api/candidate/me/stats/` | GET | Candidate engagement stats |
| `/api/candidate/me/videos/` | GET/POST | Competition video links |
| `/api/public/<slug>/leaderboard/` | GET | Public results ceremony (when competition ended) |

## Engagement sync

```bash
python manage.py sync_engagement
```

Run on a schedule (cron) for live competitions with tracking enabled. Example crontab entry:

```cron
*/10 * * * * cd /path/to/voteme/BackEnd && /path/to/venv/bin/python manage.py sync_engagement
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `PUBLIC_SIGNUP_ENABLED` | `true` to allow `/signup` (default `false`, invitation-only) |
| `BRAND_MENTION_KEYWORD` | Keyword to count in comments (default `ellaresort`) |

When onboarding a paid client, set `PUBLIC_SIGNUP_ENABLED=true`, send them `https://yoursite.com/signup`, then disable again after registration.
