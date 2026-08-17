Prof Greg code quality QA passed: yes
Failures: 0
Warnings: 3

Metrics:
- tool_files: 72
- non_test_tool_files: 38
- active_files_scanned: 76

Findings:
- WARN tool_file_count: Tool file count is high: 72; consider grouping commands by domain.
- WARN non_test_tool_file_count: Active non-test tool count is high: 38; consolidation would help.
- PASS course_specific_active_tools: No obvious course-specific build scripts remain in active tools.
- WARN large_files: Large active files found: [('tools/greg_live_production.py', 1171), ('tools/greg_server_status.py', 941), ('tools/greg_ui_server.py', 1781)].
- PASS root_constants: ROOT constants are consistent across 30 tools.
- PASS unsafe_runtime_patterns: No shell=True or eval/exec patterns found in active code.
- PASS hardcoded_home_paths: No hardcoded local user paths found in active code.
