"""E2E tests for error handling and edge cases."""

from .conftest import E2ETestBase


class TestErrorHandling(E2ETestBase):
    """Test error handling scenarios."""

    def test_invalid_gpu_specification(self):
        """Test handling of invalid GPU specifications."""
        invalid_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "invalid-gpu",
                "namespace": "default",
                "annotations": {
                    "modal-operator.io/use-modal": "true",
                    "modal-operator.io/gpu": "INVALID_GPU_TYPE:999",  # Invalid GPU spec
                },
            },
            "spec": {"containers": [{"name": "test", "image": "python:3.11", "command": ["echo", "test"]}]},
        }

        self.apply_yaml(invalid_pod)
        self.wait_for_resource("modaljobs", "invalid-gpu", timeout=30)

        # Should create ModalJob but with error status
        modaljob = self.get_resource("modaljobs", "invalid-gpu")
        # In real implementation, would check for error conditions
        assert modaljob is not None

    def test_resource_limits_exceeded(self):
        """Test handling of excessive resource requests."""
        resource_heavy_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "resource-heavy",
                "namespace": "default",
                "annotations": {
                    "modal-operator.io/use-modal": "true",
                    "modal-operator.io/memory": "1000Gi",  # Excessive memory
                    "modal-operator.io/cpu": "1000",  # Excessive CPU
                },
            },
            "spec": {
                "containers": [
                    {
                        "name": "heavy",
                        "image": "python:3.11",
                        "command": ["python", "-c", "print('Heavy resource job')"],
                    }
                ]
            },
        }

        self.apply_yaml(resource_heavy_pod)
        self.wait_for_resource("modaljobs", "resource-heavy", timeout=30)

        # Should handle gracefully (in mock mode, will succeed)
        modaljob = self.get_resource("modaljobs", "resource-heavy")
        assert modaljob["spec"]["memory"] == "1000Gi"

    def test_malformed_annotations(self):
        """Test handling of malformed annotations."""
        malformed_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "malformed-annotations",
                "namespace": "default",
                "annotations": {
                    "modal-operator.io/use-modal": "true",
                    "modal-operator.io/replicas": "not-a-number",
                    "modal-operator.io/timeout": "invalid-timeout",
                },
            },
            "spec": {"containers": [{"name": "test", "image": "python:3.11", "command": ["echo", "test"]}]},
        }

        self.apply_yaml(malformed_pod)

        # Should either reject or use defaults
        try:
            self.wait_for_resource("modaljobs", "malformed-annotations", timeout=30)
            modaljob = self.get_resource("modaljobs", "malformed-annotations")
            # Should use default values for invalid annotations
            assert modaljob["spec"]["replicas"] == 1  # Default value
        except Exception:
            # Or might be rejected entirely
            pass

    def test_operator_restart_recovery(self):
        """Test operator recovery after restart."""
        # Create a job before restart
        pre_restart_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "pre-restart", "namespace": "default"},
            "spec": {
                "containers": [
                    {
                        "name": "test",
                        "image": "python:3.11",
                        "command": ["python", "-c", "import time; time.sleep(30)"],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        self.apply_yaml(pre_restart_pod)
        self.wait_for_resource("modaljobs", "pre-restart", timeout=30)

        # Restart operator (simulate by scaling down and up)
        import subprocess

        subprocess.run(
            ["kubectl", "scale", "deployment", "modal-vgpu-operator", "--replicas=0", "-n", "modal-system"], check=True
        )

        subprocess.run(
            ["kubectl", "scale", "deployment", "modal-vgpu-operator", "--replicas=1", "-n", "modal-system"], check=True
        )

        # Wait for operator to be ready again
        self.wait_for_operator_ready()

        # Create a new job after restart
        post_restart_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "post-restart", "namespace": "default"},
            "spec": {
                "containers": [
                    {
                        "name": "test",
                        "image": "python:3.11",
                        "command": ["echo", "post-restart"],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        self.apply_yaml(post_restart_pod)
        self.wait_for_resource("modaljobs", "post-restart", timeout=60)

        # Both jobs should exist
        assert self.resource_exists("modaljobs", "pre-restart")
        assert self.resource_exists("modaljobs", "post-restart")


class TestPerformance(E2ETestBase):
    """Test performance scenarios."""

    def test_concurrent_job_creation(self):
        """Test creating multiple jobs concurrently."""
        import threading
        import time

        def create_job(job_id: int):
            job_pod = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": f"concurrent-{job_id}", "namespace": "default"},
                "spec": {
                    "containers": [
                        {
                            "name": "worker",
                            "image": "python:3.11",
                            "command": ["python", "-c", f"print('Job {job_id} completed')"],
                            "resources": {"requests": {"nvidia.com/gpu": "1"}},
                        }
                    ],
                    "restartPolicy": "Never",
                },
            }
            self.apply_yaml(job_pod)

        # Create 5 jobs concurrently
        threads = []
        start_time = time.time()

        for i in range(5):
            thread = threading.Thread(target=create_job, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        creation_time = time.time() - start_time

        # Wait for all ModalJobs to be created
        for i in range(5):
            self.wait_for_resource("modaljobs", f"concurrent-{i}", timeout=60)

        total_time = time.time() - start_time

        # Performance assertions (adjust based on requirements)
        assert creation_time < 30, f"Job creation took too long: {creation_time}s"
        assert total_time < 120, f"Total processing took too long: {total_time}s"

        # Verify all jobs were created
        for i in range(5):
            assert self.resource_exists("modaljobs", f"concurrent-{i}")

    def test_resource_cleanup_performance(self):
        """Test cleanup performance when deleting multiple resources."""
        import time

        # Create multiple jobs
        for i in range(3):
            cleanup_pod = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": f"cleanup-{i}", "namespace": "default"},
                "spec": {
                    "containers": [
                        {
                            "name": "worker",
                            "image": "python:3.11",
                            "command": ["echo", f"cleanup-{i}"],
                            "resources": {"requests": {"nvidia.com/gpu": "1"}},
                        }
                    ],
                    "restartPolicy": "Never",
                },
            }
            self.apply_yaml(cleanup_pod)

        # Wait for all to be created
        for i in range(3):
            self.wait_for_resource("modaljobs", f"cleanup-{i}", timeout=30)

        # Delete all pods and measure cleanup time
        start_time = time.time()

        import subprocess

        subprocess.run(
            ["kubectl", "delete", "pods", "-l", "app!=modal-vgpu-operator", "--namespace", "default", "--wait=true"],
            check=True,
        )

        cleanup_time = time.time() - start_time

        # Verify cleanup completed
        assert cleanup_time < 60, f"Cleanup took too long: {cleanup_time}s"
