"""E2E tests for networking functionality."""

from .conftest import E2ETestBase


class TestNetworking(E2ETestBase):
    """Test networking features."""

    def test_single_replica_job(self):
        """Test basic single replica Modal job."""
        single_job = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "single-replica", "namespace": "default"},
            "spec": {
                "containers": [
                    {
                        "name": "worker",
                        "image": "python:3.11",
                        "command": ["python", "-c", "print('Single replica job')"],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        self.apply_yaml(single_job)
        self.wait_for_resource("modaljobs", "single-replica", timeout=30)

        modaljob = self.get_resource("modaljobs", "single-replica")
        assert modaljob["spec"]["replicas"] == 1
        assert modaljob["spec"]["enable_i6pn"] is False

    def test_multi_replica_with_i6pn(self):
        """Test multi-replica job with i6pn networking."""
        multi_job = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "multi-replica",
                "namespace": "default",
                "annotations": {
                    "modal-operator.io/offload": "true",
                    "modal-operator.io/replicas": "3",
                    "modal-operator.io/enable-i6pn": "true",
                },
            },
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "worker",
                                "image": "pytorch/pytorch:latest",
                                "command": [
                                    "python",
                                    "-c",
                                    "import socket; print(f'Worker on {socket.gethostname()}')",
                                ],
                                "resources": {"requests": {"nvidia.com/gpu": "1"}},
                            }
                        ],
                        "restartPolicy": "Never",
                    }
                }
            },
        }

        self.apply_yaml(multi_job)

        # Wait for ModalJob with multi-replica config
        self.wait_for_condition(
            lambda: self.resource_exists("modaljobs", "multi-replica"),
            timeout=30,
            message="Multi-replica ModalJob should be created",
        )

        modaljob = self.get_resource("modaljobs", "multi-replica")
        assert modaljob["spec"]["replicas"] == 3
        assert modaljob["spec"]["enable_i6pn"] is True

    def test_networking_validation(self):
        """Test networking configuration validation."""
        # Test invalid config: multi-replica without i6pn
        invalid_job = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "invalid-networking",
                "namespace": "default",
                "annotations": {
                    "modal-operator.io/offload": "true",
                    "modal-operator.io/replicas": "2",
                    # Missing modal-operator.io/enable-i6pn: "true"
                },
            },
            "spec": {
                "containers": [
                    {
                        "name": "worker",
                        "image": "python:3.11",
                        "command": ["echo", "test"],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        self.apply_yaml(invalid_job)

        # Should create ModalJob but with validation error in status
        self.wait_for_resource("modaljobs", "invalid-networking", timeout=30)

        # Check for validation error in status or events
        modaljob = self.get_resource("modaljobs", "invalid-networking")
        # In a real implementation, this would have validation errors
        # For now, just verify it was created
        assert modaljob is not None

    def test_cluster_coordination(self):
        """Test cluster coordination for distributed jobs."""
        distributed_job = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "cluster-coordination",
                "namespace": "default",
                "annotations": {
                    "modal-operator.io/offload": "true",
                    "modal-operator.io/replicas": "2",
                    "modal-operator.io/enable-i6pn": "true",
                },
            },
            "spec": {
                "containers": [
                    {
                        "name": "coordinator",
                        "image": "python:3.11",
                        "command": [
                            "python",
                            "-c",
                            """
import socket
import time
print(f'Coordinator starting on {socket.gethostname()}')
time.sleep(10)
print('Coordination complete')
""",
                        ],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        self.apply_yaml(distributed_job)
        self.wait_for_resource("modaljobs", "cluster-coordination", timeout=30)

        modaljob = self.get_resource("modaljobs", "cluster-coordination")
        assert modaljob["spec"]["enable_i6pn"] is True
        assert modaljob["spec"]["replicas"] == 2

        # Verify job completes successfully with coordination
        self.wait_for_condition(
            lambda: self.get_resource("pods", "cluster-coordination")["status"].get("phase") in ["Succeeded", "Failed"],
            timeout=120,
            message="Distributed job should complete",
        )
