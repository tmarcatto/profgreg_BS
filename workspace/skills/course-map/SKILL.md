---
name: course-map
description: Create and QA a Prof Greg course map from a syllabus and trusted construction knowledge sources.
---

# Course Map Skill

Use this skill when the user wants Prof Greg to turn a syllabus, course idea, outline, or reference set into the macro plan for a course.

The Course Map is the first real gate in Prof Greg. No study guide, deck, localization, or visual production should begin until the Course Map exists and has passed QA.

## Defaults

- Audience: residential construction workers and construction-career learners in the United States.
- Default sector focus: residential construction first. Light commercial or large commercial examples are allowed only when they clarify a concept, but they must not become the default scenario.
- Learner representation: the U.S. residential construction workforce includes American-born workers and immigrant workers. Course examples, scenarios, and visual planning should reflect that workforce without stereotyping.
- Source language: English.
- Course levels: Basic, Intermediate, Advanced.
- Length is adaptive by course level and function:
  - Basic: roughly 10 pages per lesson downstream.
  - Intermediate: roughly 15 pages per lesson downstream.
  - Advanced: roughly 15 pages per lesson downstream, with higher technicality.
- Form follows function. Do not preserve lesson count, section count, or page goals when they harm learning.

## Inputs

Accept whatever the user provides, but look for:

- syllabus or rough course outline;
- course level: Basic, Intermediate, or Advanced;
- reference books, standards, PDFs, links, or source folders;
- intended course title, if any;
- required lesson count, if any;
- special constraints, if any.

If the course level is missing, infer a likely level from the syllabus and state the assumption. If the assumption is risky, flag it in QA.

## Syllabus Interpretation Rule

Treat the user-provided syllabus as an initial direction, not as a fixed contract.

Before approving the Course Map, Greg must evaluate whether the syllabus should be kept, renamed, reordered, merged, split, expanded, narrowed, or reframed based on:

- target learner and course level;
- current market/job demands;
- body of knowledge and source coverage;
- relevance to practical residential construction work in the United States;
- redundancy, missing prerequisites, or weak sequencing;
- user-provided books and formal source material.

Greg may approve the Course Map autonomously even when it changes the syllabus, but it must clearly report what changed and why.

If the syllabus is strong and Greg keeps it mostly intact, Greg must still say that it was evaluated and preserved, with rationale.

## Authority Model

Primary authority is the body of knowledge of the field, not generic web research.

For U.S. construction courses, prefer relevant authorities such as NAHB, NCCER, OSHA, ICC/code bodies, AIA, AGC, ASCE, ACI, AISC, CMAA, CSI, USACE, NIST, FHWA, FEMA, GAO, recognized professional texts, and peer-reviewed or professional construction management sources.

User-provided published books with identifiable records may be used as references, following normal source rules for metadata, relevance, authority tier, and claim mapping. They are important inputs, but they do not automatically outrank stronger standards, codes, official guidance, or formal bodies of knowledge.

User-provided attachments that are not published books, standards, official guidance, or identifiable formal publications should be marked internal-only in the Course Map and source needs. They can shape the course, but they are not student-facing references and not image sources.

The Course Map must also identify practitioner-context source opportunities for each lesson. These are not the primary technical authority, but they are required for field relevance: contractor-tech guides, trade publications, professional blogs, magazine articles, and practitioner forums that reveal common reading workflows, mistakes, and field language.

Image-heavy lessons must include a visual-source gate. Images must be unique inside each lesson and must teach a specific concept. If the available visual source base is weak, blocked, repetitive, or not licensable, mark the lesson as `visual_curation_required` instead of filling the lesson with repeated images, generated substitutes, weak visuals, or images from internal-only attachments.

Use the source ledger contract at `workspace/contracts/source-ledger-contract.md` for traceability.

Use the run folder contract at `workspace/contracts/run-folder-contract.md` when writing artifacts to disk.

Use the model routing contract at `workspace/contracts/model-routing-contract.md`. This skill should request the `course_architect` role, not a hardcoded provider/model.

## Autonomy

Greg may approve the Course Map autonomously after QA.

Greg has total autonomy to change lesson count when the syllabus is weak, overloaded, underdeveloped, redundant, or missequenced. When changing lesson count, include a concise rationale that traces the decision back to learning progression, audience, level, and source coverage.

Greg also has autonomy to change lesson titles, lesson emphasis, lesson order, lesson scope, and lesson-level terminology when research shows the syllabus needs adaptation. These changes do not require human approval, but they must be visible in the Course Map and adaptation log.

## Output Artifacts

Produce two aligned artifacts:

1. `course_map.md`: human-readable Course Map.
2. `course_map.json`: machine-readable Course Map for downstream skills.
3. `syllabus_adaptation_log.md`: what Greg kept, changed, or flagged from the input syllabus.
4. `course_map_qa.md`: autonomous QA confirming the Course Map can advance.

When working in a run folder, place them under:

```text
course_map/course_map.md
course_map/course_map.json
course_map/syllabus_adaptation_log.md
course_map/course_map_qa.md
```

## Course Map Markdown Structure

Use this structure:

```markdown
# Course Map: [Course Title]

## 1. Course Header

- Course name:
- Course tagline:
- Target audience:
- Course level:
- Estimated lesson count:
- Source language:
- Market context:

## 2. Course Level and Scope Rationale

[Explain why the course level and lesson count fit the syllabus and learner.]

## 3. Overall Narrative Arc

[Explain the learning journey from Lesson 1 to final lesson.]

## 4. Syllabus Adaptation Log

| Input item | Decision | Course Map result | Rationale |
|---|---|---|---|

## 5. Lesson Map Summary Table

| # | Lesson Title | Key Concept | Builds On | Prepares For |
|---|---|---|---|---|

## 6. Per-Lesson Detail

### Lesson 1: [Title]

- Subtitle/tagline:
- Key concept:
- Learning objectives:
- Topics covered:
- Suggested MECE section structure:
- Key terms introduced:
- Acronyms expanded:
- Concepts assumed from prior lessons:
- Concepts this lesson sets up:
- Suggested hands-on example:
- Likely source needs:
- Practitioner-context source opportunities:
- Visual opportunities:

## 7. Key Term Ownership Map

| Term | Home Lesson | Notes |
|---|---:|---|

## 8. Acronym Expansion Map

| Acronym | Full Name | First Expanded In | Notes |
|---|---|---:|---|

## 9. Source Needs by Lesson

| Lesson | Source Needs | Likely Authorities |
|---:|---|---|

## 10. QA and Approval

- MECE progression:
- Audience fit:
- Level fit:
- Syllabus adaptation:
- Lesson count rationale:
- Source coverage risks:
- Redundancy risks:
- Missing prerequisites:
- Approval status:
```

## Course Map JSON Shape

Use this high-level shape:

```json
{
  "course": {
    "title": "string",
    "tagline": "string",
    "target_audience": "construction workers in the United States",
    "level": "Basic | Intermediate | Advanced",
    "source_language": "English",
    "market_context": "United States construction industry",
    "lesson_count": 10,
    "lesson_count_rationale": "string",
    "narrative_arc": "string"
  },
  "syllabus_adaptation": [
    {
      "input_item": "string",
      "decision": "kept | renamed | reframed | reordered | merged | split | added | removed | flagged",
      "course_map_result": "string",
      "rationale": "string"
    }
  ],
  "lessons": [
    {
      "number": 1,
      "title": "string",
      "subtitle": "string",
      "key_concept": "string",
      "learning_objectives": ["string"],
      "topics_covered": "string",
      "mece_sections": [
        {
          "section_number": 1,
          "title": "string",
          "scope": "string"
        }
      ],
      "key_terms_introduced": ["string"],
      "acronyms_expanded": [
        {
          "acronym": "string",
          "full_name": "string",
          "learner_explanation": "string"
        }
      ],
      "prior_concepts": ["string"],
      "future_bridges": ["string"],
      "suggested_hands_on_example": "string",
      "likely_source_needs": ["string"],
      "visual_opportunities": ["string"],
      "visual_source_status": "sufficient | visual_curation_required",
      "image_request_needs": ["string"]
    }
  ],
  "term_ownership": [
    {
      "term": "string",
      "home_lesson": 1,
      "notes": "string"
    }
  ],
  "acronym_map": [
    {
      "acronym": "string",
      "full_name": "string",
      "first_expanded_lesson": 1,
      "notes": "string"
    }
  ],
  "source_needs_by_lesson": [
    {
      "lesson": 1,
      "needs": ["string"],
      "likely_authorities": ["string"]
    }
  ],
  "qa": {
    "mece_progression_passed": false,
    "audience_fit_passed": false,
    "level_fit_passed": false,
    "syllabus_adaptation_passed": false,
    "lesson_count_rationale_passed": false,
    "source_coverage_risks": [],
    "visual_source_risks": [],
    "redundancy_risks": [],
    "missing_prerequisites": [],
    "approval_status": "approved | needs_revision"
  }
}
```

## QA Checklist

Before approving a Course Map, check:

- The course has a clear beginning, middle, and end.
- Lesson sequence builds from simpler to more complex concepts.
- Every lesson has a distinct key concept.
- Lesson sections are MECE at the macro level.
- Key terms have one home lesson.
- Acronyms are expanded once, at the right moment.
- CALLBACK and BRIDGE opportunities are real, not invented.
- Lesson count fits the syllabus, level, and learner.
- Source needs are identified before drafting.
- Visual opportunities are paired with a visual-source status: sufficient or visual_curation_required.
- No image is repeated inside a lesson to fill space.
- If image sourcing is weak, the Course Map requires a human image-curation request package before final approval.
- No lesson is a junk drawer for unrelated topics.
- No course promise depends on unsupported or vague sources.

Then run:

```bash
python3 tools/greg_course_map_quality_check.py course_map/course_map.json course_map/course_map.md course_map/syllabus_adaptation_log.md --intake input/intake.md
```

The checker must pass before Course Map approval can route to source-ledger production. It verifies that the syllabus was treated as initial direction, adaptation or preservation rationale is traceable, lesson count rationale is documented, U.S. construction audience/level are explicit, source/authority basis is recorded, practitioner-context opportunities are present, and autonomous approval is captured.

## Callout Planning Guidance

The Course Map may suggest callout opportunities, but it should not overload lessons with callouts.

Current callout vocabulary:

- `APPLY IT`
- `KEY TERM`
- `HANDS-ON EXAMPLE`
- `SCENARIO`
- `CALLBACK`
- `BRIDGE`

Use callouts only when they improve learning, practical application, emphasis, or continuity. If a callout would merely repeat the body text, do not recommend it.

## Output Standard

The final Course Map should be confident, traceable, and easy for downstream skills to use. It should not read like a brainstorming note. It is the operating blueprint for the course.
