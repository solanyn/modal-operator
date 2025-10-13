"""Prometheus metrics for Modal operator."""

import time
from typing import Dict, Optional

from prometheus_client import Counter, Gauge, Histogram, start_http_server


class ModalOperatorMetrics:
    """Prometheus metrics collector for Modal operator."""

    def __init__(self):
        # Job metrics
        self.jobs_total = Counter("modal_jobs_total", "Total number of Modal jobs", ["status", "gpu_type", "replicas"])

        self.jobs_active = Gauge("modal_jobs_active", "Currently active Modal jobs", ["gpu_type"])

        self.job_duration = Histogram(
            "modal_job_duration_seconds",
            "Modal job duration in seconds",
            ["status", "gpu_type"],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600],
        )

        # Resource metrics
        self.gpu_utilization = Gauge("modal_gpu_utilization", "GPU utilization by job", ["job_name", "gpu_type"])

        self.replica_count = Gauge("modal_job_replicas", "Number of replicas per job", ["job_name"])

        # Networking metrics
        self.i6pn_jobs = Counter("modal_i6pn_jobs_total", "Total jobs using i6pn networking", ["replicas"])

        self.network_bandwidth = Gauge(
            "modal_network_bandwidth_mbps", "Network bandwidth utilization in Mbps", ["job_name", "direction"]
        )

        # Cost metrics
        self.cost_estimate = Gauge(
            "modal_cost_estimate_usd", "Estimated cost in USD", ["job_name", "gpu_type", "time_period"]
        )

        # Performance metrics
        self.job_queue_time = Histogram(
            "modal_job_queue_seconds",
            "Time jobs spend in queue before starting",
            ["gpu_type"],
            buckets=[1, 5, 10, 30, 60, 120, 300],
        )

        self.function_cold_starts = Counter(
            "modal_function_cold_starts_total", "Total function cold starts", ["job_name", "gpu_type"]
        )

        # Error metrics
        self.errors_total = Counter("modal_operator_errors_total", "Total operator errors", ["error_type", "component"])

        # Operator health metrics
        self.operator_restarts = Counter("modal_operator_restarts_total", "Total operator restarts")

        self.webhook_requests = Counter("modal_webhook_requests_total", "Total webhook requests", ["method", "status"])

        # Track job start times for duration calculation
        self._job_start_times: Dict[str, float] = {}
        self._job_queue_times: Dict[str, float] = {}

    def record_job_queued(self, job_name: str):
        """Record when job enters queue."""
        self._job_queue_times[job_name] = time.time()

    def record_job_started(self, job_name: str, gpu_type: Optional[str] = None):
        """Record when job actually starts running."""
        if job_name in self._job_queue_times:
            queue_time = time.time() - self._job_queue_times[job_name]
            gpu_label = gpu_type or "none"
            self.job_queue_time.labels(gpu_type=gpu_label).observe(queue_time)
            del self._job_queue_times[job_name]

    def record_job_created(
        self, job_name: str, gpu_type: Optional[str] = None, replicas: int = 1, enable_i6pn: bool = False
    ):
        """Record job creation."""
        gpu_label = gpu_type or "none"
        replica_label = str(replicas)

        self.jobs_total.labels(status="created", gpu_type=gpu_label, replicas=replica_label).inc()
        self.jobs_active.labels(gpu_type=gpu_label).inc()
        self.replica_count.labels(job_name=job_name).set(replicas)

        if enable_i6pn:
            self.i6pn_jobs.labels(replicas=replica_label).inc()

        self._job_start_times[job_name] = time.time()
        self.record_job_queued(job_name)

    def record_job_completed(self, job_name: str, status: str, gpu_type: Optional[str] = None):
        """Record job completion."""
        gpu_label = gpu_type or "none"

        self.jobs_total.labels(status=status, gpu_type=gpu_label, replicas="1").inc()
        self.jobs_active.labels(gpu_type=gpu_label).dec()

        # Record duration if we have start time
        if job_name in self._job_start_times:
            duration = time.time() - self._job_start_times[job_name]
            self.job_duration.labels(status=status, gpu_type=gpu_label).observe(duration)
            del self._job_start_times[job_name]

        # Clear replica count
        self.replica_count.labels(job_name=job_name).set(0)

    def record_error(self, error_type: str, component: str):
        """Record operator error."""
        self.errors_total.labels(error_type=error_type, component=component).inc()

    def record_operator_shutdown(self):
        """Record operator shutdown."""
        self.operator_restarts.inc()

    def record_cold_start(self, job_name: str, gpu_type: str):
        """Record function cold start."""
        self.function_cold_starts.labels(job_name=job_name, gpu_type=gpu_type).inc()

    def record_webhook_request(self, method: str, status: str):
        """Record webhook request."""
        self.webhook_requests.labels(method=method, status=status).inc()

    def record_operator_restart(self):
        """Record operator restart."""
        self.operator_restarts.inc()

    def update_gpu_utilization(self, job_name: str, gpu_type: str, utilization: float):
        """Update GPU utilization metric."""
        self.gpu_utilization.labels(job_name=job_name, gpu_type=gpu_type).set(utilization)

    def update_network_bandwidth(self, job_name: str, direction: str, bandwidth_mbps: float):
        """Update network bandwidth metric."""
        self.network_bandwidth.labels(job_name=job_name, direction=direction).set(bandwidth_mbps)

    def update_cost_estimate(self, job_name: str, gpu_type: str, time_period: str, cost_usd: float):
        """Update cost estimate metric."""
        self.cost_estimate.labels(job_name=job_name, gpu_type=gpu_type, time_period=time_period).set(cost_usd)

    def start_metrics_server(self, port: int = 8081):
        """Start Prometheus metrics HTTP server."""
        start_http_server(port)


# Global metrics instance
metrics = ModalOperatorMetrics()
