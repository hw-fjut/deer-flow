---
name: spec_data_model
description: Data model specification skills
tools: [file_write, file_read, json_parse]
constraints: [follow_sql_standards, use_type_definitions]
output_format: markdown
---

# Data Model Specification Skills

## Overview
This skill enables the Spec Development Agent to design database schemas and data models.

## Capabilities
- Design relational database schemas with proper normalization
- Define entity relationships and foreign key constraints
- Create index strategies for query optimization
- Define data types and constraints for each column
- Design migration scripts for schema evolution

## Usage Guidelines
1. Always specify primary keys for all tables
2. Define audit fields (created_at, updated_at) for all entities
3. Include indexes for frequently queried columns
4. Document data lifecycle and archival strategy
