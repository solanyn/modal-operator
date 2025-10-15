# Kubernetes Development Rules

## Helm Charts
- **Structure**: Follow standard Helm chart structure in `charts/` directory
- **Values**: Use `values.yaml` for configuration with sensible defaults
- **Templates**: Keep templates simple and readable
- **Validation**: Use `helm lint` and `helm template` for validation
- **Testing**: Include chart tests in `templates/tests/`
- **Documentation**: Document all values in `values.yaml` with comments

## CRD Generation
- **Source**: Generate CRDs from Go structs or OpenAPI schemas
- **Validation**: Include comprehensive validation schemas
- **Versioning**: Use proper API versioning (v1alpha1, v1beta1, v1)
- **Storage**: Mark one version as storage version
- **Conversion**: Implement conversion webhooks for version changes
- **Documentation**: Include examples and field descriptions

## Operators
- **Controllers**: Use "Controller" suffix for components that reconcile resources
- **Reconcilers**: Follow controller-runtime patterns for reconciliation loops
- **Finalizers**: Use finalizers for cleanup of external resources
- **Status**: Always update resource status to reflect actual state
- **Events**: Emit Kubernetes events for important state changes
- **Metrics**: Expose Prometheus metrics for observability
- **RBAC**: Define minimal required permissions for each controller
- **Leader Election**: Use leader election for HA deployments

## Kubernetes Resources
- **RBAC**: Follow principle of least privilege
- **Labels**: Use consistent labeling strategy
- **Annotations**: Document custom annotations with prefixes
- **Namespaces**: Design for multi-tenancy where applicable
- **Security**: Use security contexts and pod security standards

## Development Workflow
- **Tilt**: Primary development tool - run `tilt up` for live reloading development
- **Live Updates**: Tilt automatically rebuilds and redeploys on code changes
- **Debugging**: Use `tilt logs <resource>` to check logs, `tilt describe <resource>` for status
- **Validation**: `helm lint charts/chart-name`
- **Testing**: `helm template charts/chart-name | kubectl apply --dry-run=client -f -`
- **CRD Generation**: `uv run python scripts/generate-crds.py` - Generate CRDs from Pydantic models
- **CRD Updates**: Regenerate and validate CRDs on schema changes
- **Kind Testing**: Test on local kind clusters before production

## Tilt Development
- **Setup**: Run `tilt up` to start development environment with live reloading
- **Logs**: `tilt logs modal-operator` to view operator logs
- **Status**: `tilt describe modal-operator` for resource status
- **Debugging**: Tilt UI at http://localhost:10350 for visual debugging
- **Live Reload**: Code changes automatically trigger rebuilds and redeployments
