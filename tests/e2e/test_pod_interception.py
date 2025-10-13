"""E2E tests for pod interception and basic operator functionality."""

import pytest

from .conftest import E2ETestBase


class TestPodInterception(E2ETestBase):
    """Test basic pod interception functionality."""

    def test_gpu_pod_interception(self):
        """Test that GPU pods are intercepted and converted to ModalJobs."""
        gpu_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "gpu-test", "namespace": "default"},
            "spec": {
                "containers": [
                    {
                        "name": "gpu-container",
                        "image": "nvidia/cuda:11.8-runtime-ubuntu20.04",
                        "command": ["nvidia-smi"],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}, "limits": {"nvidia.com/gpu": "1"}},
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        # Apply GPU pod
        self.apply_yaml(gpu_pod)

        # Wait for ModalJob creation
        self.wait_for_resource("modaljobs", "gpu-test", timeout=30)

        # Verify ModalJob was created with correct spec
        modaljob = self.get_resource("modaljobs", "gpu-test")
        assert modaljob["spec"]["image"] == "nvidia/cuda:11.8-runtime-ubuntu20.04"
        assert modaljob["spec"]["command"] == ["nvidia-smi"]

        # Verify original pod was modified (mirror pod)
        pod = self.get_resource("pods", "gpu-test")
        assert "modal.com" in pod["spec"]["nodeName"]

    def test_annotation_based_offloading(self):
        """Test offloading via modal-operator.io/offload annotation."""
        annotated_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "annotated-test",
                "namespace": "default",
                "annotations": {"modal-operator.io/offload": "true"},
            },
            "spec": {
                "containers": [
                    {"name": "app", "image": "python:3.11", "command": ["python", "-c", "print('Hello Modal')"]}
                ],
                "restartPolicy": "Never",
            },
        }

        self.apply_yaml(annotated_pod)
        self.wait_for_resource("modaljobs", "annotated-test", timeout=30)

        modaljob = self.get_resource("modaljobs", "annotated-test")
        assert modaljob["spec"]["image"] == "python:3.11"

    def test_modal_container_mode(self):
        """Test Modal container mode with custom specifications."""
        modal_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "modal-container",
                "namespace": "default",
                "annotations": {
                    "modal-operator.io/use-modal": "true",
                    "modal-operator.io/image": "pytorch/pytorch:latest",
                    "modal-operator.io/command": "python -c 'import torch; print(torch.__version__)'",
                    "modal-operator.io/gpu": "T4:1",
                    "modal-operator.io/memory": "2Gi",
                },
            },
            "spec": {"containers": [{"name": "placeholder", "image": "busybox", "command": ["sleep", "infinity"]}]},
        }

        self.apply_yaml(modal_pod)
        self.wait_for_resource("modaljobs", "modal-container", timeout=30)

        modaljob = self.get_resource("modaljobs", "modal-container")
        assert modaljob["spec"]["image"] == "pytorch/pytorch:latest"
        assert modaljob["spec"]["gpu"] == "T4:1"
        assert modaljob["spec"]["memory"] == "2Gi"

    def test_non_gpu_pod_passthrough(self):
        """Test that regular pods are not intercepted."""
        regular_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "regular-test", "namespace": "default"},
            "spec": {"containers": [{"name": "app", "image": "nginx", "ports": [{"containerPort": 80}]}]},
        }

        self.apply_yaml(regular_pod)

        # Wait a bit to ensure no ModalJob is created
        import time

        time.sleep(10)

        # Verify no ModalJob was created
        with pytest.raises(Exception):  # Should not exist
            self.get_resource("modaljobs", "regular-test")

        # Verify pod runs normally
        pod = self.get_resource("pods", "regular-test")
        assert "modal.com" not in pod.get("spec", {}).get("nodeName", "")

    def test_status_synchronization(self):
        """Test Modal job status synchronization to pod status."""
        gpu_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "status-test", "namespace": "default"},
            "spec": {
                "containers": [
                    {
                        "name": "test",
                        "image": "python:3.11",
                        "command": ["python", "-c", "import time; time.sleep(5); print('Done')"],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        self.apply_yaml(gpu_pod)
        self.wait_for_resource("modaljobs", "status-test", timeout=30)

        # In mock mode, job should complete quickly
        # Wait for status updates
        self.wait_for_condition(
            lambda: self.get_resource("pods", "status-test")["status"]["phase"] in ["Succeeded", "Failed"],
            timeout=60,
            message="Pod status should be updated from Modal job",
        )
