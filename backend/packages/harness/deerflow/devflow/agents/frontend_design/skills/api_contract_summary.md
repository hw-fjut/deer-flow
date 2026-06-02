---
name: api_contract_summary
description: Summarise the backend API contract that the frontend relies on.
tools: [file_write, file_read, markdown_parse]
constraints: [every_endpoint_listed, error_model_uniform, version_path_prefixed]
output_format: markdown
---

# API Contract Summary Skill

## Overview
The frontend design produces a *summary* of the backend API contract. The
spec-development agent will turn this summary into the formal OpenAPI
specification. Keeping the summary in the frontend design package means the
spec/test/deploy loop has a single, short reference of the surface it has to
implement.

## Capabilities
- List every endpoint with method, path, request/response, errors
- Document the error model (status code, error code, message)
- Document the version path prefix and auth scheme

## Usage Guidelines
1. Every endpoint must be listed, even if it is not yet implemented
2. The error model is uniform across endpoints
3. Path versions are explicit (e.g. ``/api/v1/...``)
