# Deploying on Vercel

Vercel **serverless** runtimes only allow writing under **`/tmp`**. A SQLite file like `./app_data.db` in the project directory **will fail** (500 / `FUNCTION_INVOCATION_FAILED`) because the filesystem is read-only.

This repo handles that automatically: when `VERCEL` or `VERCEL_ENV` is set, the app uses **SQLite under the OS temp directory** (on Vercel that is writable storage under `/tmp`) unless you override with **`DATABASE_URL`**.

## Required environment variables

Set these in the Vercel project **Settings → Environment Variables**:

| Variable | Why |
|----------|-----|
| `SECRET_KEY` | Stable value (e.g. 32+ random bytes). If missing, a new key is generated on every cold start and **signed sessions / JWTs break** between invocations. |
| `SESSION_SECRET` | Optional; defaults to `SECRET_KEY`. Used for the web session cookie. |
| `JWT_SECRET` | Optional; defaults to `SECRET_KEY`. Used for API JWTs. |

## Data persistence

- **`/tmp` SQLite** is only suitable for demos: data can disappear between cold starts or scaling events.
- For a real deployment, set **`DATABASE_URL`** to a hosted database (e.g. [Neon](https://neon.tech) Postgres). You will need a SQLAlchemy-compatible URL and the matching driver (e.g. add `psycopg[binary]` to `requirements.txt` for `postgresql+psycopg://...`).

## Static files

Vercel serves files under **`public/`** from the CDN. This app still mounts **`/static`** from the `static/` folder when that directory exists in the deployment bundle (normal for this repo). If you move assets, keep `static/` in the repo or adjust `app/main.py` and templates accordingly.

## Entrypoint

`pyproject.toml` contains `[tool.vercel] entrypoint = "app.main:app"` so Vercel loads the FastAPI instance from `app/main.py` reliably.

After changing env vars, redeploy.
