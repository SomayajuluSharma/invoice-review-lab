# Invoice review: real model experiment

Independent learning prototype using Groq's OpenAI-compatible API and Python's standard library. The default model is `openai/gpt-oss-20b`.

## Scope

Three model-backed stages run sequentially:

1. ExtractionAgent calls a document-reading function and proposes fields with source quotes.
2. ReferenceAgent calls a deterministic reference check using those extracted records.
3. ExceptionSummaryAgent reads a review packet and returns an explanation.

Code controls the stage order and which tool is available at each stage. This is an orchestrated tool-using workflow, not autonomous agent negotiation, MCP, A2A or Strands. The model supplies the tool arguments and extracted values. Code checks document IDs, output shape, source-text substrings, exact supplier text, currency and reference equality. Source-text agreement does not authenticate the document or supplier.

Only two fictional text fixtures are supported: invoice INV-1042 for INR 10000.00 and credit note CN-88 for INR 2000.00 referencing that invoice. No OCR, PDF reading, supplier registry, ledger, outstanding-balance calculation or payment function exists.

## Verified on November 22, 2026

- Nine offline tests pass using an explicitly scripted model transport. They are not live-model proof.
- Two complete real-model runs succeeded on GPT-OSS20B. Each made seven requests and exercised all three stages. Reported token usage: 3918 and 3920 respectively.
- Both complete runs extracted the fixture fields with matching source quotes. All five exact reference checks returned true. Human review remained required and payment authorization remained false.
- A real-model currency-mismatch trial extracted USD for the credit and INR for the invoice. Its reference check returned `currency_equal=false` and `proposal_supported=false`. The next request reached a free-plan rate limit, so the full mismatch workflow did NOT complete. It is stored as a failed/partial run.
- Earlier attempts failed at HTTP access, record shape, document ID, provider output parsing, or free-plan limits. These are failures, not successful demonstrations. Preserved failures are included separately.

The summary prose is explicitly unverified model output. In both complete runs it changed ASCII hyphens in document numbers to typographic hyphens. Do not use it as the canonical document identifier. The structured extracted values preserve the originals. Two successful runs on one fictional pair do not establish general accuracy, safety, or production readiness.

## Running locally

Use a Groq key from a private file, never committed. Verify the account's current billing plan first. The confirmation flag records a manual check, it does not detect billing.

```sh
python -m unittest -v test_agent_demo
python agent_demo.py --key-file /private/path/to/key --confirm-free-plan --output live-result.json
```

The client permits at most twelve requests per run, at most 1400 completion tokens per request, and four turns per stage. It does not automatically retry on errors. These are execution bounds, not spend authorization or a guaranteed cost cap. Stop on rate limits rather than upgrading or repeatedly retrying.

## Evidence

- `invoice-agent-oss20-live.json`: first complete live run.
- `invoice-agent-repeat-live.json`: second complete live run.
- `invoice-agent-currency-mismatch-live.json`: partial negative trial, rate-limited after reference validation.
- `failures/`: preserved earlier unsuccessful traces. Some earliest attempts have no complete trace or usage accounting.
- `offline-tests.txt`: current nine-test result.

This directory was published on November 23, 2026 alongside the Day 68 post. The repository's earlier rules-only invoice code is a different project version and does not contain these model-backed stages. One provider organization identifier in the preserved error traces has been redacted.
