---
name: test_unit
description: Unit testing skills
tools: [file_write, file_read, code_execute]
constraints: [use_pytest_framework, minimum_80_percent_coverage]
output_format: python_test
---

# Unit Testing Skills

## Overview
This skill enables the Code Testing Agent to write and execute unit tests.

## Capabilities
- Write unit tests using pytest framework
- Mock external dependencies and services
- Test individual functions and methods in isolation
- Verify edge cases and boundary conditions
- Generate test coverage reports

## Usage Guidelines
1. Follow AAA pattern (Arrange, Act, Assert)
2. Use descriptive test names that explain the scenario
3. Test both happy path and error conditions
4. Mock all external dependencies (DB, API, file system)
5. Maintain minimum 80% code coverage
