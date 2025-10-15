# GitHub Actions Workflows

This directory contains CI/CD workflows for the Modal Operator project.

## Workflows

### 🧪 test.yml
**Trigger:** Pull requests and pushes to `main`

Runs on every PR and commit to main:
- **Linting:** Ruff format and check
- **Type checking:** MyPy (informational)
- **Unit tests:** Pytest with coverage
- **CRD validation:** Ensures CRDs are up-to-date
- **Helm linting:** Validates Helm chart syntax

### 🐳 build-image.yml
**Trigger:** Pushes to `main`, tags, and pull requests

Builds and pushes container images:
- Multi-architecture builds (amd64, arm64)
- Pushes to GitHub Container Registry (ghcr.io)
- Tags: `latest`, `main`, version tags, commit SHA
- Build attestation for supply chain security
- Only pushes on non-PR builds

### 📦 publish-chart.yml
**Trigger:** Tags starting with `v*` and chart changes

Publishes Helm charts as OCI artifacts:
- Packages Helm chart
- Pushes to GitHub Container Registry
- Automatic versioning from git tags
- Generates chart documentation
- Uploads chart as release artifact

### 🚀 release.yml
**Trigger:** Tags starting with `v*`

Coordinates full release process:
- Creates GitHub Release with changelog
- Triggers image build workflow
- Triggers chart publish workflow
- Generates installation instructions

## Publishing a Release

To publish a new release:

```bash
# Create and push a version tag
git tag v0.1.0
git push origin v0.1.0
```

This will:
1. Create a GitHub Release
2. Build and push Docker images with version tags
3. Publish Helm chart to OCI registry
4. Generate release notes

## Container Images

Published to: `ghcr.io/[owner]/modal-operator`

Tags:
- `latest` - Latest commit on main
- `v*` - Semantic version (e.g., `v0.1.0`)
- `main-sha` - Commit SHA on main branch

## Helm Charts

Published to: `oci://ghcr.io/[owner]/charts/modal-operator`

Install:
```bash
helm install modal-operator \
  oci://ghcr.io/[owner]/charts/modal-operator \
  --version 0.1.0 \
  --namespace modal-system --create-namespace
```

## Secrets Required

No additional secrets required - workflows use `GITHUB_TOKEN` which is automatically provided by GitHub Actions.

## Manual Workflow Runs

All workflows can be manually triggered from the Actions tab in GitHub if needed.
