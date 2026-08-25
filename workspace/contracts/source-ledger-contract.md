# Source Ledger Contract

Prof Greg uses a source ledger to make research traceable without making the student-facing lesson feel citation-heavy.

## Purpose

The source ledger records what sources were used, why they were trusted, which claims or concepts they support, and where they entered the course. It is an internal production artifact and a quality guardrail.

## Core Rules

- Never invent a source, statistic, quote, standard, organization, or image attribution.
- Prefer the field's body of knowledge over generic web results.
- For U.S. construction courses, prioritize relevant authorities such as NAHB, NCCER, OSHA, ICC/code bodies, AIA, AGC, ASCE, ACI, AISC, CMAA, CSI, USACE, NIST, FHWA, FEMA, GAO, and recognized academic or professional construction management sources.
- Academic discovery is required for research-heavy or technical lessons, but academic search tools are discovery aids, not final authority. Use Semantic Scholar website/search as a default checkpoint for peer-reviewed and technical literature signals. Use OpenAlex and Crossref as preferred metadata APIs for source discovery, DOI validation, citation metadata, and publication identity. CORE or similar open-access indexes may be used when full-text availability is needed.
- For U.S. residential construction, academic papers should support or sharpen the content, but they must not outrank current codes, standards, official guidance, field bodies of knowledge, or recognized professional practice when those are the governing authority.
- Source books and user-provided references are important, but they do not automatically outrank stronger domain authorities, codes, standards, or official bodies of knowledge.
- User-attached files classified as `reference_only` or `reference_and_images` must be materially used, entered in the source ledger, mapped to supported claims, and included once in student-facing References. They supplement rather than replace current external research. Older publications still require an applicability review against current authorities; a failed validation blocks production instead of silently omitting the attachment. Internal-only attachments may guide content, but must not appear in student-facing References and must not be used as image sources.
- Published books and formal uploaded sources can become student-facing references when metadata supports them, but age matters. Any book or formal source published more than 3 years before the course production date must receive an applicability review before being used as a source. If the claim may be affected by newer research, technology, regulations, codes, standards, methods, market practice, safety guidance, pricing, software, contract forms, or professional consensus, Greg must validate it against current formal sources before using it to support current claims.
- For construction law and contract-management topics, older books may support enduring concepts and vocabulary, but they must not be treated as current authority for legal rights, enforceability, standard contract forms, dispute procedures, notice requirements, lien/payment rules, or jurisdiction-specific obligations without current validation.
- Time-sensitive validation must be logged in `sources/research_log.md` and summarized in `sources/source_gaps.md` or `sources/source_policy_v1.md` when relevant. If current validation is unavailable, downgrade the source to background context or omit the claim.
- Visual sources must be unique within a lesson. Do not repeat the same image, crop, or lightly annotated version to fill multiple figure slots unless the lesson explicitly teaches comparison between views of the same image and the user has approved that choice.
- If a lesson needs real instructional images and the production pass cannot find enough strong, relevant, licensable images, do not invent images, use weak images, reuse images, or use internal attachments. Mark the lesson as `visual_curation_required`, build a didactic draft with explicit image-request placeholders, and create a human image-curation request document.
- Every human image-curation request document must include one English, keyword-focused Google-search phrase for each requested image.
- In the `visual_curation_required` stage, the human reviewer receives the draft plus the image request document. If all requested images are found, Greg inserts them and sends the lesson for approval. If only some images are found, Greg must redesign the lesson around the images that are actually available before sending it for approval.
- Web research is automatic when available, but every run must keep a research log.
- Do not use marketing pages as primary technical authority when formal sources exist.
- Do include reputable practitioner education sources when they improve field relevance: contractor-tech guides, trade publications, professional blogs, magazine articles, and moderated practitioner communities. These sources are for workflow language, common mistakes, practical sequencing, and examples unless independently supported by formal authority.
- If a claim cannot be supported, omit it, replace it with a supportable claim, or flag it as unresolved.
- Student-facing references should be useful and readable, not decorative.
- Student-facing references must be clean bibliographic entries only. Do not include internal rationale such as "useful for", "used to support", source ranking, reliability notes, or production comments.
- Student-facing references must never say "Retrieved from Prof Greg course source library," expose internal source folders, or show local course file paths.
- Student-facing references must be real in their presented form. If a book, standard, recommended practice, report, manual, PDF, or other paginated publication was used, cite it with formal bibliographic metadata and do not display a URL. If a webpage was separately used as content, cite that webpage as its own source.
- Student-facing webpage links are allowed only when the webpage itself was used as content input. Do not cite a book or standard and then send students to an abstract, catalog page, bookstore page, landing page, or teaser page as if it were the source content.
- Do not name sources in the study-guide teaching prose. Use the source name only in figure captions/source legends and in the References section.
- Boxes, callouts, and figure caption groups must never split across pages. If a box does not fit, move the whole box to the next page.

## Source Ledger JSON Shape

Each run should produce `source_ledger.json` with this shape:

```json
{
  "course_id": "string",
  "course_title": "string",
  "run_id": "string",
  "created_at": "YYYY-MM-DD",
  "research_policy": {
    "web_research": "automatic",
    "citation_style": "greg-student-friendly",
    "reading_flow_priority": true,
    "academic_discovery": {
      "semantic_scholar_checkpoint": true,
      "metadata_apis": ["openalex", "crossref"],
      "full_text_indexes_optional": ["core"],
      "final_authority": "domain-body-of-knowledge"
    }
  },
  "sources": [
    {
      "source_id": "S001",
      "title": "string",
      "author_or_organization": "string",
      "source_type": "book | code | standard | government | industry-body | academic | professional-guide | practitioner-article | trade-publication | dataset | website | image",
      "authority_tier": "primary-body-of-knowledge | formal-standard | official-guidance | peer-reviewed | professional-reference | practice-context | supplemental",
      "reliability_notes": "string",
      "url": "string or null",
      "doi": "string or null",
      "isbn": "string or null",
      "file_path": "string or null",
      "publication_date": "string or null",
      "access_date": "YYYY-MM-DD or null",
      "currency_validation": {
        "required": true,
        "status": "validated-current | validated-concept-only | not-required | unresolved",
        "validated_against": ["source_id or URL"],
        "notes": "string"
      },
      "claims_supported": [
        {
          "claim_id": "C001",
          "claim_summary": "string",
          "lesson_numbers": [1],
          "section_ids": ["1.2"],
          "use_type": "background | definition | technical-rule | example | statistic | visual-source"
        }
      ],
      "limitations": "string"
    }
  ],
  "research_log": [
    {
      "step": 1,
      "query_or_action": "string",
      "reason": "string",
      "result_summary": "string"
    }
  ],
  "validation": {
    "all_sources_verified": false,
    "unsupported_claims": [],
    "weak_sources_to_replace": [],
    "review_notes": []
  }
}
```

## Student-Facing Reference Style

Use Greg student-friendly references:

- readable organization or author;
- plain title;
- year when it is part of the publication metadata;
- URL only when the webpage itself was used as content input;
- DOI or ISBN when appropriate for books, standards, recommended practices, and formal publications;
- no local file references in student-facing references.
- do not include access dates in student-facing references; keep access dates only in the internal source ledger.
- do not include local file paths in student-facing references; keep local file paths only in the internal source ledger.

Inline citations are not mandatory for every claim. Use inline citation only when it strengthens the learning moment, highlights an important factual claim, or helps the learner trust a high-stakes technical statement.

## Source/Reference QA

Each lesson run must validate the internal source ledger against the student-facing reference list before DOCX/PDF finalization.

Each lesson must also create a lesson-level source refresh record before the lesson is considered clean. The Course Map and course-level ledger give direction, but the lesson refresh confirms that the specific lesson's sources, current-claim validation, and known gaps still support that lesson.

Required lesson refresh files:

```text
sources/lesson_[NN]_source_refresh.json
sources/lesson_[NN]_source_refresh_qa.md
```

The refresh record must review every ledger source mapped to that lesson. It must mark `status` as `completed`, mark `current_claim_validation` as `completed`, and leave no unresolved gaps unless the gap is explicitly `resolved`, `accepted-v0`, or `deferred-not-used`.

Run:

```bash
python3 tools/greg_source_reference_check.py sources/source_ledger.json sources/student_references.md --production-date YYYY-MM-DD
```

Run lesson-level refresh QA:

```bash
python3 tools/greg_lesson_source_refresh_check.py [course-slug] --lesson [NN] --output runs/[course-slug]/sources/lesson_[NN]_source_refresh_qa.md
```

The QA must fail when:

- the source ledger or student-facing references are missing;
- required source metadata is missing;
- a book or formal source more than 3 years old supports current claims without applicability/currentness review;
- an unresolved source is not flagged as weak, internal, or replaceable;
- student-facing references include access dates, local paths, internal rationale, source-tier notes, or production comments;
- student-facing references present books, standards, recommended practices, or formal publications with links to abstracts, bookstore pages, catalog pages, landing pages, or teaser pages instead of citing them as publications;
- internal-only or ineligible sources appear in student-facing References;
- unsupported claims remain.
- a lesson-level source refresh record is missing, incomplete, or does not review every ledger source mapped to that lesson.

The QA may warn, without blocking, when an older unresolved source is internal-only, supports no claims, is flagged as weak, and does not appear in student-facing References. This warning means Greg may keep the source as background context, but must not use it as student-facing authority.

## Image Source Rules

- Technical or real-world images need source attribution.
- Generated conceptual images must be labeled internally as generated and should be used only as fallback.
- Prefer deterministic diagrams over generated images when precision matters.
- Prefer trusted technical/source-based images over generated conceptual imagery when a real source is pedagogically better.
