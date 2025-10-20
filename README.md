# Modal Operator

> **Note:** This project is not affiliated with or endorsed by Modal Labs.

Run Kubernetes workloads on Modal's serverless infrastructure - get instant GPU access, pay only for compute time, and keep your existing K8s workflows.

## Why Use This?

- **Instant GPU Access**: No waiting for GPU nodes - Modal provisions them in seconds
- **Cost Savings**: Pay only for actual compute time, not idle GPUs sitting in your cluster
- **Zero Infrastructure**: No GPU node management, autoscaling, or capacity planning
- **Keep Your Workflows**: Works with existing Kubernetes pods, Kubeflow, and standard tooling
- **Native K8s Integration**: Three CRDs for batch jobs, HTTP services, and serverless functions

## Installation

```bash
# Create Modal credentials
kubectl create secret generic modal-token \
  --namespace modal-system \
  --from-literal=MODAL_TOKEN_ID="your-token-id" \
  --from-literal=MODAL_TOKEN_SECRET="your-token-secret"

# Install via Helm
helm install modal-operator oci://ghcr.io/solanyn/charts/modal-operator \
  --namespace modal-system --create-namespace
```

## Quick Examples

## Usage

The operator provides three ways to run workloads on Modal:

1. **ModalJob CRD** - For batch jobs and training workloads
2. **ModalEndpoint CRD** - For HTTP services and inference endpoints
3. **ModalFunction CRD** - For serverless functions callable from Kubernetes

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
