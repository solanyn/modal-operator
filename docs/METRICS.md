# Modal Operator Metrics

The Modal operator exposes comprehensive Prometheus metrics for monitoring job execution, resource utilization, and system health.

## Metrics Endpoint

Metrics are exposed on port `8081` at the `/metrics` endpoint:

```bash
# Port forward to access metrics
kubectl port-forward -n modal-system svc/modal-operator 8081:8081

# View metrics
curl http://localhost:8081/metrics
```

## Available Metrics

### Job Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `modal_jobs_total` | Counter | Total number of Modal jobs | `status`, `gpu_type`, `replicas` |
| `modal_jobs_active` | Gauge | Currently active Modal jobs | `gpu_type` |
| `modal_job_duration_seconds` | Histogram | Job duration in seconds | `status`, `gpu_type` |
| `modal_job_replicas` | Gauge | Number of replicas per job | `job_name` |

### Performance Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `modal_job_queue_seconds` | Histogram | Time jobs spend in queue before starting | `gpu_type` |
| `modal_function_cold_starts_total` | Counter | Total function cold starts | `job_name`, `gpu_type` |

### Resource Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `modal_gpu_utilization` | Gauge | GPU utilization by job | `job_name`, `gpu_type` |
| `modal_network_bandwidth_mbps` | Gauge | Network bandwidth utilization in Mbps | `job_name`, `direction` |

### Cost Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `modal_cost_estimate_usd` | Gauge | Estimated cost in USD | `job_name`, `gpu_type`, `time_period` |

### Networking Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `modal_i6pn_jobs_total` | Counter | Total jobs using i6pn networking | `replicas` |

### Error Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `modal_operator_errors_total` | Counter | Total operator errors | `error_type`, `component` |

### Operator Health Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `modal_operator_restarts_total` | Counter | Total operator restarts | - |
| `modal_webhook_requests_total` | Counter | Total webhook requests | `method`, `status` |

## Prometheus Configuration

### ServiceMonitor

The operator includes a ServiceMonitor for automatic Prometheus discovery:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: modal-operator
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: modal-operator
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
```

### Prometheus Rules

Example alerting rules:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: modal-operator-alerts
spec:
  groups:
  - name: modal-operator
    rules:
    - alert: ModalJobFailureRate
      expr: rate(modal_jobs_total{status="failed"}[5m]) > 0.1
      for: 2m
      labels:
        severity: warning
      annotations:
        summary: "High Modal job failure rate"
        description: "Modal job failure rate is {{ $value }} jobs/sec"
    
    - alert: ModalOperatorDown
      expr: up{job="modal-operator"} == 0
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "Modal operator is down"
        description: "Modal operator has been down for more than 1 minute"
    
    - alert: HighErrorRate
      expr: rate(modal_operator_errors_total[5m]) > 0.05
      for: 2m
      labels:
        severity: warning
      annotations:
        summary: "High error rate in Modal operator"
        description: "Error rate is {{ $value }} errors/sec"
```

## Grafana Dashboard

A comprehensive Grafana dashboard is available at `monitoring/grafana-dashboard.json`.

### Key Panels

1. **Active Modal Jobs** - Current number of running jobs
2. **Jobs by Status** - Distribution of job statuses
3. **GPU Utilization by Type** - Resource usage by GPU type
4. **Job Duration Distribution** - Performance analysis
5. **i6pn Networking Usage** - Distributed job metrics
6. **Error Rate** - System health monitoring
7. **Replica Distribution** - Multi-replica job tracking

### Import Dashboard

```bash
# Import via Grafana UI
# Dashboard ID: Upload monitoring/grafana-dashboard.json

# Or via API
curl -X POST \
  http://grafana:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  -d @monitoring/grafana-dashboard.json
```

## Monitoring Setup

### Enable Metrics

Metrics are enabled by default. To configure:

```yaml
# values.yaml
metrics:
  enabled: true
  interval: 30s
  scrapeTimeout: 10s
  labels:
    prometheus.io/scrape: "true"
```

### Deploy with Monitoring

```bash
helm upgrade --install modal-operator charts/modal-operator \
  --namespace modal-system \
  --set metrics.enabled=true \
  --set metrics.interval=15s
```

## Query Examples

### PromQL Queries

```promql
# Active jobs by GPU type
sum by (gpu_type) (modal_jobs_active)

# Job success rate
rate(modal_jobs_total{status="completed"}[5m]) / rate(modal_jobs_total[5m])

# Average job duration
rate(modal_job_duration_seconds_sum[5m]) / rate(modal_job_duration_seconds_count[5m])

# 95th percentile queue time
histogram_quantile(0.95, rate(modal_job_queue_seconds_bucket[5m]))

# Cold start rate by GPU type
rate(modal_function_cold_starts_total[5m]) by (gpu_type)

# Network bandwidth utilization
sum by (job_name) (modal_network_bandwidth_mbps{direction="ingress"})

# Total estimated hourly cost
sum(modal_cost_estimate_usd{time_period="hourly"})

# i6pn usage percentage
rate(modal_i6pn_jobs_total[5m]) / rate(modal_jobs_total[5m]) * 100

# Error rate by component
rate(modal_operator_errors_total[5m]) by (component)

# Webhook success rate
rate(modal_webhook_requests_total{status!="error"}[5m]) / rate(modal_webhook_requests_total[5m])

# Top GPU types by usage
topk(5, sum by (gpu_type) (modal_jobs_active))
```

### Alerting Queries

```promql
# High failure rate (>10%)
rate(modal_jobs_total{status="failed"}[5m]) / rate(modal_jobs_total[5m]) > 0.1

# Long queue times (>2 minutes for 95th percentile)
histogram_quantile(0.95, rate(modal_job_queue_seconds_bucket[5m])) > 120

# High cold start rate (>1 per minute)
rate(modal_function_cold_starts_total[5m]) * 60 > 1

# High cost (>$100/hour)
sum(modal_cost_estimate_usd{time_period="hourly"}) > 100

# Long-running jobs (>1 hour)
modal_job_duration_seconds > 3600

# High error rate (>5 errors/min)
rate(modal_operator_errors_total[5m]) * 60 > 5

# Operator restarts (any restart in last 5 minutes)
increase(modal_operator_restarts_total[5m]) > 0

# Webhook errors (>5% error rate)
rate(modal_webhook_requests_total{status="error"}[5m]) / rate(modal_webhook_requests_total[5m]) > 0.05

# No active jobs (potential issue)
sum(modal_jobs_active) == 0 and rate(modal_jobs_total[5m]) > 0
```

## Troubleshooting

### Metrics Not Available

1. Check metrics server is running:
```bash
kubectl logs -n modal-system deployment/modal-operator | grep "Metrics server"
```

2. Verify port is accessible:
```bash
kubectl port-forward -n modal-system svc/modal-operator 8081:8081
curl http://localhost:8081/metrics
```

3. Check ServiceMonitor configuration:
```bash
kubectl get servicemonitor -n modal-system modal-operator -o yaml
```

### Missing Data

1. Verify Prometheus is scraping:
```bash
# Check Prometheus targets
curl http://prometheus:9090/api/v1/targets
```

2. Check metric labels:
```bash
# View raw metrics
curl http://localhost:8081/metrics | grep modal_
```

### Performance Impact

Metrics collection has minimal overhead:
- Memory: ~10MB additional
- CPU: <1% additional
- Network: ~1KB/scrape interval
