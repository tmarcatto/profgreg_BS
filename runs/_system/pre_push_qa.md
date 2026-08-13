Prof Greg pre-push QA passed: yes
Failures: 0

Steps:
- PASS security QA
  Prof Greg security QA passed: yes
  Failures: 0
  Warnings: 0
  
  Findings:
  - PASS gitignore_sensitive_paths: Git ignore covers local secrets, runtime, caches, and uploaded PDFs.
  - PASS env_file_permissions: .env.local permissions are restricted: 600.
  - PASS no_shell_true: No shell=True usage found in active Greg code.
  - PASS no_eval_exec: No eval/exec usage found in active Greg code.
  - PASS no_secret_literals: No secret-like literals found in active Greg code/config.
  - PASS unguarded_output_paths: CLI output paths use the shared safe-write guard.
  - PASS security_relevant_contracts: Security-relevant operating contracts exist.
- PASS code quality QA
  Prof Greg code quality QA passed: yes
  Failures: 0
  Warnings: 0
  
  Metrics:
  - tool_files: 58
  - non_test_tool_files: 32
  - active_files_scanned: 62
  
  Findings:
  - PASS tool_file_count: Tool file count is manageable for v0: 58.
  - PASS non_test_tool_file_count: Active non-test tool count is acceptable: 32.
  ...
- PASS model routing QA
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
  ...
- PASS renderer reuse QA
  Renderer reuse QA passed: yes
  Failures: 0
  Warnings: 0
  
  Findings:
  - PASS scripts_found: Scanned 60 renderer/tool scripts.
  - PASS reusable_targets_present: Core reusable operator/QA targets exist.
  - PASS absolute_paths: No hardcoded local absolute paths found.
  - PASS course_tied_scripts: No course-tied scripts found outside Greg tools.
  - PASS lesson_tied_scripts: No lesson-tied scripts found.
  - PASS one_off_builders: No obvious one-off build scripts found.
  - PASS hardcoded_outputs: No hardcoded output constants found.
- PASS unit tests
  ........................................................................................
  ----------------------------------------------------------------------
  Ran 88 tests in 0.931s
  
  OK
