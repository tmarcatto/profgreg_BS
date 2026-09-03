Prof Greg code quality QA passed: yes
Failures: 0
Warnings: 3

Metrics:
- tool_files: 82
- non_test_tool_files: 42
- active_files_scanned: 86

Findings:
- WARN tool_file_count: Tool file count is high: 82; consider grouping commands by domain.
- WARN non_test_tool_file_count: Active non-test tool count is high: 42; consolidation would help.
- PASS course_specific_active_tools: No obvious course-specific build scripts remain in active tools.
- WARN large_files: Large active files found: [('tools/greg_live_production.py', 3297), ('tools/greg_server_status.py', 1269), ('tools/greg_ui_server.py', 2697), ('workspace/renderers/pdf/greg-buildstak-study-guide-renderer.py', 1544)].
- PASS root_constants: ROOT constants are consistent across 33 tools.
- PASS unsafe_runtime_patterns: No shell=True or eval/exec patterns found in active code.
- PASS hardcoded_home_paths: No hardcoded local user paths found in active code.
