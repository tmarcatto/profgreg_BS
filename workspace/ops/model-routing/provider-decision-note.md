# Provider Decision Note

Date: 2026-07-10

## Decision

Prof Greg will use role-based model routing instead of direct provider/model calls inside skills.

The central configuration is:

```text
workspace/config/model-routing.json
```

The environment-variable reference is:

```text
workspace/config/model-routing.env.example
```

The governing contract is:

```text
workspace/contracts/model-routing-contract.md
```

## Why

The pipeline should be able to run 24/7 without depending on a human chat session.

Provider quality changes quickly. The system should be able to switch from one provider/model to another by editing one configuration file, not by rewriting course-production skills.

## Current Role Bindings

- Course architecture and technical drafting: Anthropic Claude Opus 4.8 as default for best cost/return.
- Claude Fable 5 is premium escalation only, not default, because its cost can be hard to justify for routine 24/7 production.
- Faster or cheaper models such as Claude Sonnet 5 can be used as fallback or for reviewer passes where appropriate.
- Research orchestration: OpenAI GPT reasoning model with web/file tools, plus optional academic metadata APIs.
- Review roles: intentionally separable from drafting roles.
- Diagrams: model plans the diagram, deterministic renderer builds it.
- Images: OpenAI GPT Image 2 remains the default image-generation route.
- Grok Imagine API is a cost candidate for internal visual exploration, not a default for final student-facing visuals.
- DOCX/PDF/PPTX: local deterministic production tools.

## Important Distinction

For technical diagrams, the "API" should not be an image generator by default.

Use:

```text
diagram_planning -> LLM
diagram_rendering -> deterministic SVG/PPTX/Mermaid/Graphviz
```

This keeps precision higher and prevents beautiful but technically unreliable images.

## Future Candidates To Evaluate

- Google Gemini for alternate multimodal reasoning, TTS, and low-latency workflows.
- DeepSeek for low-cost source triage, extraction, classification, glossary expansion, and first-pass draft fragments.
- Grok 4.5 for cost-aware agentic text tasks and low-risk outline/example variants.
- Grok Imagine API for low-cost image exploration, subject to stricter safety and visual QA.
- OpenAlex, Crossref, and Semantic Scholar for source discovery and citation metadata.
- Domain-specific paid sources or standards APIs if licensing allows access to construction standards, codes, or formal training material.

## Source Snapshot

Checked on 2026-07-10:

- OpenAI model and image-generation documentation.
- Anthropic model documentation.
- Google Gemini API model documentation.
- xAI model and pricing documentation.
- DeepSeek model and pricing documentation.
- OpenAlex, Crossref, and Semantic Scholar API documentation.
- Community/forum search was attempted for current cost-performance signals. No forum thread found during this pass was strong enough to override official pricing, academic benchmarks, or production QA.

## Cost Policy

Default optimization is best cost/return, not maximum raw capability.

Premium models require a reason, such as:

- repeated QA failure on a complex stage;
- unusually complex source set;
- advanced technical content that cheaper routing cannot handle;
- explicit human authorization for premium spend.

Low-cost models also require boundaries:

- use them for first-pass or low-risk work;
- never treat low-cost output as source authority;
- route final technical content through the configured technical model and reviewer gates;
- do not send sensitive/private course material to providers whose data policy has not been approved.

## Not Yet Implemented

This v0 adds the routing contract and configuration.

Actual provider adapters should be implemented through `workspace/adapters/model-router.mjs` or a production service equivalent before unattended 24/7 operation.
