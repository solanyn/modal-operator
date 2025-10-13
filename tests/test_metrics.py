"""Tests for Modal operator metrics."""

import time
from unittest.mock import MagicMock, patch

from modal_operator.metrics import ModalOperatorMetrics, metrics


class TestModalOperatorMetrics:
    """Test Modal operator metrics collection."""

    def setup_method(self):
        """Set up test metrics instance."""
        # Mock all prometheus client classes to avoid registry conflicts
        with (
            patch("modal_operator.metrics.Counter") as mock_counter,
            patch("modal_operator.metrics.Gauge") as mock_gauge,
            patch("modal_operator.metrics.Histogram") as mock_histogram,
        ):
            # Create mock instances
            mock_counter.return_value = MagicMock()
            mock_gauge.return_value = MagicMock()
            mock_histogram.return_value = MagicMock()

            self.test_metrics = ModalOperatorMetrics()

    def test_job_creation_metrics(self):
        """Test job creation metrics recording."""
        self.test_metrics.record_job_created("test-job", "A100", replicas=2, enable_i6pn=True)

        # Verify methods were called
        self.test_metrics.jobs_total.labels.assert_called()
        self.test_metrics.jobs_active.labels.assert_called()
        self.test_metrics.replica_count.labels.assert_called()
        self.test_metrics.i6pn_jobs.labels.assert_called()

    def test_job_completion_metrics(self):
        """Test job completion metrics recording."""
        # Create job first
        self.test_metrics.record_job_created("test-job", "T4")

        # Complete job
        self.test_metrics.record_job_completed("test-job", "succeeded", "T4")

        # Verify methods were called
        self.test_metrics.jobs_total.labels.assert_called()
        self.test_metrics.jobs_active.labels.assert_called()

    def test_job_duration_tracking(self):
        """Test job duration histogram tracking."""
        job_name = "duration-test"

        # Record job creation
        self.test_metrics.record_job_created(job_name, "A100")

        # Simulate some time passing
        time.sleep(0.1)

        # Complete job
        self.test_metrics.record_job_completed(job_name, "succeeded", "A100")

        # Verify duration tracking works
        assert job_name not in self.test_metrics._job_start_times

    def test_queue_time_tracking(self):
        """Test job queue time tracking."""
        job_name = "queue-test"

        # Record job queued
        self.test_metrics.record_job_queued(job_name)

        # Simulate queue time
        time.sleep(0.05)

        # Record job started
        self.test_metrics.record_job_started(job_name, "T4")

        # Verify queue time was tracked
        assert job_name not in self.test_metrics._job_queue_times

    def test_error_metrics(self):
        """Test error metrics recording."""
        self.test_metrics.record_error("job_creation_failed", "modal_client")

        # Verify method was called
        self.test_metrics.errors_total.labels.assert_called_with(
            error_type="job_creation_failed", component="modal_client"
        )

    def test_cold_start_metrics(self):
        """Test cold start metrics recording."""
        self.test_metrics.record_cold_start("test-job", "A100")

        # Verify method was called
        self.test_metrics.function_cold_starts.labels.assert_called_with(job_name="test-job", gpu_type="A100")

    def test_webhook_metrics(self):
        """Test webhook metrics recording."""
        self.test_metrics.record_webhook_request("POST", "intercepted")
        self.test_metrics.record_webhook_request("GET", "healthy")

        # Verify methods were called
        assert self.test_metrics.webhook_requests.labels.call_count >= 2

    def test_operator_restart_metrics(self):
        """Test operator restart metrics."""
        self.test_metrics.record_operator_restart()

        # Verify method was called
        self.test_metrics.operator_restarts.inc.assert_called()

    def test_gpu_utilization_metrics(self):
        """Test GPU utilization metrics."""
        self.test_metrics.update_gpu_utilization("test-job", "A100", 85.5)

        # Verify method was called
        self.test_metrics.gpu_utilization.labels.assert_called_with(job_name="test-job", gpu_type="A100")

    def test_network_bandwidth_metrics(self):
        """Test network bandwidth metrics."""
        self.test_metrics.update_network_bandwidth("test-job", "ingress", 1000.0)
        self.test_metrics.update_network_bandwidth("test-job", "egress", 500.0)

        # Verify methods were called
        assert self.test_metrics.network_bandwidth.labels.call_count >= 2

    def test_cost_estimate_metrics(self):
        """Test cost estimate metrics."""
        self.test_metrics.update_cost_estimate("test-job", "A100", "hourly", 2.50)

        # Verify method was called
        self.test_metrics.cost_estimate.labels.assert_called_with(
            job_name="test-job", gpu_type="A100", time_period="hourly"
        )

    def test_metrics_server_startup(self):
        """Test metrics server startup."""
        with patch("modal_operator.metrics.start_http_server") as mock_server:
            self.test_metrics.start_metrics_server(port=8081)
            mock_server.assert_called_once_with(8081)

    def test_job_without_gpu_type(self):
        """Test job metrics with no GPU type specified."""
        self.test_metrics.record_job_created("cpu-job")

        # Verify method was called with "none" as gpu_type
        self.test_metrics.jobs_total.labels.assert_called()

    def test_multiple_jobs_tracking(self):
        """Test tracking multiple concurrent jobs."""
        # Create multiple jobs
        self.test_metrics.record_job_created("job1", "A100")
        self.test_metrics.record_job_created("job2", "T4")
        self.test_metrics.record_job_created("job3", "A100")

        # Complete one job
        self.test_metrics.record_job_completed("job1", "succeeded", "A100")

        # Verify tracking works
        assert self.test_metrics.jobs_total.labels.call_count >= 4

    def test_i6pn_networking_metrics(self):
        """Test i6pn networking metrics."""
        # Create jobs with different replica counts and i6pn settings
        self.test_metrics.record_job_created("single-job", "T4", replicas=1, enable_i6pn=False)
        self.test_metrics.record_job_created("cluster-job", "A100", replicas=4, enable_i6pn=True)

        # Verify i6pn metrics only recorded for enabled jobs
        self.test_metrics.i6pn_jobs.labels.assert_called_with(replicas="4")

    def test_global_metrics_instance(self):
        """Test global metrics instance is available."""
        assert metrics is not None
        assert isinstance(metrics, ModalOperatorMetrics)

    def test_metrics_attributes_exist(self):
        """Test that all expected metrics attributes exist."""
        expected_attrs = [
            "jobs_total",
            "jobs_active",
            "job_duration",
            "replica_count",
            "gpu_utilization",
            "i6pn_jobs",
            "errors_total",
            "job_queue_time",
            "function_cold_starts",
            "network_bandwidth",
            "cost_estimate",
            "operator_restarts",
            "webhook_requests",
        ]

        for attr in expected_attrs:
            assert hasattr(self.test_metrics, attr), f"Missing attribute: {attr}"

    def test_job_lifecycle_complete(self):
        """Test complete job lifecycle with all metrics."""
        job_name = "lifecycle-test"

        # Queue job
        self.test_metrics.record_job_queued(job_name)

        # Create job
        self.test_metrics.record_job_created(job_name, "A100", replicas=2, enable_i6pn=True)

        # Start job
        self.test_metrics.record_job_started(job_name, "A100")

        # Record cold start
        self.test_metrics.record_cold_start(job_name, "A100")

        # Update utilization
        self.test_metrics.update_gpu_utilization(job_name, "A100", 90.0)

        # Update bandwidth
        self.test_metrics.update_network_bandwidth(job_name, "ingress", 2000.0)

        # Update cost
        self.test_metrics.update_cost_estimate(job_name, "A100", "hourly", 5.0)

        # Complete job
        self.test_metrics.record_job_completed(job_name, "succeeded", "A100")

        # Verify all tracking worked
        assert job_name not in self.test_metrics._job_start_times
        assert job_name not in self.test_metrics._job_queue_times
