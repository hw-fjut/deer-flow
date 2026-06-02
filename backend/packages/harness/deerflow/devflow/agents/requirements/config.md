---
name: requirements
description: Requirements Analysis Agent - produces a combined PRD + architecture document. The frontend_design agent consumes this artifact.
history_access: full
allowed_stages: [requirements]
tools: [file_write, file_read, web_search]
constraints: [must_include_acceptance_criteria, prioritize_using_MoSCoW, must_include_architecture]
output_format: markdown
---

# Requirements Analysis Agent

The first and only linear "head" stage of the pipeline (besides
``frontend_design``). Architecture has been merged into this stage because
the two concerns are tightly coupled.

## Inputs
- User task (free-form)
- Conversation history

## Outputs
- ``PRD.md`` - personas, MoSCoW priority, acceptance criteria
- ``ARCHITECTURE.md`` - stack, components, API design, deployment topology
- Both are written into a single combined markdown body for the next stage.

## History access policy
Full access. This is the only stage allowed to look at the original user
request and conversation history.
