# Brief — Frontend specialist

Historical Phase Zero delegation brief. Its task instructions and route plans are preserved as
a record; use the current contract and component README for present work.

Phase Zero, with the Phase One dashboard target stated so you build toward it rather than around it.
Read `docs/00-ownership.md`, `docs/02-api-contract.md` §2–4, and `docs/04-integrity-rules.md` I-6.

Phase Zero has been signed off. D-12 is resolved; Node.js 20.20.2 and npm 10.8.2 are installed on the project Mac.

## 1. Mission and scope

Phase Zero: a working interface that displays a full case result — case details, both advocate panels,
the Judge's ruling with confidence and reasoning, and evidence on demand.

Phase One: the ~80%-complete dispute-manager dashboard in the handoff §3. Structure Phase Zero so Phase
One is an extension, not a rewrite: build against the real API contract, keep data fetching in a typed
client layer, and keep every state (loading, empty, error, escalated) a first-class render path from the
start.

## 2. Non-goals

- You never connect to PostgreSQL. API calls only, through the typed client.
- You do not compute rulings, confidence, urgency, or deviation in the browser. Display what the API
  returns.
- You do not mock a result inline in a component to make a screen look finished. Mocks live in the
  fixture layer and are visibly labelled.
- You do not build Phase One's charts and filters until Phase Zero is approved.

## 3. Allowed paths

`frontend/**` — app/route files, `frontend/src/components/`, `frontend/src/lib/api/`,
`frontend/src/fixtures/`, `frontend/tests/`, `frontend/README.md`, `frontend/ASSUMPTIONS.md`,
`frontend/package.json`.

## 4. Forbidden paths

`backend/**`, `database/**`, `shared/**`, `docs/**`, `tests/**`, `README.md`, `.env.example`.

## 5. Contracts

**Input:** the HTTP contract in `docs/02-api-contract.md` and the JSON Schemas in `shared/schemas/`.
Generate your TypeScript types from `shared/openapi.yaml` — do not hand-write them, and do not widen a
type to make a component compile. A type mismatch is a contract issue to raise.

**Output:** the Phase Zero case view, plus a typed API client whose every method maps to one documented
endpoint. Base URL from `NEXT_PUBLIC_API_BASE_URL`.

**Required displays, Phase Zero:**

- case details and status
- Rider Advocate argument + evidence summary, and Driver Advocate the same, on opposite sides
- Judge ruling, recommended action (money formatted from `amount_cents` + currency — never parse a
  float), confidence, reasoning
- clickable evidence controls that reveal the underlying evidence record
- per-evidence **verification status and uncertainty percentage**
- escalation state and, when escalated, the human-review summary
- **a visible badge whenever `synthetic_reasoning` is true** (integrity rule I-6). Do not label
  scripted output as advocate or Judge reasoning without it. This is an acceptance criterion.

**Phase One additions (do not build yet):** today/week/month counts, automatically-processed count, a
time-series line graph separating automatic from human-intervention cases, the human-review queue with
filtering and urgency sorting, approve-a-resolution, and override-a-resolved-case with a reason code from
the closed vocabulary.

## 6. Dependencies and assumptions

*Given:* Next.js 15 App Router + TypeScript + Tailwind + Recharts (D-02); Node 20 LTS once installed
(D-12); reviewer identity sent as `X-Reviewer-Id` (D-07); money as integer cents; `80% complete` means
feature completeness, not visual polish (D-15); no image analysis (D-16).

*Record in `frontend/ASSUMPTIONS.md`:* component structure, how you render an unknown/new `ruling_type`
or `reason_code` without crashing, and your accessibility approach.

*Ambiguous → ask:* any display that would require you to invent a number the API does not return.

## 7. Required tests

- The case view loads from a fixture response and from a live API response with no hardcoded production
  results anywhere in component source.
- Loading, empty, error, and escalated states each render a distinct, correct surface. Test them
  explicitly, including a 500 and a `database_unavailable` error body.
- Evidence controls reveal the evidence record; verification status and uncertainty percentage render,
  including the case where uncertainty is absent.
- Money renders correctly from `amount_cents` for `325` → `$3.25`, for `0`, and for a large value.
- **`synthetic_reasoning: true` renders the badge; `false` does not.** Both asserted.
- Confidence renders at the declared precision and is visually prominent.
- An unknown enum value renders a safe fallback rather than throwing.
- A source scan finds no `fetch` to a database, no SQL string, and no credential.
- Keyboard navigation reaches every evidence control; axe reports no critical violations.

## 8. Passing criteria

All §7 tests pass; the app runs against a live backend and against fixtures with one env change;
`frontend/README.md` documents setup, run, test, and fixture mode; types are generated from the shared
contract and the generation step is in `package.json`.

## 9. Handoff artifacts

`frontend/README.md`, `frontend/ASSUMPTIONS.md`, the typed client, the test log, screenshots of each
state (loaded, escalated, error, empty, synthetic-reasoning badge), and a pinned dependency list. Report
to the lead agent.

## 10. Git and GitHub

Read `docs/06-git-workflow.md` in full. It is binding. The owner-set rules that apply to you:

- **Your branch prefix is `fe/`.** Branch from `main`, never from another specialist's branch.
- **You hold at most one branch at a time** — one in existence, not one in progress. Your previous
  branch must be merged and deleted on the remote *and* locally before you cut the next one. No second
  branch to park work or to try a different visual direction. If the work does not fit one branch, say so
  and the section gets split.
- **Push to GitHub when you are done with your changes**, then open a pull request against `main`. A push
  is a claim the work is done, so `bash tools/ci/check-ownership.sh`, `bash tools/ci/check-secrets.sh`,
  `bash tools/ci/check-one-branch.sh` and your §7 suite must be green first.
- Address review feedback on the **same** branch. Never force-push a branch under review.
- After the lead agent squash-merges, delete the branch to free your slot.
- You do not merge your own pull request.

Your diff must stay inside `frontend/`. Generated TypeScript types from `shared/openapi.yaml` are
committed **into your own tree**; you never edit `shared/`. `node_modules/` and `.next/` are gitignored
and must never appear in a commit.

Commit subjects use the `fe:` prefix, e.g. `fe: render synthetic-reasoning badge on the case view`.
