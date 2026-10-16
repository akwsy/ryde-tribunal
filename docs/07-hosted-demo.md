# Online demo: access, setup, and status

## Use the demo

Open **[https://ryde-tribunal.vercel.app/](https://ryde-tribunal.vercel.app/)**. Choose **Explore as a reviewer** to browse the synthetic case workspace or **Explore the evidence** to inspect a sample case. Guest profiles are read-only. Filing, adjudication, approvals, overrides, and imports are not saved from a guest profile.

The sign-in page also has a judge-passcode option for authorised reviewers. The passcode is private and must be shared separately by the project owner. Do not place it in this repository or in a public submission.

### Current availability

The Vercel frontend is published and loads. The API route is connected to Render, but the latest Render deployment failed its database safety check. The reviewer dashboard may therefore show **“historical archive is unavailable”** until Render is configured to use the dedicated synthetic demo database. Do not present the online case history as working until the cases load successfully.

The guard intentionally refuses to start the hosted API when either `READ_DATABASE_DSN` or `TRIBUNAL_DATABASE_DSN` points to the primary `ryde_tribunal` database or any database other than `ryde_tribunal_demo` (test-only suffixes are allowed for tests). Use a dedicated Neon database, not the local company-data database or the Neon default database.

## Online architecture

- **Frontend:** Vercel serves the Next.js app at the link above.
- **API:** Render runs the FastAPI service created from [`render.yaml`](../render.yaml), built with [`deploy/backend.Dockerfile`](../deploy/backend.Dockerfile).
- **Database:** Neon hosts an isolated database named `ryde_tribunal_demo` with synthetic demo records only.

Vercel sends same-origin `/api/v1` requests to the Render API through `INTERNAL_API_ORIGIN`. Render keeps database DSNs, judge credentials, and any model key server-side. The Render free service can sleep while idle, so its first request may take 50 seconds or more.

## Prepare the synthetic demo database

Complete this once against a fresh, dedicated Neon project. Never copy or seed the primary local database into the hosted environment. Normal service startup must not migrate, clear, or reseed data.

Create a database named `ryde_tribunal_demo`. Use the private operator setup to initialise it; the guarded initializer creates migrations, synthetic examples, and separate read/write roles. It refuses an unexpected database name or an already populated application schema.

Generate private demo credentials outside the repository:

```bash
python tools/demo_credentials.py /absolute/path/outside/the/repository
```

Use the owner-only output and private environment to run the initializer:

```bash
python tools/demo_admin.py initialize
```

The seed is synthetic. It includes historical sample decisions and current-policy examples. Do not run `initialize` again after a successful setup. If setup stopped after migrations and seeding but before demo cases were filed, use the guarded recovery command:

```bash
python tools/demo_admin.py complete
```

Recovery verifies the database name, migration versions, expected seed counts, and synthetic provenance before continuing. It never clears or reseeds existing records. If its checks fail, stop and inspect the database rather than bypassing the guard.

## Configure Render

In the `ryde-tribunal-demo-api` service’s Environment settings, configure the variables listed below. Never include any connection string in the browser, README, screenshots, or public messages.

| Variable | Required value |
| --- | --- |
| `DEMO_ACCESS_ENABLED` | `true` |
| `DEMO_SECURE_COOKIES` | `true` |
| `POLICY_VERSION` | `ryde-policy-1.1.0` |
| `DEMO_PUBLIC_ORIGIN` | `https://ryde-tribunal.vercel.app` |
| `DEMO_PASSCODE_HASH` | Passcode hash from the private credentials output |
| `DEMO_SESSION_SECRET` | Random session secret from the private credentials output |
| `READ_DATABASE_DSN` | Read-only role’s PostgreSQL connection string for `ryde_tribunal_demo` |
| `TRIBUNAL_DATABASE_DSN` | Writer role’s PostgreSQL connection string for `ryde_tribunal_demo` |
| `MODEL_PROVIDER`, `MODEL_PROVIDER_NAME`, `MODEL_BASE_URL`, `MODEL_NAME`, `MODEL_API_KEY` | Optional provider configuration; keep API keys in Render only |

Both DSNs must have `/ryde_tribunal_demo` as their database path and use their respective read-only or writer role. Save and redeploy the service after changing variables. Do not use the Neon owner/admin string for the app’s read-only connection. Keep the import database setting empty; hosted bulk import is disabled.

## Configure Vercel

The Vercel project should use `frontend` as its root directory and include the repository root for shared files. Configure:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `/api/v1` |
| `NEXT_PUBLIC_DEMO_ACCESS` | `true` |
| `INTERNAL_API_ORIGIN` | `https://ryde-tribunal-demo-api.onrender.com` |

Only the first two values are intended for browser use. Never add a database DSN, judge passcode/hash, session secret, or model API key to a `NEXT_PUBLIC_` variable. Redeploy Vercel after changing build-time routing settings.

## Verify before sharing

1. Confirm both Render DSNs target `ryde_tribunal_demo` and use the correct role.
2. Confirm Render reports a successful deployment and `https://ryde-tribunal-demo-api.onrender.com/healthz` returns `{"status":"ok"}`.
3. Open the Vercel URL in a signed-out browser and use a guest profile. The dashboard should load cases and charts without an archive-unavailable message.
4. Confirm guest writes remain blocked, direct protected API requests require a session, and a reviewer’s approved or overridden decision survives a refresh.
5. Keep the judge passcode private and share it only with intended reviewers.

Restarting a service must preserve filings and reviewer actions. Do not attach a seed command to normal startup. Before a deliberate demo reset, create a separate Neon branch or snapshot and use the guarded operator workflow; never reset `ryde_tribunal`.
