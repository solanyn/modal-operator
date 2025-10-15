# Development Environment

## Prerequisites

- **Docker**: Colima with 30GB disk limit and M4 optimizations
- **Kubernetes**: kind cluster
- **Tilt**: Development environment orchestration

## Quick Start

1. **Start Colima** (if not running):
```bash
colima start --disk 30 --vm-type=vz --vz-rosetta
```

2. **Set Docker environment**:
```bash
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
```

3. **Start Tilt development environment**:
```bash
./tilt.sh
```

4. **Access Tilt UI**: http://localhost:10350

## Tilt Resources

### Setup
- **generate-crds**: Generate CRDs from Pydantic models
- **modal-operator**: Main operator deployment

### Testing
- **test-unit**: Run unit tests (manual trigger)
- **test-e2e**: Run e2e tests (manual trigger)
- **test-gpu-pod**: Example GPU pod for testing (manual trigger)

### Ports
- **8080**: Operator application port
- **8081**: Prometheus metrics port

## Development Workflow

1. **Code Changes**: Edit files in `modal_operator/` - Tilt will automatically rebuild and redeploy
2. **CRD Changes**: Edit `modal_operator/crds.py` - Tilt will regenerate and apply CRDs
3. **Testing**: Use Tilt UI to trigger unit/e2e tests manually
4. **Debugging**: Use port forwards to access operator directly

## Controller Organization

Controllers are organized in `modal_operator/controllers/`:
- `modal_job_controller.py` - Modal job lifecycle management
- `networking_controller.py` - Modal i6pn networking features
- `function_controller.py` - ModalFunction CRD handling
- `webhook_controller.py` - Mutating admission webhook
- `status_sync.py` - Status synchronization
- `trainjob_controller.py` - Kubeflow integration

All controllers follow the "Controller" naming suffix standard.

## Manual Commands

```bash
# Generate CRDs
uv run python scripts/generate-crds.py

# Run unit tests
uv run pytest tests/ -x --tb=short

# Run e2e tests
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
uv run pytest tests/e2e/ -x --tb=short

# Apply test GPU pod
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: test-gpu-pod
  annotations:
    modal-operator.io/offload: "true"
spec:
  containers:
  - name: test
    image: nvidia/cuda:11.8-runtime-ubuntu20.04
    command: ["nvidia-smi"]
    resources:
      requests:
        nvidia.com/gpu: 1
  restartPolicy: Never
EOF
```

## Status

✅ **CRD Generation**: Fixed nullable field handling  
✅ **Colima + Docker**: Working with M4 optimizations  
✅ **Kind Clusters**: Creating successfully  
✅ **Tilt Environment**: Ready for development  
🔄 **E2E Tests**: Infrastructure ready, operator deployment needs work  

## Next Steps

1. Fix operator deployment in e2e tests
2. Add live reload for faster development cycles
3. Integrate with Phase 3 Kubeflow components
