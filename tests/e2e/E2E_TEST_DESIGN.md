# E2E Test Design for Modal vGPU Operator

## Test Categories

### 1. Basic Pod Interception Tests
- **GPU Pod Detection**: Verify pods with `nvidia.com/gpu` requests are intercepted
- **Annotation-based Offloading**: Test `modal-operator.io/offload: "true"` annotation
- **Modal Container Mode**: Test `modal-operator.io/use-modal: "true"` with custom specs
- **Non-GPU Pod Passthrough**: Ensure regular pods are not intercepted

### 2. CRD Lifecycle Tests
- **ModalJob Creation**: Verify CRDs are created from intercepted pods
- **Status Synchronization**: Test Modal job status → Kubernetes pod status mapping
- **Resource Cleanup**: Verify CRDs are cleaned up when pods are deleted
- **Field Validation**: Test CRD validation rules and constraints

### 3. Kubeflow Integration Tests
- **PyTorchJob Offloading**: Multi-replica distributed training jobs
- **TFJob Support**: TensorFlow distributed training
- **Katib Experiments**: Hyperparameter tuning with Modal scaling
- **Job Status Propagation**: Kubeflow job status → Modal job status → Pod status

### 4. Networking Tests
- **Single Replica Jobs**: Basic Modal job execution
- **Multi-replica with i6pn**: Distributed jobs with IPv6 private networking
- **Cluster Coordination**: Replica discovery and communication
- **Tunnel Integration**: Modal tunnel → Kubernetes service connectivity

### 5. Error Handling Tests
- **Modal API Failures**: Network errors, authentication failures
- **Invalid Configurations**: Malformed CRDs, unsupported features
- **Resource Limits**: Memory/CPU constraints, timeout handling
- **Recovery Scenarios**: Operator restart, cluster failures

### 6. Performance Tests
- **Scale Testing**: Multiple concurrent jobs
- **Resource Utilization**: Memory/CPU usage under load
- **Startup Time**: Time from pod creation to Modal job execution
- **Cleanup Performance**: Resource cleanup efficiency

## Test Implementation Strategy

### Environment Setup
1. **Kind Cluster**: Fresh cluster per test suite
2. **Operator Deployment**: Mock mode for fast testing, real Modal for integration
3. **Kubeflow Components**: Minimal Training Operator installation
4. **Test Data**: Predefined pod specs, job templates

### Test Execution Flow
1. **Setup**: Create kind cluster, deploy operator, install CRDs
2. **Test**: Execute test scenarios with assertions
3. **Validation**: Check Kubernetes resources, Modal job status
4. **Cleanup**: Delete resources, collect logs
5. **Teardown**: Destroy cluster

### Assertion Categories
- **Resource Existence**: CRDs, pods, services created
- **Status Correctness**: Job phases, error conditions
- **Data Integrity**: Spec translation, status mapping
- **Performance Metrics**: Timing, resource usage
