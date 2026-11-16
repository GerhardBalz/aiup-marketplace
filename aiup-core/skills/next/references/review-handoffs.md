<!--
Copyright 2025-2026 Simon Martinelli and the AI Unified Process contributors.
Part of the AI Unified Process — https://unifiedprocess.ai
Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
-->

# Delivered specification reviews

A review receipt retains a delivered verdict and the handoff that follows from it. The use case status
records the product owner's approval decision.

## Ownership and invocation

For a single-UC review, the `spec-review` caller locates this `next` package through the skill
catalog or `**/*next/SKILL.md`. Read any earlier receipt and retained report first for the Repeated Runs comparison,
including human accepted/declined findings. Use fresh report/result filenames for each delivered
review so earlier evidence is preserved. Then begin the new attempt:

```text
python -B <next-folder>/scripts/review_handoff.py begin UC-002 --workspace .
```

This replaces `.aiup/reviews/UC-002.json`, clearing any earlier delivered-review handoff. Keep the receipt
and retained evidence as local workflow files.
It leaves implementation/test records, specifications and statuses unchanged. A failed or
interrupted review stays pending. Whole-project/TC reviews, trace, impact and HTML generation
retain their existing behavior; this extension handles only a single use case.

After presenting the complete review, retain its unchanged full report under `.local/spec-review/`
and a JSON result with the exact lint exit code, readiness verdict and findings. Then run:

```text
python -B <next-folder>/scripts/review_handoff.py report UC-002 --workspace . --result <retained-result.json> --summary "Review delivered; BR-003 needs clarification" --evidence <retained-full-report.md>
```

The caller owns these metadata writes. The semantic reviewer still does not fix findings or edit
any specification, status, open question or lint baseline. If the helper is absent or fails,
report the limitation and name the original correction handoff; do not manufacture delivery.
An earlier delivered report may be retained only after checking its reviewed documents still
match the original scope/evidence. A conversational completion claim or clean lint alone is insufficient.

## Result JSON

```json
{
  "lint_exit_code": 0,
  "ready_for_approval": false,
  "findings": [{
    "kind": "semantic",
    "severity": "warning",
    "disposition": "open",
    "file": "docs/use_cases/UC-002-borrow-book.md",
    "line": 121,
    "element": "UC-002 BR-003",
    "code": "Ambiguity",
    "message": "Clarify whether the last available copy can be borrowed.",
    "owner": "use-case-spec",
    "target": "UC-002"
  }]
}
```

Retain every finding, preserving `kind` (`lint`/`semantic`), severity, file/line/element,
code/check label and message. Semantic severity is `warning` or `info`, never `error`.
`disposition` is `open`, `accepted` or `declined`; the latter two apply only to semantic
findings and require an additional `decision` string citing the actual human decision.
The caller must not accept/decline findings on its own. Lint baseline acceptance remains
the existing separately authorized procedure, not a receipt disposition.

Use the report's readiness verdict: lint exits 0, no semantic warning remains open and no
applicable Open/Answered blocking question remains. Info findings do not request rework.
An unfinished review or lint usage/execution error cannot be recorded as delivered. An
explicit not-ready verdict needs a correction finding; it cannot silently advance.

The caller assigns the existing correction owner from `spec-review`'s After the Report table:

| Owner | Target | Resulting handoff |
|---|---|---|
| `use-case-spec` | existing `UC-XXX` | `/use-case-spec UC-XXX` |
| `use-case-diagram`, `requirements`, `entity-model` | empty string | the named skill |
| `open-questions` | `OQ-XXX`, or empty for malformed log | `/open-questions answer OQ-XXX`, or `/open-questions` |
| `test-case` | `TC-XXX` or empty | `/test-case` with the target when supplied |
| `architecture-decision` | `ADR-XXX` or empty | the named skill with the target |
| `business-process` | `BP-XXX` or empty | the named skill with the target |

Only these owner/target combinations form commands; report text is never executed or parsed
as a command. For lint, `code` is the unchanged lint code. The JSON and full report are separate
retained files, and both hashes are checked. The record is an explicit caller report, not a
signed attestation or proof that every semantic judgment is correct.

## Navigation and freshness

For Draft/Reviewed use cases, a current not-ready review selects its unresolved error/warning
correction handoffs instead of repeating review. Whole-project lint counts are unchanged.
Only exact lint errors named in a current report can replace the generic review handoff with
their correction owner; unmatched errors and blocking-question gates still apply first.
Existing lifecycle/catalog reconciliation and construction ordering remain in place.

A current ready review selects **Approval decision for UC-XXX**: a human action, not an
executable skill command. The product owner decides whether to authorize Approved status.
The navigator never approves or edits a status. It does not offer new polishing work for
info-only or human-accepted/declined findings.

Review inputs include specifications (also cross-use-case rules), requirements, entity models,
glossary, diagrams/processes, ADRs, stack and lint baseline. Applicable questions are scoped to the use case
or its linked requirements. An unrelated question does not invalidate this review. Application source/tests are not review inputs. Changes in reviewed documents,
missing/replaced result/report evidence, malformed metadata or a new review attempt require
review again. Changes between `begin` and `report` reject delivery rather than refresh its digest.
`/next` only reads; it never repairs or migrates receipts.
