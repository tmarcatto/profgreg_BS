---
name: source-ledger
description: Build and validate Prof Greg source ledgers for construction course research and citation traceability.
---

# Source Ledger Skill

Use this skill when Prof Greg needs to research, classify, validate, or document sources for a course, Course Map, study guide, visual, deck, or localization workflow.

The source ledger is an internal production artifact. It keeps Greg honest without forcing the student-facing lesson to become citation-heavy.

## Contract

Follow the source ledger contract at `workspace/contracts/source-ledger-contract.md`.

When writing files to a run folder, follow `workspace/contracts/run-folder-contract.md`.

Follow `workspace/contracts/model-routing-contract.md` for API/model use. This skill should request the `source_research` role and optional metadata helpers, not hardcoded provider/model IDs.

## Default Research Context

- Domain: U.S. construction industry.
- Audience: construction workers in the United States.
- Source language for original content: English.
- Citation style: Greg student-friendly.
- Web research: automatic when available.
- Research logging: mandatory.

## Authority Model

Primary authority is the body of knowledge of the field.

For U.S. construction courses, prioritize:

- codes and standards bodies;
- official government or regulatory sources;
- recognized industry associations;
- formal professional bodies of knowledge;
- recognized training and credentialing bodies;
- peer-reviewed or professional construction management literature;
- reputable professional textbooks and handbooks supplied by the user.

Examples include NAHB, NCCER, OSHA, ICC/code bodies, AIA, AGC, ASCE, ACI, AISC, CMAA, CSI, USACE, NIST, FHWA, FEMA, GAO, and equivalent formal authorities for the subject.

Avoid using marketing pages as technical authority when formal sources exist.
Do not confuse marketing pages with reputable practitioner education. A contractor-tech guide, trade publication, professional blog, magazine article, or moderated practitioner discussion can be useful when it teaches field workflow, common mistakes, reading sequence, or practical examples with identifiable authorship or editorial ownership. Classify these as practitioner context unless they are formal standards or published technical references.

Use academic discovery as a quality checkpoint for research-heavy or technical lessons. Semantic Scholar website/search is the default checkpoint for peer-reviewed and technical-literature signals; do not depend on a Semantic Scholar API key. Use OpenAlex and Crossref as preferred metadata APIs when available, especially for publication identity, DOI checks, author/venue metadata, and finding related academic sources. Use CORE or similar open-access indexes only when full text is needed.

Academic metadata and search results are not the final authority. For U.S. residential construction, current codes, standards, official guidance, field bodies of knowledge, and recognized professional practice outrank isolated papers when they govern the claim.

User-attached books may be used as references, following the normal source rules for metadata, relevance, authority tier, and claim mapping. If an attached document is not a published book, standard, official guidance, or identifiable formal publication, use it only as an internal content reference for scope, vocabulary, sequencing, and gap detection.

Respect the upload manifest policy for every user-attached source:

- `context_only`: use as production context only; do not list it in student-facing References and do not use its images.
- `reference_only`: it may appear in student-facing References when it passes normal source rules, but its images may not be reused.
- `reference_and_images`: it may appear in student-facing References when it passes normal source rules, and its images may be reused when the source/license context supports that use and the image is properly referenced.

If an older attachment predates the upload-policy metadata, treat it as `context_only` until the operator explicitly reclassifies it. Do not cite attachments as "course source library."

Any book or formal source published more than 3 years before the course production date needs an applicability/currentness review before it can support current claims. If it is kept only as internal background, maps to no claims, is flagged weak or replaceable, and does not appear in student-facing References, it may remain in the ledger with a warning.

## Research Order

For each research need:

1. Identify the claim, concept, standard, definition, method, statistic, or visual that needs support.
2. Classify the source need:
   - definition;
   - technical rule;
   - standard/code;
   - workflow or best practice;
   - market/statistic;
   - example/case;
   - image/visual source.
3. Choose likely authority classes before searching.
4. Search or inspect user-provided references.
5. Run an academic-discovery checkpoint when the topic is technical, practice-sensitive, research-heavy, or likely to benefit from peer-reviewed context. Search Semantic Scholar directly and use OpenAlex/Crossref metadata when useful.
6. Run a practitioner-context sweep for each lesson using queries such as "how to read [topic] construction plans", "common mistakes reading [topic] drawings", "[topic] blueprint symbols legend", and "[topic] construction drawing guide".
7. Record every meaningful search/action in `research_log`.
8. Add candidate sources to `sources`.
9. Assign an `authority_tier`.
10. Map sources to supported claims.
11. Flag weak, missing, conflicting, or overbroad sources.
12. Mark validation status.

Before drafting student-facing references, separate public/publishable sources from internal-only attachments.

Do not create hybrid references. If the source is a book, standard, recommended practice, report, manual, PDF, or other paginated publication, cite it as that publication without a URL. Use a student-facing URL only when a webpage itself was used as content input, and cite that webpage as its own source.

## Authority Tiers

Use these tiers consistently:

- `primary-body-of-knowledge`: formal body of knowledge, core credentialing material, code family, or field-defining institution.
- `formal-standard`: official code, standard, technical criterion, regulation, or authoritative manual.
- `official-guidance`: government, regulator, public agency, or recognized institution guidance.
- `peer-reviewed`: academic source with peer review.
- `professional-reference`: professional textbook, handbook, industry guide, or reputable practitioner source.
- `practice-context`: reputable practitioner article, trade publication, professional blog, or contractor-tech guide used for field language, workflow sequencing, examples, or common mistakes. Do not use this tier alone for high-stakes technical rules.
- `supplemental`: useful context, but not enough to support high-stakes technical claims by itself.

If a source does not fit any tier, either explain why it is acceptable in `reliability_notes` or do not use it.

## Source Types

Use these source types:

- `book`
- `code`
- `standard`
- `government`
- `industry-body`
- `academic`
- `professional-guide`
- `practitioner-article`
- `trade-publication`
- `dataset`
- `website`
- `image`

## Claim Mapping

Every important claim should be traceable to at least one source in the ledger, even if the lesson body does not show an inline citation.

Use concise claim summaries:

- Bad: "estimating"
- Good: "Quantity takeoff accuracy depends on reading drawings and specifications together, not measuring plans in isolation."

Use `use_type` to clarify how the source is used:

- `background`
- `definition`
- `technical-rule`
- `example`
- `statistic`
- `visual-source`

## Student-Facing Reference Style

Keep references useful and readable:

```text
[S001] Organization or Author. Title. Year. URL only if the webpage itself was used as content input; DOI/ISBN when appropriate for formal publications.
```

Do not include internal rationale in student-facing references. Avoid notes such as "why this matters", "useful for", "used to support", reliability comments, or authority-tier explanations. Keep that reasoning in the source ledger, not in the student's References page.
Do not include access dates in student-facing references. Keep access dates only in the internal source ledger.

Inline citations are optional. Use them only when they improve the learning moment, support a high-stakes technical statement, or make an important factual claim more trustworthy.

## Image and Visual Source Rules

For visuals, classify the source path:

1. `deterministic-diagram`: no external image source required, but underlying claims/data still need support.
2. `trusted-source-image`: source attribution required.
3. `generated-conceptual-image`: fallback only, must be labeled internally as generated.

Never present generated imagery as a real jobsite, real project, real person, real organization, or sourced technical figure.

## Validation Checklist

Before marking a source ledger valid:

- Every source exists or is user-provided.
- Every source has enough metadata to be found again.
- Every high-value claim has source support.
- No marketing page is used where a formal source is available.
- No invented citation remains.
- Weak sources are flagged.
- Conflicts between sources are noted.
- Image sources include attribution or generated/fallback status.
- The ledger supports student-friendly references without breaking reading flow.
- Student-facing references contain only clean bibliographic entries: no access dates, local paths, internal rationale, source-tier notes, or production comments.
- Student-facing references do not link books, standards, recommended practices, or formal publications to abstract/bookstore/catalog/landing pages.
- Internal-only, unresolved, weak, or no-claim sources do not appear in student-facing References.

Then run the source/reference checker:

```bash
python3 tools/greg_source_reference_check.py sources/source_ledger.json sources/student_references.md --production-date YYYY-MM-DD
```

Zero failures are required before the lesson can move to final DOCX/PDF production. Warnings must be reviewed and kept in the internal process review, not shown to students.

## Output Artifacts

When working in a run folder, produce:

```text
sources/source_ledger.json
sources/research_log.md
```

Optionally produce:

```text
sources/source_gaps.md
sources/student_references.md
```

## Source Ledger JSON

Use the JSON shape from `workspace/contracts/source-ledger-contract.md`.

Set:

- `validation.all_sources_verified` to `true` only after checking existence and metadata.
- `validation.unsupported_claims` for claims that still need support.
- `validation.weak_sources_to_replace` for sources that are usable only temporarily.
- `validation.review_notes` for judgment calls.

## Escalation

If a source cannot be found:

1. Replace with a supported equivalent if possible.
2. Narrow the claim.
3. Omit the claim if it is not essential.
4. Flag the issue if the claim is essential.

Do not fill gaps with confident-sounding unsourced prose.
