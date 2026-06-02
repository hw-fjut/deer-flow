---
name: deploy_kubernetes
description: Kubernetes deployment skills
tools: [file_write, kubectl_apply, helm_template]
constraints: [use_resource_limits, configure_health_probes]
output_format: yaml
---

# Kubernetes Deployment Skills

## Overview
This skill enables the Deployment Agent to configure Kubernetes deployments.

## Capabilities
- Create Kubernetes manifests (Deployment, Service, Ingress)
- Configure resource limits and requests
- Set up liveness and readiness probes
- Configure horizontal pod autoscaling
- Set up persistent volume claims

## Usage Guidelines
1. Always set resource requests and limits
2. Use ConfigMaps for non-sensitive configuration
3. Use Secrets for sensitive data
4. Configure proper health probes
5. Use rolling update strategy for zero-downtime deployments
