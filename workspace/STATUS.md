# Prof Greg Development Status

Status date: 2026-08-13

## Current Stage

Prof Greg completed multiple full-flow v0/confirmation runs:

- `Construction Cost Estimating: From Takeoff to Bid` Lesson 1.
- `Construction Contract Essentials` Lesson 1.
- `Construction Schedule Management` Lessons 1, 2, and 3 as the current multi-lesson confirmation run.

The active task is now Phase 4A: server operator hardening after the GitHub repository and Hetzner server foundation were created.

Roadmap of record: `workspace/ROADMAP.md`.

Current roadmap position: Phase 4 - 24/7 Server Deployment, server foundation live but persistent public/semi-public interface not exposed.

Pre-Git/server code quality and security review was completed on 2026-08-12. GitHub/server bootstrap was completed on 2026-08-13.

## Confirmed Foundation

- Operator interface contract exists.
- Model routing contract and configuration exist.
- Course Map skill exists.
- Source ledger skill exists.
- Study-guide draft and reviewer skills exist.
- DOCX/PDF, visual QA, deck, human approval, and localization skills exist.
- Full-flow v0 test package exists.
- Construction Cost Estimating Lesson 1 completed intake, Course Map, source ledger, draft, review, PDF, approval, deck, deck approval, localization smoke test, and process review.
- Construction Schedule Management Lessons 1, 2, and 3 completed the planned multi-lesson continuity test. Lesson 2 forced cross-lesson MECE/glossary improvements; Lesson 3 confirmed continuity with approved study guide, approved deck r02, and consolidated pipeline QA with 0 failures and 0 warnings.
- Construction Schedule Management Lesson 1 now also has a reusable study-guide PDF validation revision, PDF r02, generated from `lesson_01_study_guide_spec.json`; the approved PDF artifact remains the original `lesson_01_study_guide.pdf`.
- Construction Schedule Management Lesson 1 now also has a reusable deck-renderer validation revision, deck r04, generated from `lesson_01_deck_spec.json`; the approved deck artifact remains r03.
- Artifact specs for the reusable PDF and deck renderers now pass a pre-render spec gate, and the render wrappers call that gate before producing files.
- Prof Greg now has a residential-construction-first audience anchor and a dark-background negative-logo rule.
- Blueprint Reading Course Map v3 has been promoted to the active `course_map.md`.
- Blueprint Lesson 1 curated draft/PDF is the active reference artifact for study-guide behavior.

## Current Working Decisions

- Use Course Map v3 as official for the Blueprint bench.
- Use Lesson 1 only as the active reference lesson.
- Park Lesson 2 for now.
- Do not run another final QA pass on the Blueprint bench before returning to system work.
- Continue treating v0 approvals as process approvals, not commercial-final approval.

## Open System Work

1. Refine prompts using the completed v0 and multi-lesson confirmation runs.
2. Improve study-guide and deck renderers. Started with deck components and PDF layout QA.
3. Improve visual QA and MECE deck review. Started with visual-plan QA and deck similarity checks.
4. Improve localization text-fit handling before localized PPTX rendering.
5. Improve source/reference separation and outdated-source applicability checks.
6. Improve Course Map autonomy QA so syllabus adaptation is traceable.
7. Improve study-guide content QA before rendering.
8. Improve renderer reuse readiness and archive one-off historical scripts.
9. Improve model/API routing validation.
10. Prepare Phase 3D full-flow v1 test bench and intake gate.
11. Reduce manual production steps now that the operator and canonical manifest can track a full approved English lesson package.
12. Continue converting artifact production from one-off scripts into spec-driven reusable renderers.
13. Add stricter render-aware QA for deck/PDF geometry issues.
14. Add course-level glossary and visual registries for cross-lesson MECE.
15. Prepare Git repository setup, deployment environment contract, and server integration plan.
16. Add cost/logging observability for model/API calls before 24/7 operation.
17. Add server status, backup, and log-rotation controls before exposing a persistent interface.

## Next Recommended Step

Phase 3 technical pause is complete for the planned blocks:

- Multi-lesson canonical artifacts and course status are now upgraded.
- Deck render-aware QA has been tightened for the specific failures found in Lessons 1-3.
- Course-level glossary and visual registries are now added and connected to the consolidated pipeline.
- PDF render-aware QA has been tightened.
- Lesson-level source refresh is now required and connected to consolidated lesson QA.
- Approval recording and canonical promotion automation now exist.
- A single local lifecycle action now runs source refresh, consolidated QA, and canonical manifest updates.
- Pre-server quality/security guardrails now exist: shared path guards, local security QA, code-quality QA, stricter `.gitignore`, restricted `.env.local` permissions, renderer path containment, and an online-agent security contract.
- Git/server contracts and environment setup are now in place.
- `tools/greg_server_status.py` now provides a non-destructive deployment status operator for local and server checkouts.
- Backup/log operations policy now exists and is checked through `tools/greg_server_status.py --ops-only`.
- The first backup job now exists through `tools/greg_server_status.py --create-backup`, with archive checksum and restore manifest.
- Next validate the manual backup on the live server, then add a scheduled backup timer.

Latest verification:

- Full local Greg test suite passed after backup job addition: 99 tests, 0 failures.
- Code quality QA passed: 0 failures, 0 warnings.
- Security QA passed: 0 failures, 0 warnings.
- Model routing QA passed: 0 failures, 0 warnings.

Existing operator tools:

- `tools/greg_course_status.py`
- `tools/greg_intake_check.py`
- `tools/test_greg_intake_check.py`
- `tools/greg_run_lesson.py`
- `tools/test_greg_run_lesson.py`
- `tools/greg_lesson_pipeline_qa.py`
- `tools/test_greg_lesson_pipeline_qa.py`
- `tools/greg_route_request.py`
- `tools/greg_full_flow_readiness.py`
- `tools/greg_create_run.py`
- `tools/greg_canonical_artifacts.py`
- `tools/test_greg_canonical_artifacts.py`
- `tools/greg_lesson_source_refresh_check.py`
- `tools/test_greg_lesson_source_refresh_check.py`
- `tools/greg_record_approval.py`
- `tools/test_greg_record_approval.py`
- `tools/greg_course_map_quality_check.py`
- `tools/test_greg_course_map_quality_check.py`
- `tools/greg_visual_plan_check.py`
- `tools/test_greg_visual_plan_check.py`
- `tools/greg_deck_quality_check.py`
- `tools/test_greg_deck_quality_check.py`
- `tools/greg_pdf_layout_check.py`
- `tools/test_greg_pdf_layout_check.py`
- `tools/greg_source_reference_check.py`
- `tools/test_greg_source_reference_check.py`
- `tools/greg_study_guide_content_check.py`
- `tools/test_greg_study_guide_content_check.py`
- `tools/greg_renderer_reuse_check.py`
- `tools/test_greg_renderer_reuse_check.py`
- `tools/greg_model_routing_check.py`
- `tools/test_greg_model_routing_check.py`
- `tools/greg_prepare_full_flow_test.py`
- `tools/test_greg_prepare_full_flow_test.py`
- `tools/greg_localized_deck_text_map_check.py`
- `tools/test_greg_localized_deck_text_map_check.py`
- `tools/greg_render_deck_from_spec.py`
- `tools/test_greg_render_deck_from_spec.py`
- `tools/greg_render_study_guide_from_spec.py`
- `tools/test_greg_render_study_guide_from_spec.py`
- `tools/greg_artifact_spec_check.py`
- `tools/test_greg_artifact_spec_check.py`
- `tools/greg_security.py`
- `tools/greg_security_check.py`
- `tools/greg_code_quality_check.py`
- `tools/greg_source_policy_check.py`
- `tools/greg_server_status.py`
- `tools/test_greg_security.py`
- `tools/test_greg_security_check.py`
- `tools/test_greg_code_quality_check.py`
