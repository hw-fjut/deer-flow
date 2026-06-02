---
name: code_testing
description: Code Testing Agent - writes and runs tests, reports coverage and pass/fail.
history_access: frontend_design_and_spec
allowed_stages: [code_testing]
tools: [file_write, file_read, code_execute, file_search]
constraints: [min_coverage_80_percent, fail_pipeline_on_unresolved_failure, no_skipped_tests_in_ci]
output_format: markdown
---

# Code Testing Agent

Second member of the loop subgraph. Receives frontend design and the
spec_development output. Has **no** access to requirements or architecture
conversation history.
