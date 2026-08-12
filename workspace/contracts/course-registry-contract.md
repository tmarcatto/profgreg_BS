# Course Registry Contract

This contract defines the course-level glossary and visual registry used by Prof Greg.

## Purpose

The registry gives Greg course memory across lessons.

It records:

- glossary home lessons;
- study-guide visuals;
- deck visuals;
- visual titles and learning claims;
- repeated visual structures that require explicit MECE justification.

The registry is an internal quality artifact, not student-facing material.

## Required Outputs

Each multi-lesson run should maintain:

```text
process_review/course_registry.json
process_review/course_registry.md
process_review/course_registry_qa.md
```

Generate and validate with:

```text
tools/greg_course_registry.py [course-slug] --write --output process_review/course_registry_qa.md
```

## Glossary Rules

- Each glossary term should have one home lesson.
- Later lessons should not redefine terms whose home lesson is earlier.
- Later lessons may use short callbacks or reminders for earlier terms.
- Acronym variants should normalize to the same home term when appropriate.

## Visual Rules

- Visual titles and visual IDs must be unique across the course.
- Visual learning claims must be unique across the course.
- Repeated visual structures require explicit justification.
- A repeated structure may be acceptable only when the teaching function differs clearly, such as taxonomy versus checklist, comparison versus process, or concept map versus decision frame.
- Visual registry warnings must be resolved or justified before new lesson approval.

## Pipeline Rule

The consolidated lesson pipeline must include the course registry gate after cross-lesson MECE:

```text
course_registry
```

This gate supports cross-lesson MECE but does not replace lesson-specific visual-plan QA.
