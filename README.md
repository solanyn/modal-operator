# Modal Operator

A Kubernetes operator that enables serverless compute workloads by offloading pods to Modal's cloud infrastructure while maintaining full compatibility with Kubeflow components.

The operator consists of Modal vGPU controllers deployed via Helm charts, built with Python using the [Kopf](https://kopf.readthedocs.io/) framework and the [Modal Python client](https://modal.com/docs).

## Features

- **Three CRD Types**: ModalJob (batch), ModalEndpoint (HTTP), ModalFunction (serverless functions)
- **Seamless GPU Offloading**: Automatically detects GPU pods and runs them on Modal's serverless infrastructure
- **Production Deployments**: Persistent deployments using `app.deploy.aio()` pattern
- **Kubernetes Service Integration**: Functions and endpoints accessible via standard K8s services
- **Direct Status Patching**: Reliable status updates via Kubernetes API
- **Resource Cleanup**: Automatic Modal app teardown on CRD deletion
- **Kubeflow Integration**: Compatible with Katib, Training Operator, and KServe
- **Metrics & Monitoring**: Prometheus metrics for job tracking and cost monitoring
- **Single Distroless Image**: ~180MB image containing operator, logger, and proxy
- **Testing Ready**: Mock mode for development and testing without Modal API

## Quick Start

### Prerequisites

- Kubernetes cluster (kind, minikube, or any K8s distribution)
- Helm 3.x
- Docker
- kubectl
- Python 3.9+ with [uv](https://docs.astral.sh/uv/)
- Modal account and API tokens

### Development Setup

**Note: This project uses `uv` exclusively for Python package management.**

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Format code
uv run ruff format

# Lint code
uv run ruff check

# Test real Modal integration
uv run python test_real_modal.py

# Run e2e tests locally with kind
./scripts/run-e2e-tests.sh

# Run e2e tests in Modal (recommended)
./scripts/run-modal-e2e.sh
```

### Testing on kind

The easiest way to test the operator is using the provided kind setup:

```bash
# Run the complete e2e test
inv test-e2e

# Or step by step:
inv kind-create
inv docker-build
inv kind-load
inv deploy
inv test-gpu-pod
```

This will:
1. Create a kind cluster
2. Build and load the operator image
3. Deploy the operator with mock Modal client
4. Test with a sample GPU pod

### Production Deployment

1. **Create Modal API credentials secret:**
```bash
kubectl create secret generic modal-token \
  --namespace modal-system \
  --from-literal=token-id="your-modal-token-id" \
  --from-literal=token-secret="your-modal-token-secret"
```

2. **Deploy with Helm:**
```bash
helm upgrade --install modal-operator ./charts/modal-operator \
  --namespace modal-system \
  --create-namespace \
  --set testing.mockModal=false
```

## Usage

The operator provides three ways to run workloads on Modal:

1. **ModalJob CRD** - For batch jobs and training workloads
2. **ModalEndpoint CRD** - For HTTP services and inference endpoints
3. **ModalFunction CRD** - For serverless functions callable from Kubernetes
4. **Pod Annotations** - For automatic GPU pod offloading

### ModalJob - Batch Workloads

Run batch jobs on Modal with GPU support:

```yaml
apiVersion: modal-operator.io/v1alpha1
kind: ModalJob
metadata:
  name: training-job
  namespace: default
spec:
  image: pytorch/pytorch:latest
  command: ["python", "train.py"]
  cpu: "4.0"
  memory: "16Gi"
  gpu: "A100"  # GPU type: T4, A10G, A100, etc.
  env:
    EPOCHS: "100"
    BATCH_SIZE: "32"
```

### ModalEndpoint - HTTP Services

Deploy HTTP services with persistent URLs:

```yaml
apiVersion: modal-operator.io/v1alpha1
kind: ModalEndpoint
metadata:
  name: inference-api
  namespace: default
spec:
  image: python:3.11-slim
  handler: "app.handler"  # Python module.function
  cpu: "2.0"
  memory: "4Gi"
  gpu: "T4"  # Optional GPU
  min_replicas: 1
  max_replicas: 10
  env:
    MODEL_PATH: "/models/latest"
```

The endpoint will be accessible at the URL provided in the status:
```bash
kubectl get modalendpoint inference-api -o jsonpath='{.status.endpoint_url}'
```

### ModalFunction - Serverless Functions

Deploy serverless functions callable from within Kubernetes:

```yaml
apiVersion: modal-operator.io/v1alpha1
kind: ModalFunction
metadata:
  name: data-processor
  namespace: default
spec:
  image: python:3.11-slim
  handler: "processor.process"  # Python module.function
  cpu: "1.0"
  memory: "2Gi"
  timeout: 300  # seconds
  concurrency: 10  # concurrent invocations
  env:
    LOG_LEVEL: "INFO"
```

The function is callable from other pods via Kubernetes Service:
```python
import requests
response = requests.get("http://data-processor.default.svc.cluster.local")
```

### Kubeflow TrainJob Integration

Use Kubeflow Trainer v2 TrainJobs for distributed ML training on Modal:

```yaml
apiVersion: trainer.kubeflow.org/v1alpha1
kind: TrainJob
metadata:
  name: pytorch-distributed
  annotations:
    modal.com/enabled: "true"
spec:
  runtimeRef:
    name: modal-pytorch-runtime
  trainer:
    command: ["python", "-m", "torch.distributed.run"]
    args: ["--nproc_per_node=2", "train.py"]
    env:
    - name: PYTHONPATH
      value: "/workspace"
  podSpecOverrides:
  - targetJobs: ["trainer-node"]
    containers:
    - name: trainer
      resources:
        requests:
          nvidia.com/gpu: 1
```

### Modal Container Mode

Use Modal containers directly via annotations for maximum flexibility:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: modal-container
  annotations:
    modal-operator.io/use-modal: "true"
    modal-operator.io/image: "python:3.11-slim"
    modal-operator.io/command: "python -c print('Hello from Modal!')"
    modal-operator.io/cpu: "1.0"
    modal-operator.io/memory: "512Mi"
    modal-operator.io/gpu: "T4:1"  # Optional: GPU specification
    modal-operator.io/timeout: "300"
    modal-operator.io/env-PYTHONPATH: "/app"  # Environment variables
spec:
  containers:
  - name: placeholder
    image: busybox
    command: ["sleep", "infinity"]
```

### Basic GPU Pod Offloading

Add the annotation to any pod that should be offloaded to Modal:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-training
  annotations:
    modal-operator.io/offload: "true"
    modal-operator.io/gpu-type: "A100"  # Optional: specify GPU type
    modal-operator.io/tunnel: "true"    # Optional: enable secure tunneling
    modal-operator.io/tunnel-port: "8000"  # Optional: tunnel port (default: 8000)
spec:
  containers:
  - name: training
    image: pytorch/pytorch:latest
    resources:
      requests:
        nvidia.com/gpu: 1
```

### Automatic GPU Detection

Pods requesting GPU resources are automatically detected and offloaded:

```yaml
resources:
  requests:
    nvidia.com/gpu: 1  # Automatically triggers Modal offloading
```

### Kubeflow Integration

The operator works seamlessly with Kubeflow components:

- **Katib**: Hyperparameter tuning experiments run on Modal GPUs
- **Training Operator**: TFJob/PyTorchJob distributed training
- **KServe**: Model inference endpoints

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Kubeflow      │    │  Modal vGPU      │    │     Modal       │
│   Components    │───▶│   Controllers    │───▶│   Apps/Functions│
│                 │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │                          │
                              ▼                          │
                       ┌──────────────────┐              │
                       │   Kubernetes     │              │
                       │   Pod Status     │              │
                       │   (Transparent)  │              │
                       └──────────────────┘              │
                                                         │
                       ┌──────────────────┐              │
                       │  Secure Tunnels  │◀─────────────┘
                       │ (Private Network)│
                       └──────────────────┘
```

### Components

- **Modal App Manager**: Creates Modal Apps with Functions for each GPU pod
- **K8s Status Mapper**: Maps Modal App/Function status to Kubernetes pod phases transparently
- **Tunnel Manager**: Creates secure Modal tunnels for private networking
- **Pod Controller**: Watches GPU pods and creates corresponding Modal Apps
- **Status Synchronizer**: Continuously syncs Modal App status to Kubernetes

### Transparency Features

- **Container Status**: Shows Modal Function IDs as container image IDs
- **Host Information**: Displays `modal.com` as the host for offloaded pods
- **Tunnel Services**: Creates Kubernetes Services pointing to Modal tunnel endpoints
- **Rich Annotations**: Exposes Modal App IDs, Function IDs, and tunnel URLs
- **Native K8s Experience**: Pods appear as normal Kubernetes resources with Modal backend

## Configuration

### Modal API Setup

1. **Create `.env` file with your Modal tokens:**
```bash
MODAL_TOKEN_ID=ak-your-token-id
MODAL_TOKEN_SECRET=as-your-token-secret
```

2. **Test Modal integration:**
```bash
uv run python test_real_modal.py
```

### Kubernetes Deployment

Key configuration options in `values.yaml`:

```yaml
modal:
  tokenSecret: modal-token      # Secret containing Modal API credentials
  defaultGpuType: "T4"         # Default GPU type for Modal jobs
  environment: "dev"           # Modal environment

controller:
  enableKatibAdapter: true     # Enable Katib integration
  enableTrainingOperatorAdapter: true  # Enable Training Operator integration
  enableKServeAdapter: true    # Enable KServe integration
  metricsEnabled: true         # Enable Prometheus metrics

testing:
  enabled: false               # Enable testing mode
  mockModal: true             # Use mock Modal client
```

## Monitoring

The operator exposes Prometheus metrics on port 8081:

- `modal_jobs_total`: Total number of Modal jobs by status and GPU type
- `modal_job_duration_seconds`: Job duration histogram
- `modal_jobs_active`: Currently active jobs
- `modal_gpu_utilization`: GPU utilization by job

Access metrics:
```bash
kubectl port-forward svc/modal-operator 8081:8081 -n modal-system
curl http://localhost:8081/metrics
```

## Development

### Building

```bash
# Install dependencies
uv sync

# Build Docker image
uv run invoke docker-build

# Run tests
uv run pytest

# Format code
uv run ruff format

# Lint code
uv run ruff check
```

### Testing

```bash
# Create kind cluster and run e2e tests
uv run invoke test-e2e

# Test individual components
uv run invoke test-gpu-pod

# Test real Modal API integration
uv run python test_real_modal.py

# Clean up
uv run invoke kind-delete
```

### Mock Mode

For development and testing, the operator can run in mock mode without requiring Modal API credentials:

```yaml
testing:
  enabled: true
  mockModal: true
```

In mock mode:
- Jobs are simulated locally
- Status transitions happen automatically
- No actual GPU workloads are executed

## Troubleshooting

### Common Issues

1. **Pod stuck in Pending**: Check operator logs for Modal API errors
2. **Status not updating**: Verify RBAC permissions for pod status updates
3. **Metrics not available**: Ensure metrics server is enabled and accessible

### Debugging

```bash
# Check operator logs
kubectl logs -n modal-system deployment/modal-operator -f

# Check pod events
kubectl describe pod <pod-name>

# Verify RBAC
kubectl auth can-i update pods/status --as=system:serviceaccount:modal-system:modal-operator
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Run `make test-e2e` to verify
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
