# Invoice autopilot: orchestrated end-to-end prototype

Next step after `live-agent-demo`. That version ran three fixed stages in a
fixed order. This version processes a whole fictional inbox end to end: an
OrchestratorAgent freely chooses its tools and delegates to specialist agents
(extraction, validation, settlement), and CODE, never the model, decides
whether the case auto-completes or pauses for human review.

Python standard library only. Default model `openai/gpt-oss-20b` on Groq's
OpenAI-compatible API.

## What is new versus live-agent-demo

- Batch inbox of five fictional documents (was: one fixed invoice + credit pair).
- Fictional supplier registry check and duplicate detection (against the batch
  and a fictional open-invoice ledger). Neither existed before.
- Simulated settlement: passed invoices net of passed credits, computed by
  code with Decimal math. Still no ledger writes and no payments.
- Orchestration: the model picks tools and order; specialists run as
  delegations. Agents do not negotiate with each other; code arbitrates every
  outcome. This is still not an MCP/A2A/autonomous-negotiation system.
- Auto-complete path: when every deterministic check passes, the case
  completes WITHOUT human review. Any failed check routes the case to human
  review with code-computed reasons.
- `execute_payment` is a listed tool that always refuses, so a model call
  demonstrably cannot move money. Every attempt is recorded in the trace.

## Safety invariants (enforced by code, not the model)

- Extraction fields require verbatim source quotes; fabricated quotes are
  rejected.
- Validation verdicts are recomputed by `validate_extracted`; the model only
  gathers evidence through check tools.
- The settlement proposal must equal the code-computed Decimal result exactly
  or it is rejected.
- `finalize_case` recomputes all blockers and refuses while anything failed
  or is missing. Missing steps ("not ready") are distinguished from failed
  checks ("needs a human") because a live run showed the model conflating them.
- `submit_result` requires a decided case and all documents processed.
- Global request cap, per-agent turn caps, bounded corrective retries only for
  API-rejected invalid model output (tool_use_failed / output_parse_failed).
  Rate limits and all other errors stop the run.

## Verified on November 23, 2026

- Ten offline tests pass using a scripted transport. They are not live-model
  proof. (`offline-tests.txt`)
- One complete LIVE run on the small inbox (one fictional invoice INV-2001 for
  INR 15000.00 plus one fictional credit note CN-201 for INR 3000.00):
  `autopilot-live-small.json`. 21 requests, 11600 reported tokens. The live
  orchestrator chose a correct order (extract all, validate all, settle,
  finalize) and the case auto-completed with net 12000.00. One corrective
  retry was consumed for invalid model output. The model's narrative report
  wrote "12,000.00" with a comma; it is stored as unverified text, while the
  code-computed settlement preserves exact strings.
- Five preserved FAILED live runs (`failures-live-*.json`): two died on the
  model inventing a `check_invoice_number` tool, one on unparseable provider
  output, one hit the free-plan 8000 TPM limit one step before finishing, and
  the first "successful" run actually misrouted a clean case to human review
  after calling finalize before settlement. These failures drove the
  corrective-retry, error-wording and ordering fixes above. They are failures,
  not successful demonstrations.
- The full five-document inbox (duplicate, unknown supplier, currency
  mismatch) is covered by offline tests only; no live full-inbox run yet
  (request/token budget and pacing still being worked out).

## Scope limits

Fictional text documents only. No real inbox, email or file ingestion, no OCR
or PDF parsing, no real supplier data, no accounting-system writes, no
payments. The registry and ledger are hardcoded fiction. One successful live
run on one fictional pair does not establish general accuracy, safety, or
production readiness.

## Running locally

Use a Groq key from a private file, never committed. Verify the account's
current billing plan first.

```sh
python -m unittest -v test_autopilot
python autopilot.py --key-file /private/path/to/key --confirm-free-plan \
    --inbox small --pace-seconds 5 --output live-result.json
```

`--inbox full` runs the five-document case (needs a higher request budget and
roughly 5 seconds per request of pacing to stay under the free plan's
8000 tokens/minute). Stop on rate limits; do not upgrade to finish a demo.
