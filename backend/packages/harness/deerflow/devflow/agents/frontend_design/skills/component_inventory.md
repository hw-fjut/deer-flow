---
name: component_inventory
description: Catalogue the component tree (atoms / molecules / organisms) with their props contract.
tools: [file_write, file_read, markdown_parse]
constraints: [use_atomic_design_taxonomy, props_must_be_typed, no_business_logic_in_components]
output_format: markdown
---

# Component Inventory Skill

## Overview
A canonical, typed list of UI components the application needs. This is the
contract that spec-development and code-testing agents can use to detect
missing pieces (a route without components, a component without tests, ...).

## Capabilities
- Organise components in the atomic-design taxonomy (atom / molecule / organism / template)
- For each component, list props, events, slots, variants, and the page(s) using it
- Flag components that depend on async data

## Usage Guidelines
1. Every component must declare its props contract
2. No business logic inside a component - state must be lifted
3. Components must be reusable across at least one blueprint
