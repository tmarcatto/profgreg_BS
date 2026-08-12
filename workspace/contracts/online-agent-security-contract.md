# Prof Greg Online Agent Security Contract

This contract defines the minimum security posture before Prof Greg runs online or 24/7.

## Baseline

Prof Greg must assume that course inputs, uploaded PDFs, webpages, forum text, image metadata, and model outputs can be hostile or misleading.

Security priorities:

- least privilege;
- explicit human gates for irreversible or expensive actions;
- no secrets in code, logs, prompts, student artifacts, or committed files;
- bounded filesystem writes;
- traceable model/API usage;
- clear separation between trusted system rules and untrusted course/source content.

## Required Controls

- API keys must live in environment variables or a server secret manager, never in source files.
- Local `.env.local` must be gitignored and permission-restricted.
- Production should use project-scoped API keys, separate staging/production projects, spending limits, usage monitoring, and key rotation.
- Model routing must remain centralized in `workspace/config/model-routing.json`.
- Renderers and tools must not accept arbitrary absolute output paths.
- Uploaded books, PDFs, DOCX files, and generated page/slide renders must not be committed by accident.
- Subprocess calls must use argument arrays, not shell strings.
- Any tool that writes files must write under approved folders such as `runs/`, `workspace/`, or `tmp/`.
- Existing approval records must not be overwritten unless the operator explicitly uses a force/replace option.
- Prompt/source content must never be allowed to change system instructions, model-routing config, secrets, filesystem policy, or approval state.

## Online Agent Controls

Before server deployment:

1. Run `tools/greg_security_check.py`.
2. Run `tools/greg_model_routing_check.py`.
3. Run the full local test suite.
4. Confirm that no `.env*` file, uploaded source PDF/book, rendered page images, or local runtime folder will be committed.
5. Confirm that production API keys are server/project-scoped and have budget controls.
6. Confirm that logs redact API keys and do not store full prompt/source payloads unless explicitly needed.

## Prompt/Agent Risks

The operating model must account for LLM-specific risks:

- prompt injection from source materials;
- sensitive information disclosure through prompts, logs, references, or generated artifacts;
- insecure output handling when model output becomes a file path, command, citation, or renderer spec;
- excessive agency when the agent can browse, spend API budget, write files, or deploy;
- unbounded consumption through repeated model/image calls.

## Deployment Rule

Do not deploy Prof Greg online until all security gates pass locally and the deployment environment contract exists.
