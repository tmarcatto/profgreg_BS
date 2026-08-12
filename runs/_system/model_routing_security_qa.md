Model routing QA passed: yes
Failures: 0
Warnings: 0

Config: /Users/tmarcato/prof-greg/workspace/config/model-routing.json

Findings:
- PASS config_exists: Model routing config exists.
- PASS providers_present: Providers configured: 9.
- PASS required_roles: All required role bindings are present.
- PASS provider_references: All binding provider/helper references exist.
- PASS provider_secret_fields: Providers reference env vars only; no secret fields found.
- PASS secret_literals: No secret-like literals found in routing config.
- PASS policy_flags: Policy flags require no hardcoded skill models and env-only secrets.
- PASS skills_hardcoded_models: No hardcoded model IDs found in skills.
- PASS deterministic_roles: Deterministic rendering roles route to local_deterministic.
