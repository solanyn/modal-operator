# Tiltfile for Modal vGPU Operator development

# Tilt configuration
# update_settings(suppress_unused_image_warnings=[])

# Load extensions
load('ext://helm_resource', 'helm_resource', 'helm_repo')

# Allow kind cluster context
allow_k8s_contexts('kind-tilt-dev')

# Configuration
config.define_string("namespace", args=False, usage="Kubernetes namespace")
config.define_bool("kubeflow", args=True, usage="Install Kubeflow (default: false)")
cfg = config.parse()
namespace = cfg.get("namespace", "modal-system")
enable_kubeflow = cfg.get("kubeflow", False)

# Set Docker build options for space efficiency
docker_prune_settings(num_builds=2, max_age_mins=60)

# Ensure kind cluster exists with proper configuration
local_resource(
    'kind-cluster',
    cmd='kind get clusters | grep -q tilt-dev || (kind create cluster --name tilt-dev --config kind-config.yaml && kubectl cluster-info)',
    labels=['setup']
)

# Create Modal token secret from .env file
local_resource(
    'modal-token-secret',
    cmd='kubectl create namespace modal-system --dry-run=client -o yaml | kubectl apply -f - && kubectl create secret generic modal-token --namespace modal-system --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -',
    labels=['setup']
)

# Install cert-manager for webhook TLS certificates
local_resource(
    'cert-manager',
    cmd='kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.2/cert-manager.yaml',
    labels=['setup']
)

# Install just ServiceMonitor CRDs (no network dependencies)
local_resource(
    'servicemonitor-crds',
    cmd='kubectl apply --server-side -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.85.0/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml || echo "CRDs already exist"',
    labels=['monitoring']
)

# Clone and install Kubeflow (optional - enable with: tilt up -- --kubeflow)
if enable_kubeflow:
    local_resource(
        'kubeflow-manifests',
        cmd='rm -rf .tmp/kubeflow-manifests && mkdir -p .tmp && git clone --depth 1 --branch v1.10.2 https://github.com/kubeflow/manifests.git .tmp/kubeflow-manifests',
        labels=['setup']
    )

    local_resource(
        'kubeflow-install',
        cmd='kubectl apply --server-side --validate=false --force-conflicts -k .tmp/kubeflow-manifests/example || sleep 30',
        deps=['.tmp/kubeflow-manifests'],
        resource_deps=['kubeflow-manifests'],
        auto_init=True,
        labels=['setup']
    )

# Generate and apply CRDs
local_resource(
    'generate-crds',
    cmd='uv sync && uv run python scripts/generate-crds.py',
    deps=['modal_operator/crds.py', 'scripts/generate-crds.py', 'pyproject.toml'],
    labels=['setup']
)

k8s_yaml(['charts/modal-operator/crds/modaljobs.yaml', 'charts/modal-operator/crds/modalendpoints.yaml', 'charts/modal-operator/crds/modalfunctions.yaml'])

# Wait for CRDs to be ready (with retry for timing issues)
local_resource(
    'wait-for-crds',
    cmd='sleep 2 && kubectl wait --for condition=established --timeout=60s crd/modaljobs.modal-operator.io crd/modalendpoints.modal-operator.io crd/modalfunctions.modal-operator.io',
    resource_deps=['generate-crds'],
    labels=['setup']
)

# Build single operator image (contains operator, logger, and proxy)
docker_build(
    'modal-operator',
    '.',
    dockerfile='Dockerfile'
)

# Build vprox image for transparent networking
# docker_build(
#     'ghcr.io/solanyn/modal-operator-vprox',
#     '.',
#     dockerfile='docker/vprox/Dockerfile'
# )

# Deploy operator with Helm (testing overrides)
helm_resource(
    'modal-operator',
    'charts/modal-operator',
    namespace=namespace,
    flags=[
        '--create-namespace',
        '--set', 'modal.environment=main',  # Use main environment
        '--set', 'replicaCount=1'
    ],
    resource_deps=['wait-for-crds'],
    image_deps=['modal-operator'],
    image_keys=[('image.repository', 'image.tag')]
)

# Port forward for debugging
k8s_resource(
    'modal-operator',
    port_forwards=['8080:8080', '8081:8081'],
    labels=['operator']
)

# Example GPU pod for testing
k8s_yaml('examples/modal-container-pod.yaml')

k8s_resource(
    'modal-container-example',
    labels=['test-pods'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL
)

print("🚀 Modal vGPU Operator development environment ready!")
print("📋 Available resources:")
print("  - prometheus-operator: Prometheus Operator for ServiceMonitor CRDs")
print("  - prometheus: Metrics collection server")
print("  - grafana-helm: Grafana dashboards (admin/admin)")
if enable_kubeflow:
    print("  - kubeflow-install: Complete Kubeflow v1.10.2 platform")
else:
    print("  - kubeflow: DISABLED (enable with: tilt up -- --kubeflow)")
print("  - modal-operator: Main operator deployment")
print("  - modal-container-example: Example GPU pod for testing")
print("🔧 Ports: 8080 (app), 8081 (metrics)")
