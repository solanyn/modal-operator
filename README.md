# Modal Operator

> **Note:** This project is not affiliated with or endorsed by Modal Labs.

A Kubernetes operator that deploys Modal apps from inline Python source and exposes them as native Kubernetes Services.

## How It Works

```
kubectl apply ModalApp (inline Python) → operator runs modal deploy → ExternalName Service
                                                                        ↓
                                                          app.namespace.svc.cluster.local
```

1. You create a `ModalApp` custom resource with inline Python source
2. The operator deploys it to Modal via the CLI
3. An ExternalName Service is created pointing to the Modal URL
4. Other pods access it at `http://<name>.<namespace>.svc.cluster.local`

## Installation

```bash
# Install CRDs
kubectl apply -f https://raw.githubusercontent.com/solanyn/modal-operator/main/deploy/crds.yaml

# Create Modal credentials
kubectl create secret generic modal-credentials \
  --namespace modal-system \
  --from-literal=MODAL_TOKEN_ID="your-token-id" \
  --from-literal=MODAL_TOKEN_SECRET="your-token-secret"

# Install operator
helm install modal-operator oci://ghcr.io/solanyn/charts/modal-operator \
  --namespace modal-system --create-namespace
```

## Usage

```yaml
apiVersion: modal.internal.io/v1alpha1
kind: ModalApp
metadata:
  name: hello-modal
  namespace: default
spec:
  source: |
    import modal

    app = modal.App("hello-modal")

    @app.function()
    @modal.web_endpoint()
    def hello():
        return {"message": "Hello from Modal!"}
```

```bash
kubectl apply -f app.yaml
kubectl get modalapps

# Access from any pod in the cluster
curl http://hello-modal.default.svc.cluster.local
```

### GPU Workloads

```yaml
apiVersion: modal.internal.io/v1alpha1
kind: ModalApp
metadata:
  name: llm-serve
  namespace: ai
spec:
  appName: llm-serve
  source: |
    import modal

    app = modal.App("llm-serve")

    @app.function(gpu="L40S")
    @modal.web_endpoint()
    def serve():
        ...
  envFrom:
    - secretRef:
        name: huggingface-token
  env:
    MODEL_NAME: "mistralai/Devstral-Small-2505"
```

### Spec Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source` | string | required | Inline Python source code |
| `appName` | string | metadata.name | Modal app name |
| `envFrom` | list | [] | Secrets/ConfigMaps to inject as env vars |
| `env` | map | {} | Plain environment variables |
| `servicePort` | int | 80 | Service port |

### Status

```bash
kubectl get modalapps
NAME          PHASE     URL                                      AGE
hello-modal   Running   https://user--hello-modal.modal.run      5m
```

## Configuration

Helm values:

```yaml
modal:
  tokenSecret: modal-credentials    # Secret with MODAL_TOKEN_ID and MODAL_TOKEN_SECRET
  tokenIdKey: MODAL_TOKEN_ID
  tokenSecretKey: MODAL_TOKEN_SECRET

watchNamespaces: ""                 # Comma-separated, empty = cluster-wide

metrics:
  enabled: true
  port: 8081
```

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format .
uv run python -m pytest tests/ -v
```

## License

MIT License - see LICENSE file for details.
