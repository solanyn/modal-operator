# Modal Operator Design

## Overview

A Kubernetes operator that manages Modal apps with in-cluster service discovery and automatic auth injection.

## TODO

- [ ] Use `uv` to install modal as a dependency so it can be used as a binary or via subprocess
- [ ] Consider rewriting in Go for better k8s integration and single binary deployment

## Goals

- Single CRD (`ModalApp`) to deploy and manage Modal apps
- Automatic in-cluster Service for each app
- Auth header injection (no client-side Modal credentials needed)
- Optional external exposure via HTTPRoute or Ingress
- Clean deletion (stops Modal app when CR deleted)

## Architecture

```
                                ┌─────────────────┐
                                │ modal-operator  │
                                │ (1 replica)     │
                                │                 │
                                │ watches CRs     │
                                │ modal deploy    │
                                │ creates Service │
                                └─────────────────┘
                                         │
                                         │ writes URLs to status
                                         ▼
┌────────┐    ┌─────────┐    ┌─────────────────┐    ┌───────┐
│ Client │───▶│ Service │───▶│ modal-proxy     │───▶│ Modal │
└────────┘    └─────────┘    │ (N replicas)    │    └───────┘
                             │                 │
                             │ injects auth    │
                             │ headers         │
                             └─────────────────┘
```

### Components

**modal-operator** (1 replica)
- Watches ModalApp custom resources
- Runs `modal deploy` on create/update
- Runs `modal app stop` on delete
- Creates Service + EndpointSlice per ModalApp
- Optionally creates HTTPRoute or Ingress

**modal-proxy** (N replicas, horizontally scalable)
- Stateless HTTP proxy
- Watches ModalApp resources for `.status.url`
- Injects `Modal-Key` and `Modal-Secret` headers
- Forwards requests to Modal endpoints

## CRD

```yaml
apiVersion: modal.goyangi.io/v1alpha1
kind: ModalApp
metadata:
  name: devstral-small
  namespace: ai
spec:
  # App name on Modal (defaults to metadata.name)
  appName: llm-devstral-small

  # Inline Python source
  source: |
    import modal
    app = modal.App("llm-devstral-small")
    
    @app.function(gpu="L40S")
    @modal.web_server(port=8000)
    def serve():
        ...

  # Secrets to inject as env vars during deploy
  envFrom:
    - secretRef:
        name: huggingface-token

  # Plain env vars
  env:
    MODEL_NAME: "mistralai/Devstral-Small-2505"

  # Service port (Service always created)
  servicePort: 80  # default: 80

  # Optional: external exposure via Gateway API
  route:
    hostname: devstral.goyangi.io
    parentRef:  # optional, uses operator default if omitted
      name: envoy-external
      namespace: network

  # OR: external exposure via Ingress
  ingress:
    hostname: devstral.goyangi.io
    ingressClassName: nginx  # optional, uses operator default

status:
  phase: Pending | Deploying | Running | Failed | Stopping
  url: solanyn--llm-devstral-small-serve.modal.run
  appId: ap-xxxxx
  lastDeployed: "2026-02-03T10:00:00Z"
  message: ""
```

## Operator Configuration

```yaml
# values.yaml or ConfigMap
config:
  # Modal credentials (operator-level, used for all deploys)
  credentialsSecretRef:
    name: modal-credentials
    namespace: modal-system
    # expects: MODAL_TOKEN_ID, MODAL_TOKEN_SECRET

  # Namespaces to watch (empty = cluster-wide)
  watchNamespaces: []

  # Proxy settings
  proxy:
    port: 8080
    replicas: 2

  # Defaults for external exposure
  defaultGatewayRef:
    name: envoy-external
    namespace: network
  defaultIngressClassName: nginx
```

## Resources Created

### Always (per ModalApp)

**Service**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: devstral-small
  namespace: ai
  ownerReferences:
    - apiVersion: modal.goyangi.io/v1alpha1
      kind: ModalApp
      name: devstral-small
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: 8080
```

**EndpointSlice**
```yaml
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: devstral-small
  namespace: ai
  labels:
    kubernetes.io/service-name: devstral-small
addressType: IPv4
endpoints:
  - addresses:
      - "10.x.x.x"  # modal-proxy pod IPs
ports:
  - port: 8080
```

### If `route` specified

**HTTPRoute**
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: devstral-small
  namespace: ai
spec:
  parentRefs:
    - name: envoy-external
      namespace: network
  hostnames:
    - devstral.goyangi.io
  rules:
    - backendRefs:
        - name: devstral-small
          port: 80
```

### If `ingress` specified

**Ingress**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: devstral-small
  namespace: ai
spec:
  ingressClassName: nginx
  rules:
    - host: devstral.goyangi.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: devstral-small
                port:
                  number: 80
```

## Lifecycle

### Create

1. Add finalizer to ModalApp
2. Read secrets from `envFrom`
3. Write source to temp file
4. Run `modal deploy <path> --env KEY=val ...`
5. Parse URL from output
6. Update status: `phase=Running`, `url=...`
7. Create Service + EndpointSlice
8. Create HTTPRoute/Ingress if specified

### Update

1. If `source` or `env` changed: redeploy
2. If `route`/`ingress` changed: update/create/delete as needed

### Delete

1. Run `modal app stop <appName>`
2. Delete Service, EndpointSlice, HTTPRoute/Ingress
3. Remove finalizer

## Proxy

### Request Flow

1. Client sends request to `devstral-small.ai.svc.cluster.local`
2. Service routes to modal-proxy pod
3. Proxy extracts service name from Host header
4. Looks up ModalApp CR to get Modal URL from `.status.url`
5. Injects `Modal-Key` and `Modal-Secret` headers
6. Forwards request to Modal endpoint
7. Returns response to client

### URL Cache

Proxy watches ModalApp resources and maintains in-memory cache:
```
service-name.namespace → modal-url
```

Cache updated on ModalApp status changes.

### Auth Headers

Read from operator-level secret:
- `Modal-Key: <MODAL_TOKEN_ID>`
- `Modal-Secret: <MODAL_TOKEN_SECRET>`

## File Structure

```
modal-operator/
├── modal_operator/
│   ├── __init__.py
│   ├── config.py         # configuration loading
│   ├── operator.py       # kopf handlers
│   ├── deployer.py       # modal CLI wrapper
│   ├── resources.py      # Service/EndpointSlice/Route creation
│   └── proxy/
│       ├── __init__.py
│       ├── server.py     # aiohttp proxy server
│       └── cache.py      # ModalApp URL cache
├── charts/modal-operator/
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── crds/
│   │   └── modalapp.yaml
│   └── templates/
│       ├── operator-deployment.yaml
│       ├── proxy-deployment.yaml
│       ├── operator-rbac.yaml
│       └── proxy-rbac.yaml
```

## Usage Examples

### Basic (in-cluster only)

```yaml
apiVersion: modal.goyangi.io/v1alpha1
kind: ModalApp
metadata:
  name: ministral-8b
  namespace: ai
spec:
  source: |
    import modal
    app = modal.App("llm-ministral-8b")
    # ...
```

Access: `http://ministral-8b.ai.svc.cluster.local`

### With external access

```yaml
apiVersion: modal.goyangi.io/v1alpha1
kind: ModalApp
metadata:
  name: devstral-small
  namespace: ai
spec:
  source: |
    ...
  route:
    hostname: devstral.goyangi.io
```

Access:
- Internal: `http://devstral-small.ai.svc.cluster.local`
- External: `https://devstral.goyangi.io`

### With secrets

```yaml
apiVersion: modal.goyangi.io/v1alpha1
kind: ModalApp
metadata:
  name: gpt-oss-120b
  namespace: ai
spec:
  source: |
    ...
  envFrom:
    - secretRef:
        name: huggingface-token
  env:
    MODEL_NAME: "openai/gpt-oss-120b"
```
