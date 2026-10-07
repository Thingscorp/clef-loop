# Checkout service launch-readiness (example state)

Test summary: staging deploy of the checkout service, 14 cases executed.
12 passed. 2 failures under review. No production action taken.

Open items:
1. Idempotency keys on POST /orders are accepted but never stored —
   double-submit protection is unproven against retry storms.
2. Webhook signature verification rejects valid signatures when the
   provider rotates keys (stale key cache, TTL 24h, no forced refresh).
3. Load test covers 2x peak traffic; 5x headroom target not yet run.

Passing: happy-path order flow, refund flow, card-decline handling,
inventory decrement under concurrency (50 parallel), tax calculation
for 12 jurisdictions, receipt email rendering, admin dashboard filters,
rate limiting at 100 rps, schema migrations up/down, audit log
completeness, PII redaction in logs.
