# Prof Greg Model Routing Contract

This contract prevents Prof Greg skills from hardcoding model providers, model IDs, or API-specific behavior.

Skills must ask for a capability role. The router decides which provider and model currently serves that role.

## Core Rule

No skill should call a provider directly.

Use capability roles such as:

- `course_architect`
- `source_research`
- `technical_content`
- `pedagogy_review`
- `citation_review`
- `design_review`
- `visual_planning`
- `diagram_planning`
- `diagram_rendering`
- `image_generation`
- `pptx_generation`
- `docx_pdf_generation`
- `localization`
- `localization_review`

The current provider/model binding lives in:

```text
workspace/config/model-routing.json
```

## Configuration Layers

Use three layers:

1. `roles`: what Prof Greg is trying to do.
2. `providers`: available APIs or local engines.
3. `bindings`: which provider/model currently handles each role.

Skills may mention the role they need, but not the provider/model ID.

## Secret Handling

Secrets must not be stored in this repo.

Provider bindings point to environment variable names only, such as:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
```

Use:

```text
workspace/config/model-routing.env.example
```

as the non-secret reference.

## Role Guidelines

### Course Map

Use `course_architect`.

This role needs strong reasoning, curriculum architecture, source-awareness, and long-context handling.

### Technical Study Guides

Use `technical_content`.

This role needs strong technical writing, construction-domain precision, and source-led discipline.

### Reviewer Roles

Use the specific review role:

- `pedagogy_review`
- `citation_review`
- `design_review`
- `localization_review`

Reviewer roles should be able to disagree with the drafter. Do not route drafter and reviewer to the same model when independent review is important and budget allows.

### Diagrams

Use two separate roles:

- `diagram_planning`: reasoning about what the diagram should teach.
- `diagram_rendering`: deterministic rendering through SVG, PPTX shapes, Mermaid, Graphviz, or equivalent code-native tools.

Do not use image generation for precise technical diagrams unless explicitly marked as conceptual fallback.

### Images

Use `image_generation`.

Generated conceptual images are fallback for student-facing artifacts. Prefer deterministic diagrams and trusted technical images when precision matters.

### Research

Use `source_research` for web/source discovery and metadata enrichment.

Research output must still go through the source ledger. Search APIs do not replace source validation.

Academic discovery tools are helpers, not authority layers. Use Semantic Scholar website/search as a default checkpoint for peer-reviewed and technical-literature signals. Use OpenAlex and Crossref as preferred metadata APIs for publication identity, DOI validation, and citation metadata. Do not require a Semantic Scholar API key for the normal Greg workflow.

For U.S. residential construction, formal bodies of knowledge, current codes, standards, official guidance, and recognized professional practice outrank isolated academic papers when they govern the claim.

## Observability

Every production run should log:

- role requested;
- provider selected;
- model selected;
- reason for selection;
- fallback used, if any;
- source/research calls, when relevant.

The recommended run-level log path is:

```text
runs/[course-slug]/ops/model_usage_log.jsonl
```

## Fallback Rules

If a preferred provider is unavailable:

1. Use the configured fallback for the same role.
2. Log the fallback.
3. If the fallback would materially reduce quality, mark the stage as `needs_review`.
4. Never silently switch from deterministic diagram rendering to generated images.

## Updating Models

When a better model or provider becomes available, update:

```text
workspace/config/model-routing.json
```

Do not edit individual skills for model changes unless a new capability role is needed.
