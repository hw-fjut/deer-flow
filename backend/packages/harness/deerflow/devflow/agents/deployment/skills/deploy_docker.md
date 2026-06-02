---
name: deploy_docker
description: Docker deployment skills
tools: [file_write, docker_build, docker_run]
constraints: [use_multi_stage_build, no_root_user]
output_format: dockerfile
---

# Docker Deployment Skills

## Overview
This skill enables the Deployment Agent to create and configure Docker deployments.

## Capabilities
- Create optimized multi-stage Dockerfiles
- Configure docker-compose for multi-service deployments
- Set up health checks and readiness probes
- Configure environment variables and secrets management
- Optimize image size and layer caching

## Usage Guidelines
1. Use minimal base images (alpine, slim)
2. Never run containers as root user
3. Use .dockerignore to reduce build context
4. Pin dependency versions for reproducibility
5. Include health check endpoints
