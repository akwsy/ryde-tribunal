# Hosted synthetic judge demo

The shared judge demo runs against a separate database containing generated records only. Never use `ryde_tribunal` or copy the local company database into the hosted project. Normal application startup does not migrate or reseed the database.

## Services

- **Frontend:** Vercel, with the project root set to `frontend` and the repository parent directory enabled for shared contract files if Vercel requests it.
- **API:** Render, created from the root `render.yaml` blueprint. Its Docker image is in `deploy/backend.Dockerfile`.
- **Database:** an isolated Neon project and database named `ryde_tribunal_demo`.

Use a separate synthetic-only Neon project. The initial setup checks the connected database name and refuses to seed if application tables already exist. Take a Neon branch snapshot before first initialization. Do not run the initializer a second time against a populated database.

## One-time database setup

Create a Neon database named `ryde_tribunal_demo`, then store its direct PostgreSQL connection string in the private operator environment. Keep it out of shell history, screenshots, Git, deployment logs, and messages. Use the `DEMO_ADMIN_DSN` only for initialization. The seed includes 47 generated historical decisions, 16 recent trips, and six current-policy examples. It creates separate read and write roles for the app.

Prepare the private values with:

```sh
python tools/demo_credentials.py /absolute/path/outside/the/repository
```

The output directory contains the judge passcode and generated secrets with owner-only file permissions. Supply the database connection and those generated role passwords to the one-time initializer through the operator's private environment, then run:

```sh
python tools/demo_admin.py initialize
```

The initializer requires Python dependencies from `backend/requirements.txt`; use the project's existing backend environment. It refuses a non-demo database name and refuses to reseed a database with existing application tables.

If migrations and the synthetic seed already exist but setup stopped before demo cases were filed, use `python tools/demo_admin.py complete` instead of `initialize`. This recovery command checks the database name, migration versions, exact seed counts, synthetic-only provenance, and any partially filed demo cases before it continues. It records its prepared and complete stages so it can safely resume; it never reseeds or clears existing data. If those checks do not match the known generated state, it stops for inspection.

## Render API configuration

Set the variables marked `sync: false` in the Render service dashboard. Use the role-specific Neon connection strings for `READ_DATABASE_DSN` and `TRIBUNAL_DATABASE_DSN`; the frontend must never receive them.

| Variable | Value |
| --- | --- |
| `DEMO_ACCESS_ENABLED` | `true` |
| `DEMO_SECURE_COOKIES` | `true` |
| `POLICY_VERSION` | `ryde-policy-1.1.0` |
| `DEMO_PUBLIC_ORIGIN` | Exact Vercel HTTPS origin, with no trailing slash |
| `DEMO_PASSCODE_HASH` | Hash from the private generated secrets file |
| `DEMO_SESSION_SECRET` | Random value from that file |
| `READ_DATABASE_DSN` | Neon connection string for the read-only demo role |
| `TRIBUNAL_DATABASE_DSN` | Neon connection string for the demo writer role |
| `MODEL_PROVIDER` | Configured provider; leave unset or use the validated deterministic mode if no live key is available |
| `MODEL_PROVIDER_NAME`, `MODEL_BASE_URL`, `MODEL_NAME`, `MODEL_API_KEY` | Exact values for a verified provider; keep the key only in Render |

Keep the import database setting empty. Hosted bulk import is blocked by the demo access middleware. The health endpoint exposes only service status; API routes and API documentation require a valid judge session.

## Vercel frontend configuration

Set `NEXT_PUBLIC_API_BASE_URL=/api/v1`, `NEXT_PUBLIC_DEMO_ACCESS=true`, and `INTERNAL_API_ORIGIN` to the Render HTTPS origin. These are the only API-routing settings exposed to the browser. Do not add a database URL, passcode hash, session secret, or model key to a `NEXT_PUBLIC_` variable.

After the first deployment, copy the Vercel origin into Render's `DEMO_PUBLIC_ORIGIN`, redeploy the API, then redeploy the frontend. Confirm sign-in and direct API protection in a signed-out browser before sharing the link.

## Fresh start and recovery

Restarting either app service must preserve disputes and reviewer actions. Do not attach a startup seed command. Before replacing the demo, create a fresh isolated database or restore a Neon snapshot into a separate branch; never reset the local primary database. Keep the judge passcode separate from the public URL and share it only with intended reviewers.

Render's free API service can sleep between visits; the first request may take a short while. If it remains unavailable, show the startup retry message and check the Render service logs without exposing secrets. Free-tier availability and limits can change; describe them as observed at deployment time.
