# Invoice review lab: credit-note linking experiment

A narrow, local Python experiment using fictional records. It is separate from the invoice review app and does not change that app's UI, database or HTTP endpoints.

## Run

Requires Python 3.10+ and no packages or network access.

    python -m unittest -v test_linking_preview

The 15 tests cover a valid link proposal, reference normalization, missing or invalid references, unknown reference, supplier and currency mismatches, an unresolved invoice resend, excessive credit, full credit, invalid input, input immutability and repeated record IDs.

`engine.py` is reused unchanged from the existing invoice-review prototype. `linking_preview.py` and its tests are new. The original 38-test suite was verified separately. This standalone repository includes the 15 linking tests, not the full web application suite.

## Scope

The function takes manually supplied fields and a manually supplied original-invoice reference. It validates records using the original prototype's field rules and fictional supplier alias map. A unique same-supplier, same-currency, normalized-reference match produces a proposal requiring review. Multiple matching invoice records remain ambiguous, including an invoice resend.

The amount shown is only invoice amount minus this one credit amount. It is not an open balance or amount payable. The experiment does not model tax, payment history, earlier credits, multiple allocations or currency conversion. It does not extract data with AI, authenticate a reviewer, save decisions, post to a ledger, or authorize payments. It intentionally makes no approval decision.

The test output is evidence about this limited fictional experiment, not production readiness or accounting correctness for real records.

## Try the fictional demo

    python demo.py

Compare its JSON output with `example-output.json`. The source is deterministic Python, not an AI model or multi-agent system.
