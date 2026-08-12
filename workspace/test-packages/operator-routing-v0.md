# Operator Routing V0 Test Matrix

Status date: 2026-08-08

Use this matrix when changing `tools/greg_route_request.py` or `workspace/contracts/operator-routing-contract.md`.

## Current Blueprint Bench Assumption

- Course Map exists.
- Lesson 1 reference draft/PDF exists.
- Approval file does not exist.
- Lesson 2 is parked.

## Expected Routes

| Human request | Expected intent | Expected stage | Allowed now | Reason |
|---|---:|---:|---:|---|
| `segue` | `status` | current run stage | yes | Continuation should check status first. |
| `onde estamos?` | `status` | current run stage | yes | Status request. |
| `gere a Lesson 1` | `study_guide` | `DRAFT` | yes | Lesson generation request. |
| `rode os revisores da Lesson 1` | `review` | `REVIEW` | yes | Reviewer request should not be swallowed by `Lesson`. |
| `prepare o pdf da Lesson 1` | `docx_pdf` | `DOCX_PDF` | yes | PDF request should not be swallowed by `Lesson`. |
| `gera o deck da Lesson 1` | `approval` | `HUMAN_APPROVAL` | no | Deck is gated by approval file. |
| `localize para pt-br` | `approval` | `HUMAN_APPROVAL` | no | Localization depends on approved English artifact. |
| `aprovo a apostila da Lesson 1 e autorizo gerar o deck` | `approval` | `HUMAN_APPROVAL` | yes | Approval should be captured before routing to deck. |

## Notes

Gate-sensitive intents should have higher priority than generic lesson language:

1. approval;
2. deck;
3. localization;
4. review;
5. docx/pdf;
6. study guide.
