# Reusable Renderer Contract

Prof Greg renderers must become reusable production components, not one-off scripts tied to a single course, lesson, or local machine path.

## Purpose

Reduce drift between approved design and generated artifacts by separating:

- lesson content;
- visual plan;
- design tokens;
- renderer configuration;
- output paths;
- QA.

## Renderer Inputs

A reusable renderer should accept a run folder and lesson number, then read canonical artifacts from the run:

```text
runs/[course-slug]/
  lesson_draft/lesson_[NN]_draft.md
  review/lesson_[NN]_visual_plan.json
  deck/lesson_[NN]_visual_plan.json
  sources/student_references.md
  workspace/design-system/
  workspace/renderers/
```

Do not hardcode:

- absolute user paths;
- course slugs;
- course titles;
- lesson titles;
- lesson number `01`;
- output filenames beyond templated patterns;
- provider/model IDs.

## Allowed Renderer Configuration

Renderer scripts may define reusable defaults:

- page size;
- slide size;
- typography scale;
- BuildStak design tokens;
- component names;
- QA output naming pattern.

Course-specific values must be loaded from run artifacts or explicit CLI arguments.

## Expected CLI Pattern

Current spec-driven renderer pattern:

```text
python3 tools/greg_artifact_spec_check.py runs/[course-slug]/docx_pdf/lesson_[NN]_study_guide_spec.json
python3 tools/greg_render_study_guide_from_spec.py runs/[course-slug]/docx_pdf/lesson_[NN]_study_guide_spec.json

python3 tools/greg_artifact_spec_check.py runs/[course-slug]/deck/lesson_[NN]_deck_spec.json
python3 tools/greg_render_deck_from_spec.py runs/[course-slug]/deck/lesson_[NN]_deck_spec.json
```

Future higher-level operator pattern:

```text
python3 tools/greg_render_study_guide.py [course-slug] --lesson 1
node tools/greg_render_deck.mjs [course-slug] --lesson 1
```

The current one-off scripts may remain as historical production artifacts, but new production should prefer reusable renderers.

## Spec Gate

Every renderer spec must pass `tools/greg_artifact_spec_check.py` before rendering.

The spec gate checks:

- required fields for the artifact type;
- cache-safe revision naming such as `r02`;
- relative workspace-safe paths only;
- approved baseline artifact exists;
- revision output does not overwrite the approved baseline artifact;
- renderer-supported deck layouts or PDF visual types;
- minimum deck QA declarations for MECE, no automatic last-item highlight, and residential context;
- minimum PDF metadata, source markdown, icon, and technical-revision note.

Render wrappers must call this gate internally so server-side production cannot bypass it by accident.

## QA

Before renderer work is considered stable, run:

```text
python3 tools/greg_renderer_reuse_check.py
```

The checker reports:

- hardcoded absolute paths;
- scripts tied to specific course slugs;
- scripts tied to `lesson_01`;
- likely one-off build scripts;
- missing reusable renderer entry points.

Warnings do not block v0 historical artifacts, but they define the 3B refactor backlog.
