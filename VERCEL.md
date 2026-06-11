# Deploying on Vercel

Vercel **serverless** workers do not give you a durable writable disk. A SQLite file in the project directory **fails** (read-only FS). SQLite under `/tmp` **appears to work** but data is **lost** on cold starts, new instances, and redeploys — which looks like “logout then everything is gone”.

**Production rule:** set **`DATABASE_URL`** to **Postgres** (this repo ships the **`psycopg`** driver). The app **requires** `DATABASE_URL` when `VERCEL` / `VERCEL_ENV` is set.

## 1. Create a Postgres database (Neon)

1. Sign up at [Neon](https://neon.tech) and create a project + database.
2. Copy the **connection string** (often `postgresql://...` or `postgres://...` with `sslmode=require`).
3. Paste it as **`DATABASE_URL`** in Vercel. The app normalizes `postgres://` → `postgresql+psycopg://` so Neon’s default string usually works as-is.

## 2. Required environment variables

Set these in **Vercel → Project → Settings → Environment Variables** (apply to **Production** and **Preview** as needed):

| Variable | Why |
|----------|-----|
| **`DATABASE_URL`** | **Required on Vercel.** Persistent storage for users, orgs, expenses. Without it the app fails fast at startup instead of silently losing data. |
| `SECRET_KEY` | Stable value (e.g. 32+ random bytes). If missing, a new key is generated on every cold start and **signed sessions / JWTs break** between invocations. |
| `SESSION_SECRET` | Optional; defaults to `SECRET_KEY`. Used for the web session cookie. |
| `JWT_SECRET` | Optional; defaults to `SECRET_KEY`. Used for API JWTs. |

After changing env vars, **redeploy** so new values apply.

## 3. Local development

Without `VERCEL` / `VERCEL_ENV`, the app still defaults to **`sqlite:///./app_data.db`** in the project directory.

To test against Postgres locally, set `DATABASE_URL` to the same Neon (or local) URL.

## 4. Migrations

`app/main.py` runs `Base.metadata.create_all` on startup. `app/db_migrate.py` only applies **SQLite** additive migrations; on Postgres, `create_all` defines the schema for a fresh database.

## 5. Static files

Vercel serves files under **`public/`** from the CDN. This app mounts **`/static`** from the `static/` folder when that directory exists in the deployment bundle.

## 6. Entrypoint

`pyproject.toml` defines **`[project]`** (required by Vercel’s **`uv lock`** install) and **`[tool.vercel] entrypoint`**. Dependency pins are mirrored in **`requirements.txt`** for local `pip install -r`; keep them aligned when you upgrade packages.
