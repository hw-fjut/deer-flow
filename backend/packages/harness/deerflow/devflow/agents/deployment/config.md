---
name: deployment
description: Deployment Agent - generates Docker/K8s manifests and validates deployment.
history_access: frontend_design_and_testing
allowed_stages: [deployment]
tools: [file_write, file_read, code_execute, shell]
constraints: [must_produce_dockerfile, must_produce_k8s_manifests, must_include_healthcheck]
output_format: markdown
---

# Deployment Agent

Final member of the loop subgraph. Receives frontend design and the
code_testing output. Has **no** access to requirements, architecture, or
spec_development conversation history.
