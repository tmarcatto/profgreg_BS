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
