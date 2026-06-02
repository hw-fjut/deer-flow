---
name: architecture_design
description: Author the architecture document (stack, components, API design, deployment topology).
tools: [file_write, file_read, markdown_parse]
constraints: [must_include_components, must_include_api_style, must_include_deployment_topology]
output_format: markdown
---

# Architecture Design Skill

## Overview
Turn the PRD into a technical architecture document. This is the *how*.

## Capabilities
- Pick a technology stack and justify it
- Draw the component diagram (logical, not physical)
- Define the API style (REST/GraphQL/gRPC)
- Define the deployment topology
- List the key non-functional trade-offs

## Usage Guidelines
1. Every architecture decision must cite the PRD requirement that motivates it
2. Avoid prematurely committing to specific library versions
3. Call out any decisions that need human input (suitable for Type-1 escalation)
