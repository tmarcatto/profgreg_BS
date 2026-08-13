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
  - tool_files: 64
  - non_test_tool_files: 35
  - active_files_scanned: 68
  
  Findings:
  - PASS tool_file_count: Tool file count is manageable for v0: 64.
  - PASS non_test_tool_file_count: Active non-test tool count is acceptable: 35.
  ...
- PASS environment QA
  Prof Greg environment QA passed: yes
  Missing required keys: 0
  
  Keys:
  - OPENAI_API_KEY: set length=164 (required)
  - ANTHROPIC_API_KEY: set length=108 (required)
  - GOOGLE_API_KEY: set length=53 (optional)
  - XAI_API_KEY: set length=89 (optional)
  - DEEPSEEK_API_KEY: set length=35 (optional)
  - SEMANTIC_SCHOLAR_API_KEY: missing length=0 (optional)
  - OPENALEX_API_KEY: missing length=0 (optional)
  - OPENAI_BASE_URL: missing length=0 (optional)
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
- PASS source policy QA
  Source policy QA passed: yes
  Failures: 0
  Warnings: 0
  
  Findings:
  - PASS source_contract_academic_policy: Source contract records academic discovery policy.
  - PASS source_skill_academic_workflow: Source-ledger skill includes academic checkpoint workflow.
  - PASS model_contract_metadata_helpers: Model routing contract clarifies metadata helpers.
  - PASS routing_metadata_helpers: Routing config treats academic helpers as discovery/metadata helpers.
- PASS server operations QA
  Prof Greg server operations QA passed: yes
  Mode: local
  Root: /Users/tmarcato/prof-greg
  Failures: 0
  Warnings: 0
  
  Findings:
  - PASS ops_contract_exists: Server operations contract exists.
  - PASS ops_contract_policy_terms: Contract records backup, log, and secret-exclusion policy.
  - PASS logrotate_sample: Repository logrotate sample has required rotation policy.
  - PASS server_logrotate: Server logrotate check skipped outside server mode.
  - PASS backup_manifest: Backup manifest check skipped outside server mode.
- PASS job operator QA
  Prof Greg job operator QA passed: yes
  Jobs: 0
  Failures: 0
  Warnings: 0
  
  Findings:
  - PASS job_contract: Server job contract exists.
  - PASS job_root: Job root exists: /Users/tmarcato/prof-greg/tmp/jobs.
  - PASS job_states: No invalid job states found.
- PASS renderer reuse QA
  Renderer reuse QA passed: yes
  Failures: 0
  Warnings: 0
  
  Findings:
  - PASS scripts_found: Scanned 66 renderer/tool scripts.
  - PASS reusable_targets_present: Core reusable operator/QA targets exist.
  - PASS absolute_paths: No hardcoded local absolute paths found.
  - PASS course_tied_scripts: No course-tied scripts found outside Greg tools.
  - PASS lesson_tied_scripts: No lesson-tied scripts found.
  - PASS one_off_builders: No obvious one-off build scripts found.
  - PASS hardcoded_outputs: No hardcoded output constants found.
- PASS unit tests
  ......................................................................................................
  ----------------------------------------------------------------------
  Ran 102 tests in 0.266s
  
  OK
