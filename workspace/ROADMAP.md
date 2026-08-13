# Prof Greg Roadmap

Status date: 2026-08-13

This roadmap updates the original Prof Greg plan after the Blueprint Reading bench.

## Mission

Prof Greg is an autonomous course-production agent for construction education.

Core flow:

1. Receive syllabus, course level, and reference material.
2. Produce a Course Map.
3. Build source ledger and research log.
4. Draft the English study guide.
5. Run reviewer passes.
6. Produce DOCX/PDF student guide.
7. Wait for human approval before deck generation.
8. Produce English PPTX deck.
9. Localize approved material to PT-BR and ES-419.
10. Review the full run and improve the system.

## Phase 0 - Local Bench

Status: mostly complete.

Goal: create the isolated local home for Prof Greg and make the agent real inside the OpenClaw structure.

Done:

- Created `/Users/tmarcato/prof-greg`.
- Cloned OpenClaw under `openclaw/`.
- Installed local OpenClaw runtime under `runtime/`.
- Created isolated OpenClaw home under `home/`.
- Created isolated workspace under `workspace/`.
- Created OpenClaw workspace files: `SOUL.md`, `AGENTS.md`, `TOOLS.md`, `BOOTSTRAP.md`, `IDENTITY.md`, `USER.md`, and `HEARTBEAT.md`.
- Created initial contracts, skills, design system, model routing, and test package.

Still needed:

- Replace the generic starter `SOUL.md` with Prof Greg's true identity once the operating model is stable.
- Add a simple startup checklist for future sessions.

## Phase 1 - Greg System Core

Status: v0 ready for full-flow test.

Goal: make the local Greg pipeline coherent, traceable, and repeatable before server deployment.

Done:

- Created operator interface contract.
- Created operator routing contract.
- Created run-folder contract.
- Created model-routing contract and config.
- Created source-ledger, study-guide, review, DOCX/PDF, deck, human-approval, design, visual QA, and localization contracts/skills.
- Created a full-flow v0 test checklist.
- Created `tools/greg_course_status.py` to summarize course/run status from files.
- Created `tools/greg_route_request.py` to classify human requests and enforce basic gates.
- Created `workspace/contracts/stage-execution-contract.md` to define stage inputs, outputs, gates, and next stages.
- Created `tools/greg_full_flow_readiness.py` to check whether the system is ready for a fresh full-flow v0 test.
- Created `tools/greg_create_run.py` to create normalized run folders for new courses.
- Promoted Blueprint Course Map v3 as official bench artifact.
- Promoted Blueprint Lesson 1 curated draft/PDF as active study-guide reference.
- Parked Lesson 2 artifacts.

Still needed:

- Validate stage execution on fresh material.
- Add process-level QA that checks source use, image usefulness, layout, and gate status during and after the fresh full-flow v0 test.

## Phase 2 - Full-Flow V0 Test

Status: completed twice; confirmation run complete.

Goal: run the whole pipeline with fresh material to prove Greg works beyond one course and to verify that the updated contracts prevent repeated visual/layout failures.

Required test:

- Intake.
- Course Map.
- Sources.
- Lesson 1 study guide.
- Reviewer passes.
- DOCX/PDF.
- Human approval record.
- English deck.
- PT-BR and ES-419 localization smoke tests.
- Process review.

Exit condition:

- The system can produce one complete lesson package with traceable sources, controlled gates, and documented limitations.

Completed tests:

- `Construction Cost Estimating: From Takeoff to Bid` Lesson 1.
- Produced Course Map, source ledger, English study guide PDF, human approval record, English deck, deck approval, PT-BR/ES-419 localization smoke tests, and full-flow process review.
- `Construction Contract Essentials` Lesson 1.
- Produced Course Map, source ledger, English study guide PDF, human approval record, English deck revision r03, deck approval, PT-BR/ES-419 localization smoke tests, and internal process review.
- Final v0 decision: proceed to Phase 3 refinement.
- `Construction Schedule Management` Lessons 1, 2, and 3.
- Produced Course Map, source ledger, English study guide PDFs, human approval records, English decks, deck approvals, visual plans, and consolidated pipeline QA. Lesson 2 established stricter cross-lesson MECE and glossary discipline. Lesson 3 served as the planned continuity test and passed consolidated pipeline QA with 0 failures and 0 warnings after approved visual corrections. This run also established the residential-construction-first audience anchor and dark-background negative-logo rule.

## Phase 3 - Prompt, Renderer, and Design Refinement

Status: active; technical pause after the Construction Schedule Management Lesson 3 continuity test is complete.

Goal: improve quality after we see the full pipeline run end to end.

Planned work:

- Refine prompts using golden examples.
- Improve source-search policy by discipline.
- Improve visual selection and image QA.
- Improve DOCX/PDF rendering consistency.
- Improve PPTX production and slide QA. Started with reusable BuildStak deck components and `tools/greg_deck_quality_check.py`.
- Improve localization style and terminology handling.

Phase 3 progress:

- Created `workspace/renderers/deck/buildstak-deck-components.md`.
- Created `tools/greg_deck_quality_check.py`.
- Connected deck components and deck QA tool to `deck-production-contract.md`.
- Connected deck components and deck QA tool to `deck-producer`.
- Updated `greg_course_status.py` to avoid Blueprint-specific artifact assumptions.
- Updated `greg_full_flow_readiness.py` for Phase 3 readiness.
- Added slide text similarity and nearby slide-function checks to `tools/greg_deck_quality_check.py`.
- Added unit tests for deck QA similarity/classification behavior in `tools/test_greg_deck_quality_check.py`.
- Verified the approved Construction Contract Essentials deck r03 passes the new deck QA with no warnings.
- Created `tools/greg_pdf_layout_check.py`.
- Added unit tests for PDF layout QA behavior in `tools/test_greg_pdf_layout_check.py`.
- Connected PDF layout QA to `docx-pdf-production-contract.md` and `docx-pdf-producer`.
- Verified the approved Construction Contract Essentials study guide PDF passes the new PDF layout QA with no warnings.
- Created `workspace/contracts/canonical-artifacts-contract.md`.
- Created `tools/greg_canonical_artifacts.py`.
- Added unit tests for canonical artifact manifest behavior in `tools/test_greg_canonical_artifacts.py`.
- Generated canonical manifests for `construction-contract-essentials`.
- Updated `greg_course_status.py` and `greg-operator` to use `canonical_artifacts.json`.
- Created `tools/greg_localized_deck_text_map_check.py`.
- Added unit tests for localized deck text-map QA in `tools/test_greg_localized_deck_text_map_check.py`.
- Connected localized deck fit gate to `localization-production-contract.md` and `localization-producer`.
- Created PT-BR and ES-419 localized deck fit plans for Construction Contract Essentials.
- Added residential-construction-first audience anchoring across Course Map, study guide, DOCX/PDF, deck, visual QA, and design-system rules.
- Added visual QA checks for residential context and respectful U.S. workforce representation when visuals depict people.
- Added negative BuildStak wordmark asset and dark-background logo rule.
- Updated deck QA to treat the negative wordmark as brand imagery for image-cadence checks.
- Improved canonical artifact selection so revisioned decks such as `lesson_01_deck_r03.pptx` are preferred over canonical copies.
- Regenerated the `construction-schedule-management` canonical manifest with the approved study guide and deck artifacts.
- Added reusable BuildStak deck renderer at `workspace/renderers/deck/greg-buildstak-deck-renderer.mjs`.
- Added deck spec support with `runs/construction-schedule-management/deck/lesson_01_deck_spec.json`.
- Added `tools/greg_render_deck_from_spec.py` so decks can be rendered from a JSON spec without one-off scripts.
- Rendered `construction-schedule-management` deck r04 as a technical validation of the reusable renderer; the approved artifact remains r03.
- Verified the reusable-rendered r04 deck with deck QA: 0 failures and 0 warnings.
- Added reusable BuildStak study-guide PDF renderer at `workspace/renderers/pdf/greg-buildstak-study-guide-renderer.py`.
- Added study-guide PDF spec support with `runs/construction-schedule-management/docx_pdf/lesson_01_study_guide_spec.json`.
- Added `tools/greg_render_study_guide_from_spec.py` so study-guide PDFs can be rendered from a JSON spec without one-off scripts.
- Rendered `construction-schedule-management` PDF r02 as a technical validation of the reusable renderer; the approved artifact remains the original `lesson_01_study_guide.pdf`.
- Verified the reusable-rendered r02 PDF with PDF layout QA and visual page inspection: 0 failures and 0 warnings.
- Added `tools/greg_artifact_spec_check.py` as a pre-render gate for deck and study-guide PDF specs.
- Added artifact-spec QA reports for the Construction Schedule Management deck and PDF specs.
- Updated deck and PDF render wrappers so invalid specs fail before rendering.
- Produced Construction Schedule Management Lessons 2 and 3 using the refined pipeline.
- Confirmed that Lesson 3 completed the planned multi-lesson continuity test with approved study guide, approved deck r02, and consolidated pipeline QA passing with 0 failures and 0 warnings.
- Created `runs/construction-schedule-management/process_review/technical_pause_after_lesson_03.md`.

Phase 3 technical-pause findings:

- Canonical artifacts were Lesson-1-centric; manifest version 2 now supports multi-lesson artifact records.
- Canonical artifact selection now distinguishes approved student-facing artifacts from renderer-validation revisions when approval records exist.
- Course status reporting now summarizes every produced lesson and approval state.
- Deck render-aware QA is stricter for visual geometry, footer clearance, text-box density, mixed visual modes, repeated slide functions, and arbitrary highlights. PDF layout QA is stricter for sparse body pages, orphan headings, section openings, callout continuity, figure cadence, and figure-caption/spec alignment.
- Cross-lesson MECE now includes a course-level glossary registry and visual registry.
- Source refresh now runs at lesson level, not only Course Map level.
- Approval recording now updates canonical artifacts automatically.
- The local lesson operator now has a standard `lifecycle` action that refreshes lesson sources, runs consolidated lesson QA, and updates the canonical manifest.
- Pre-server quality/security review added shared path guards, renderer path containment, approval overwrite protection, tighter `.gitignore`, restricted local secret-file permissions, recurring security QA, and recurring code-quality QA.
- Full local Greg test suite passed after pre-server quality/security review: 86 tests, 0 failures.
- Code quality QA passed with 0 failures and 0 warnings.
- Security QA passed with 0 failures and 0 warnings.

## Phase 4 - 24/7 Server Deployment

Status: server foundation live; persistent online interface not exposed yet.

Goal: move Prof Greg from local bench to a secure always-on environment.

Original plan:

- Hetzner server.
- SSH key isolation.
- Firewall and least privilege.
- Secrets outside code.
- Docker deployment.
- 24/7 runtime.

Preparation completed:

- Created the GitHub repository `tmarcatto/profgreg_BS`.
- Initialized the local Git repository.
- Published the first clean commit to `main`.
- Added Git repository rules and generated-artifact exclusion rules.
- Added the deployment environment contract.
- Added a pre-push QA command that runs security QA, code quality QA, model-routing QA, renderer-reuse QA, and unit tests.
- Created the Hetzner CPX12 server `profgreg`.
- Created dedicated Prof Greg SSH key and local ignored secret storage.
- Configured baseline SSH hardening and firewall.
- Created least-privilege runtime user `profgreg`.
- Installed Python, Node, Git, LibreOffice, Poppler, and font tooling.
- Cloned `tmarcatto/profgreg_BS` into `/opt/profgreg/app`.
- Added deploy-safe QA mode so server checks do not dirty the Git checkout.
- Server deploy-safe QA passed with 88 tests and 0 failures.
- Server dry-run course creation passed without dirtying the Git checkout.
- Created server-only `/etc/profgreg/profgreg.env` placeholder with restricted permissions.
- Installed and validated `profgreg-healthcheck.service` as a safe `systemd` oneshot check.
- Confirmed systemd healthcheck passes deploy-safe QA without dirtying the Git checkout.
- Validated server-loaded provider secrets without printing values.
- Ran minimal API smoke tests for OpenAI, Anthropic, DeepSeek, xAI, and local deterministic routing.
- API smoke tests passed, including a minimal OpenAI `gpt-image-2` image-generation validation.
- Added server backup/log operations checks, manual backup manifest generation, job-state readiness, and scheduled backup timer policy files.
- Installed and validated `profgreg-backup.timer` and `profgreg-backup.service` on the live server with a successful scheduled backup run.
- Added `tools/greg_server_status.py` as a non-destructive local/server deployment status operator.
- Added server-status unit tests and local status report generation.
- Added `workspace/contracts/server-operations-contract.md` for backup and log operations policy.
- Added `workspace/ops/logrotate-profgreg.conf` and connected backup/log readiness checks to `tools/greg_server_status.py --ops-only`.
- Added the first backup job through `tools/greg_server_status.py --create-backup`, with archive checksum and restore manifest.
- Added `workspace/contracts/server-job-contract.md` and job-state operations in `tools/greg_server_status.py --jobs-only`.

Updated rule:

Do not deploy Greg 24/7 until the local full-flow v0 test has produced a successful process review. Deploying before the pipeline is coherent would only make the wrong thing run faster.

## Current Position

Phase 1 is v0 ready, Phase 2 has completed multiple full-flow runs, Phase 3 consolidation has produced reusable renderers and stronger QA, and Phase 4 server foundation is live.

The Cost Estimating, Construction Contract Essentials, and Construction Schedule Management runs proved the pipeline across multiple course areas. They also exposed system-level weaknesses in visual QA, deck MECE review, artifact cache handling, source/reference separation, localized slide fit, and server readiness. These are now mostly converted into contracts, reusable renderers, and QA tools.

## Next Best Step

Proceed to Phase 4A server operator hardening:

1. Keep server status and deploy-safe QA passing from `main`.
2. Install backup root and logrotate config on the live server.
3. Validate the first manual backup on the live server, then add a scheduled backup timer.
4. Install `/srv/profgreg/jobs` on the live server and validate a no-op job lifecycle.
5. Then run a fresh full-flow v1 test from the operator path.

### Phase 3B Started - Renderer Reuse

- Added `workspace/contracts/reusable-renderer-contract.md`.
- Added `tools/greg_renderer_reuse_check.py`.
- Added reusable deck renderer and deck-spec wrapper for BuildStak PPTX output.
- Added reusable study-guide PDF renderer and PDF-spec wrapper for BuildStak student-guide output.
- Added artifact-spec validation as a required pre-render gate.
- Historical one-off build scripts were moved to `tools/legacy/one_offs/`.
- Current renderer reuse audit passes with zero warnings on the active tool surface.

### Phase 3C Started - Model/API Routing Validation

- Added `tools/greg_model_routing_check.py`.
- The checker validates required roles, provider references, env-only secrets, no secret literals, no hardcoded model IDs in skills, and local deterministic routing for rendering roles.
- Current model routing QA passes with zero warnings.

### Phase 3D Started - Second Full-Flow Test Bench

- Added `workspace/test-packages/full-flow-v1/`.
- Added `tools/greg_prepare_full_flow_test.py`.
- Added `tools/greg_intake_check.py` so a template intake does not advance to Course Map.
- Prepared `runs/phase-3d-full-flow-v1-bench` as an empty from-zero test slot. It correctly remains at `INTAKE` until real course content is supplied.

### Phase 3A Started - Local Operator

- Added `tools/greg_run_lesson.py` as the local lesson operator.
- The operator infers the current stage, gate status, blockers, active artifacts, optional pipeline QA, and next safe command.
- Added `--action lifecycle` to run lesson source refresh, consolidated pipeline QA, and canonical manifest promotion in one safe local command.
- Current run `construction-contract-essentials` reports `FULL_FLOW_CONFIRMATION_COMPLETE`.
- Current run `construction-schedule-management` reports `FULL_FLOW_CONFIRMATION_COMPLETE` with active deck artifact `deck/lesson_01_deck_r03.pptx`.
