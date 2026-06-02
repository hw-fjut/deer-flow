---
name: design_tokens
description: Define the visual design tokens (colors, typography, spacing, motion) that the rest of the frontend consumes.
tools: [file_write, file_read, markdown_parse]
constraints: [no_inline_hex_outside_tokens, follow_design_system_naming, use_4px_base_grid]
output_format: markdown
---

# Design Tokens Skill

## Overview
The Frontend Design Agent uses this skill to emit a single source-of-truth
``design_tokens.md`` describing the visual language of the project.

## Capabilities
- Define a color palette (brand + neutral + semantic) with WCAG AA contrast notes
- Define typography scale (font families, sizes, weights, line heights)
- Define spacing, radius, and elevation scales
- Define motion (duration curves, allowed easing tokens)
- Map every primitive to a CSS variable / Tailwind token name

## Usage Guidelines
1. Tokens must be the only place where raw hex / px values appear
2. The output must be importable by the chosen UI framework
3. Mark deprecated tokens explicitly so the spec/test loop can detect drift
