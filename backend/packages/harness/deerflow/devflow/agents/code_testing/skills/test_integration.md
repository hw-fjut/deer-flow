---
name: test_integration
description: Integration testing skills
tools: [file_write, file_read, code_execute, docker_run]
constraints: [use_test_database, cleanup_after_tests]
output_format: python_test
---

# Integration Testing Skills

## Overview
This skill enables the Code Testing Agent to write and execute integration tests.

## Capabilities
- Test API endpoints with real database connections
- Verify data flow between services and components
- Test authentication and authorization flows
- Validate request/response serialization
- Test concurrent access patterns

## Usage Guidelines
1. Use a dedicated test database (never production)
2. Clean up test data after each test suite
3. Use fixtures for common test data setup
4. Test happy path first, then error scenarios
5. Verify database state changes after operations
