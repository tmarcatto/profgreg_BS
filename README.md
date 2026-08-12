# Prof Greg

Prof Greg is the local production pipeline for BuildStak learning materials.

The repository keeps the durable system pieces:

- agent identity, contracts, skills, and design-system rules;
- reusable PDF and deck renderers;
- model-routing configuration examples;
- QA tools and automated checks;
- central process QA reports.

The repository does not track local secrets, OpenClaw/runtime installs, generated course outputs, user-supplied source files, local caches, or API smoke-test logs.

## Local Checks

Run these before committing meaningful changes:

```bash
python3 tools/greg_security_check.py --output runs/_system/security_qa.md
python3 tools/greg_code_quality_check.py --output runs/_system/code_quality_qa.md
PYTHONPYCACHEPREFIX=/private/tmp/prof-greg-pycache python3 -m unittest discover -s tools -p 'test_greg_*.py'
```

## Configuration

Copy `workspace/config/model-routing.env.example` into a local `.env.local` file and fill in provider keys locally. Do not commit `.env.local`.
