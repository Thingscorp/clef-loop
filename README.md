# clef-loop

Clef is a **decision helper for coding agents** — it judges; it does not chat, code, or complete. `clef-loop` wraps it in a **recursive six-phase QA loop**: the agent does the legwork (reads code, writes the test sheet, runs cases, applies fixes) and Clef makes every judgment call — coverage, deduplication, risk triage, failure triage, severity, fix review, regression verdict, confidence, and loop termination.

The rule of the loop: **the agent is the hands, Clef is the judge.** No gated decision is made on the agent's judgment alone, and no phase exits without its Clef gate passing.

## Verified claims

Every claim below is backed by a test in `tests/` — fully mocked, no network, no key, no charges. Run them yourself: `python3 -m unittest discover -s tests` (48/48 pass, ~0.1s).

| Claim | Backing data |
|---|---|
| POSTs only to the two known endpoints | `test_request_shape` asserts the exact URL and POST method; `test_endpoints_are_the_only_real_urls_in_source` scans `bin/clef-decide` for any other URL — none exists |
| API key from standard config, never prompted or logged | `test_missing_key_stops` (helper refuses without it); `test_key_never_prompted_interactively` (no `input()`/`getpass` anywhere in source); `tests/test_config.py` proves the full precedence chain |
| No retries, no idempotency key | `test_no_retry_on_transport_error`: a failed transport produces exactly 1 attempt, never a resend; `test_no_idempotency_header_sent` |
| 16,384-token budget enforced before sending | `test_context_budget_refuses`; `test_constants_match_claims` pins the constant |
| ≤32 questions, ≤64 options, 2–10 score levels | `test_gateway_bounds` exercises each bound; `test_constants_match_claims` pins them |
| `bin/clef-decide` is executable and stdlib-only | `test_helper_is_executable`; `test_stdlib_only_imports` (imports: argparse, concurrent.futures, json, os, sys, urllib — nothing else) |
| SystemOne model is `clef`, `clef-flash`, or `jev-latest` only (`:free` preserved); anything else rejected | `test_flash_model_sent_exactly`, `test_flash_free_spelling_preserved`, `test_unknown_clef_variant_rejected`, `test_model_allowlist_pinned` |
| Luna uses the decisions route with the proven choice shape; other types rejected | `test_luna_posts_to_decisions_with_proven_shape`, `test_luna_rejects_non_choice` |
| Panel: one judge one vote, majority wins, double tie escalates | `test_majority_wins`, `test_tie_reruns_then_decides`, `test_double_tie_escalates` |

## Quickstart

```bash
export CLEF_API_KEY=...   # your key; never committed, never logged

# Ask Clef to judge a state blob against structured questions
bin/clef-decide --state-file state.md --questions questions.json
bin/clef-decide --state-file state.md --questions questions.json --json
```

`--state-file` holds a concise state (a diff, a test summary, an iteration report) — never the whole repo. `--questions` is a JSON map of question ID to question. Answers come back by question ID. See `examples/launch-readiness/` for a worked example and `docs/question-sets.md` for the full phase-by-phase question library.

## Judges

`--judge` selects which judge drives the gate (default `clef`). All four share the one API key.

```bash
bin/clef-decide --state-file state.md --questions questions.json --judge jev
bin/clef-decide --state-file state.md --questions questions.json --model clef-flash
```

- `clef` — the full-size decision model. The thorough reader; keep it for the highest-stakes verdicts.
- `clef-flash` — the 9B variant ([model card](https://huggingface.co/Cloudflare/clef-flash)): same SystemOne wire, no free-form generation, built for speed — median request latency 38.8ms vs 209.3ms for `clef` on the Decision Index suite. Pick it for cheap, fast, high-volume gates.
- `jev` — SystemOne model `jev-latest`. The risk and adversarial judge: risk triage, second opinions, catching what the others miss.
- `luna` — the `/v1/decisions` route (model `gpt-6-luna-decisions`, fixed). Structured scored audits with rationale — the audit trail. Choice questions only; use a SystemOne judge for `noul`/`score`.

Only `clef`, `clef-flash`, and `jev-latest` (plus a `:free` suffix spelling, preserved verbatim) are accepted on the SystemOne route — anything else is rejected, since none of these are chat models. Request shape reference: the [SystemOne quickstart](https://docs.typesafe.ai/introduction/quickstart).

### Panel votes

`--panel` fans one choice question out to all four judges in parallel and applies the tribunal rule: **one judge, one vote; majority wins.** A tie re-runs once (new votes, not retried requests); a second tie escalates to the owner — the helper exits 2 and never auto-picks.

```bash
bin/clef-decide --state-file report.md --questions done.json --panel
```

`done.json` must hold exactly one choice question, e.g. `{"done": {"type": "choice", "instructions": "...", "criteria": {"done": "...", "not_done": "..."}}}`. Use the panel for the loop-termination gate (phase 6) and other high-stakes verdicts; routine gates stay single-judge.

## How a gate works

Three question types:

| Type | Judges | Example |
|------|--------|---------|
| `choice` | picks one named option | should this diff `accept` or get `review`? |
| `noul` | a proposition is true or false | "every case passes" — true or false |
| `score` | rates along an ordered scale | blast radius from "none" to "user funds at risk" |

Questions in one request are independent — never chain answers within a request. Read results with `bin/clef-decide`, which prints each decision plus reported token usage, or `--json` for the raw payload. Probabilities and confidence are estimates, not guarantees.

## The loop

1. **Discovery** — inventory every user-facing feature from the code into a sheet; gate: `coverage` (noul) until nothing is undocumented.
2. **Test generation** — gate each feature's `risk` (score); risk level sets suite depth.
3. **Execution** — run every case; failures gate `triage` (choice: real-defect / bad-test / environment-flake), then `severity` (choice).
4. **Remediation** — each defect gets a minimal proposed diff; gate `fix_review` (choice: accept / review).
5. **Regression** — re-run everything; gate `regression_clean` (noul). New failures loop back to phase 3.
6. **Recursive loop** — write the iteration report; gate `confidence` (score) and `done` (noul). If `done` is false, loop back to phase 1.

Full workflow: `docs/quality-loop.md`. If Clef doesn't approve, keep trying: re-run the stochastic verdict; if the refusal is stable, strengthen the work or the evidence and re-ask. Never bypass a failed gate silently — and never merge, ship, or call something done on a refused gate without explicit human order.

## Configuration

The key follows standard CLI practices — first source found wins:

1. `--api-key` flag (explicit per-call; prefer the options below — flags can
   leak into shell history and process listings)
2. `$CLEF_API_KEY` environment variable
3. `$EXPERIENTIAL_API_KEY` environment variable (legacy name, still honored)
4. `api_key=` in `~/.config/clef-decide/config`

```ini
# ~/.config/clef-decide/config — KEY=VALUE lines, # comments
api_key=...
# endpoint=https://...        # override the SystemOne endpoint (https:// only)
# luna_endpoint=https://...   # override the decisions endpoint (https:// only)
```

The SystemOne endpoint is likewise overridable: `--endpoint` flag → `$CLEF_ENDPOINT`
→ config file → default `https://api.experientiallabs.ai/v1/systemone`.
Luna's decisions endpoint: `--luna-endpoint` flag → `$LUNA_ENDPOINT`
→ config file → default `https://api.experientiallabs.ai/v1/decisions`.
Missing key everywhere stops the helper with setup instructions — it never
prompts, never logs.

## For agents

`SKILL.md` at the repo root is the drop-in agent skill: hand any agent the
repo URL and it can clone, configure a key, and drive the loop. It covers
the sheet format, all six phases, the question sets, and the operating
rules — everything the README and `docs/` describe, in the form agent
harnesses auto-discover.

## Hard rules (enforced in code)

- POSTs only to the configured endpoints: SystemOne (default
  `https://api.experientiallabs.ai/v1/systemone`) for clef/clef-flash/jev,
  decisions (default `https://api.experientiallabs.ai/v1/decisions`) for Luna.
  No other endpoints.
- Bearer key comes from the standard config chain above, shared by all four
  judges. Missing key stops the helper — it never prompts, never logs.
- SystemOne model is sent as `clef`, `clef-flash`, or `jev-latest` exactly
  (a `:free` suffix spelling is preserved if explicitly selected). Luna's model
  is fixed (`gpt-6-luna-decisions`). Anything else is rejected.
- **No retries, no idempotency key.** An unknown outcome may already be charged, so the helper never re-sends on its own. (A panel tie triggers one fresh vote round, not a retried request.)
- Context budget: 16,384 tokens shared by state + question definitions. Over budget is refused before sending.
- Gateway bounds: ≤32 questions per request, ≤64 options per choice, 2–10 levels per score.
- Panel: one judge one vote, majority wins, double tie escalates with exit 2.

## Testing

Fully mocked — no network, no key, no charges:

```bash
python3 -m unittest discover -s tests
```

48 tests cover request shape, key handling, context budget, gateway bounds, judge routing, the Luna decisions route, panel voting, and error surfacing. Live calls are always opt-in: ask before any potentially charged call, and never claim it worked without a real response.

## Layout

- `SKILL.md` — the drop-in agent skill (clone the URL, set a key, drive the loop).
- `bin/clef-decide` — the CLI. Python 3, stdlib only, zero dependencies.
- `docs/quality-loop.md` — the six-phase workflow in full.
- `docs/question-sets.md` — copy-paste question sets per phase, with state shapes.
- `examples/launch-readiness/` — worked example: a launch-readiness gate.
- `tests/` — the mocked test suite (`test_clef_mock.py`, `test_claims.py`, `test_config.py`, `test_judges.py`).

## License

MIT. See `LICENSE`.
