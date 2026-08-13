Prof Greg server operations QA passed: yes
Mode: local
Root: /Users/tmarcato/prof-greg
Failures: 0
Warnings: 0

Findings:
- PASS ops_contract_exists: Server operations contract exists.
- PASS ops_contract_policy_terms: Contract records backup, log, and secret-exclusion policy.
- PASS logrotate_sample: Repository logrotate sample has required rotation policy.
- PASS backup_service_sample: Repository backup service has required least-privilege policy.
- PASS backup_timer_sample: Repository backup timer has required schedule policy.
- PASS worker_service_sample: Repository worker service has required least-privilege policy.
- PASS ui_service_sample: Repository private UI service has required least-privilege policy.
- PASS server_logrotate: Server logrotate check skipped outside server mode.
- PASS backup_manifest: Backup manifest check skipped outside server mode.
