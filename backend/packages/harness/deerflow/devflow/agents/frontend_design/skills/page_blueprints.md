---
name: page_blueprints
description: Generate page-level blueprints: route, layout, key components, and data dependencies.
tools: [file_write, file_read, markdown_parse]
constraints: [one_blueprint_per_route, list_data_dependencies_explicitly, include_error_and_loading_states]
output_format: markdown
---

# Page Blueprints Skill

## Overview
Produce a blueprint for every route in the application. A blueprint is a
structured description that the spec-development agent can translate into
API contracts and that the testing agent can target with end-to-end tests.

## Capabilities
- Enumerate every public route and authenticated route
- For each route define: layout, key components, data dependencies,
  empty/loading/error states
- Cross-link components to the component inventory

## Usage Guidelines
1. Every blueprint must list its data dependencies by name
2. Always include the empty / loading / error UI states
3. Reference the design tokens used (do not redeclare them)
