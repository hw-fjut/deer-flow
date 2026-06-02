---
name: routing_and_state
description: Define the routing tree, navigation guards, and the global state store layout.
tools: [file_write, file_read, markdown_parse]
constraints: [one_state_store_per_domain, guards_must_be_explicit, no_direct_api_calls_from_components]
output_format: markdown
---

# Routing & State Skill

## Overview
Specify the client-side routing tree and the boundaries of the global state
store. The spec/test/deploy loop will use this to decide which API endpoints
to implement first.

## Capabilities
- Define route tree with layouts and lazy chunks
- Define navigation guards (auth, role, feature flag)
- Define state slices per domain (auth, user, billing, ...)
- Define how a component reaches the API (store actions, not direct fetch)

## Usage Guidelines
1. One state slice per business domain
2. Navigation guards listed in priority order
3. Component-to-API access must go through the store
