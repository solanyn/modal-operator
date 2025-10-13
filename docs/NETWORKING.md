# Modal Operator Networking Features

The Modal operator supports advanced networking features for distributed workloads, including IPv6 private networking (i6pn) and multi-replica job coordination.

## Features

### IPv6 Private Networking (i6pn)
- **High-bandwidth communication** between Modal functions (≥50Gbps)
- **Private networking** within Modal workspace
- **Optimized for distributed training** workloads

### Multi-Replica Jobs
- **Distributed execution** across multiple Modal functions
- **Automatic rank assignment** for distributed training frameworks
- **Coordinated job lifecycle** management

## Usage

### Basic Distributed Job

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: distributed-training
  annotations:
    modal-operator.io/use-modal: "true"
    modal-operator.io/image: "python:3.11-slim"
    modal-operator.io/command: "python train.py"
    modal-operator.io/replicas: "4"
    modal-operator.io/enable-i6pn: "true"
spec:
  containers:
  - name: placeholder
    image: busybox
    command: ["sleep", "infinity"]
  restartPolicy: Never
```

### PyTorch Distributed Training

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: pytorch-distributed
  annotations:
    modal-operator.io/use-modal: "true"
    modal-operator.io/image: "pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime"
    modal-operator.io/command: "python -m torch.distributed.launch --nproc_per_node=1 train.py"
    modal-operator.io/replicas: "8"
    modal-operator.io/enable-i6pn: "true"
    modal-operator.io/gpu: "A100:1"
    modal-operator.io/memory: "8Gi"
spec:
  containers:
  - name: placeholder
    image: busybox
    command: ["sleep", "infinity"]
    resources:
      requests:
        nvidia.com/gpu: 1
      limits:
        nvidia.com/gpu: 1
  restartPolicy: Never
```

## Annotations

### Networking Annotations

| Annotation | Description | Default | Example |
|------------|-------------|---------|---------|
| `modal-operator.io/replicas` | Number of distributed replicas | `1` | `"4"` |
| `modal-operator.io/enable-i6pn` | Enable IPv6 private networking | `false` | `"true"` |

### Environment Variables

The operator automatically sets these environment variables for distributed jobs:

- `RANK`: Current replica rank (0-based)
- `WORLD_SIZE`: Total number of replicas
- `MODAL_I6PN_ENABLED`: Whether i6pn is enabled (`"true"` or `"false"`)

### Command Templating

Commands can use templating for distributed parameters:

```yaml
modal-operator.io/command: "python train.py --rank {rank} --world-size {world_size}"
```

## Architecture

### Distributed Job Flow

1. **Pod Creation**: User creates pod with networking annotations
2. **ModalJob Generation**: Operator creates ModalJob with networking spec
3. **Modal Function Creation**: Multiple Modal functions created with rank assignment
4. **i6pn Setup**: IPv6 private networking enabled if requested
5. **Execution**: Functions execute with distributed environment variables
6. **Status Sync**: Job status synchronized back to Kubernetes

### Networking Implementation

```python
# Automatic rank assignment
for rank in range(replicas):
    function.spawn(rank, world_size)

# Environment setup per replica
os.environ["RANK"] = str(rank)
os.environ["WORLD_SIZE"] = str(world_size)
os.environ["MODAL_I6PN_ENABLED"] = str(enable_i6pn).lower()
```

## Examples

### Simple Distributed Job

```bash
kubectl apply -f examples/distributed-training.yaml
```

### Check Job Status

```bash
# Check ModalJob
kubectl get modaljobs

# Check networking parameters
kubectl get modaljobs <name> -o yaml | grep -A5 "replicas\|enable_i6pn"

# Check mirror pods
kubectl get pods | grep mirror
```

## Best Practices

### For Distributed Training

1. **Enable i6pn** for high-bandwidth communication
2. **Use appropriate replica count** based on dataset size
3. **Set sufficient timeout** for training completion
4. **Use GPU-optimized images** for training workloads

### Resource Planning

- **CPU/Memory**: Scale per replica requirements
- **GPU**: Each replica gets dedicated GPU resources
- **Networking**: i6pn provides ≥50Gbps between replicas

### Monitoring

- Monitor job progress through ModalJob status
- Check individual replica logs in Modal dashboard
- Use mirror pods for Kubernetes-native monitoring

## Troubleshooting

### Common Issues

1. **Replicas not starting**: Check Modal workspace limits
2. **Networking issues**: Verify i6pn is enabled in Modal workspace
3. **Timeout errors**: Increase timeout for long-running training jobs

### Debug Commands

```bash
# Check ModalJob status
kubectl describe modaljobs <name>

# Check operator logs
kubectl logs -n modal-system deployment/modal-operator -f

# Verify networking configuration
kubectl get modaljobs <name> -o jsonpath='{.spec.enable_i6pn}'
```
