"""Tests for PodTemplateMirror."""

import pytest
from unittest.mock import Mock

from kubernetes import client

from modal_operator.controllers.pod_mirror import PodTemplateMirror


class TestPodTemplateMirror:
    """Test cases for PodTemplateMirror."""

    @pytest.fixture
    def pod_mirror(self):
        """PodTemplateMirror instance."""
        return PodTemplateMirror()

    def test_should_mirror_pod_with_annotation(self, pod_mirror):
        """Test should_mirror_pod with explicit Modal annotation."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.annotations = {"modal-operator.io/use-modal": "true"}

        result = pod_mirror.should_mirror_pod(pod)

        assert result is True

    def test_should_mirror_pod_with_gpu_requests(self, pod_mirror):
        """Test should_mirror_pod with GPU requests."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.annotations = {}
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]
        pod.spec.containers[0].resources = Mock(spec=client.V1ResourceRequirements)
        pod.spec.containers[0].resources.requests = {"nvidia.com/gpu": "1"}

        result = pod_mirror.should_mirror_pod(pod)

        assert result is True

    def test_should_mirror_pod_without_indicators(self, pod_mirror):
        """Test should_mirror_pod without Modal indicators."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.annotations = {}
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]
        pod.spec.containers[0].resources = None

        result = pod_mirror.should_mirror_pod(pod)

        assert result is False

    def test_extract_modal_spec_basic(self, pod_mirror):
        """Test basic Modal spec extraction."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.annotations = {"modal-operator.io/use-modal": "true", "modal-operator.io/timeout": "600"}
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]
        pod.spec.containers[0].image = "pytorch/pytorch:latest"
        pod.spec.containers[0].command = ["python", "-c", "print('hello')"]
        pod.spec.containers[0].args = ["--verbose"]
        pod.spec.containers[0].resources = Mock(spec=client.V1ResourceRequirements)
        pod.spec.containers[0].resources.requests = {"cpu": "500m", "memory": "1Gi", "nvidia.com/gpu": "1"}
        pod.spec.containers[0].env = [Mock(name="TEST_VAR", value="test_value")]
        pod.spec.containers[0].env[0].name = "TEST_VAR"
        pod.spec.containers[0].env[0].value = "test_value"

        spec = pod_mirror.extract_modal_spec(pod)

        assert spec["image"] == "pytorch/pytorch:latest"
        assert spec["command"] == ["python", "-c", "print('hello')"]
        assert spec["args"] == ["--verbose"]
        assert spec["cpu"] == "0.5"  # 500m converted to float
        assert spec["memory"] == "1Gi"
        assert spec["gpu"] == "T4:1"  # Default GPU type
        assert spec["timeout"] == 600
        assert spec["env"]["TEST_VAR"] == "test_value"

    def test_extract_modal_spec_with_annotations(self, pod_mirror):
        """Test Modal spec extraction with annotation overrides."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.annotations = {
            "modal-operator.io/use-modal": "true",
            "modal-operator.io/image": "custom-image:latest",
            "modal-operator.io/command": "python train.py",
            "modal-operator.io/gpu": "A100:2",
            "modal-operator.io/env-CUSTOM_VAR": "custom_value",
        }
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]
        pod.spec.containers[0].image = "original-image:latest"
        pod.spec.containers[0].command = None
        pod.spec.containers[0].args = None
        pod.spec.containers[0].resources = None
        pod.spec.containers[0].env = None

        spec = pod_mirror.extract_modal_spec(pod)

        assert spec["image"] == "custom-image:latest"  # Annotation override
        assert spec["command"] == ["sh", "-c", "python train.py"]  # String converted to command
        assert spec["gpu"] == "A100:2"  # Annotation override
        assert spec["env"]["CUSTOM_VAR"] == "custom_value"  # From annotation

    def test_get_primary_container_with_gpu(self, pod_mirror):
        """Test getting primary container with GPU requests."""
        pod = Mock(spec=client.V1Pod)
        pod.spec = Mock(spec=client.V1PodSpec)

        # First container without GPU
        container1 = Mock(spec=client.V1Container)
        container1.resources = Mock(spec=client.V1ResourceRequirements)
        container1.resources.requests = {"cpu": "100m"}

        # Second container with GPU
        container2 = Mock(spec=client.V1Container)
        container2.resources = Mock(spec=client.V1ResourceRequirements)
        container2.resources.requests = {"nvidia.com/gpu": "1"}

        pod.spec.containers = [container1, container2]

        result = pod_mirror._get_primary_container(pod)

        assert result == container2  # GPU container selected

    def test_extract_cpu_from_resources(self, pod_mirror):
        """Test CPU extraction from container resources."""
        container = Mock(spec=client.V1Container)
        container.resources = Mock(spec=client.V1ResourceRequirements)
        container.resources.requests = {"cpu": "250m"}

        result = pod_mirror._extract_cpu(container, {})

        assert result == "0.25"  # 250m converted to float

    def test_extract_memory_from_resources(self, pod_mirror):
        """Test memory extraction from container resources."""
        container = Mock(spec=client.V1Container)
        container.resources = Mock(spec=client.V1ResourceRequirements)
        container.resources.requests = {"memory": "2Gi"}

        result = pod_mirror._extract_memory(container, {})

        assert result == "2Gi"

    def test_extract_gpu_from_resources(self, pod_mirror):
        """Test GPU extraction from container resources."""
        container = Mock(spec=client.V1Container)
        container.resources = Mock(spec=client.V1ResourceRequirements)
        container.resources.requests = {"nvidia.com/gpu": "2"}

        result = pod_mirror._extract_gpu(container, {})

        assert result == "T4:2"  # Default GPU type with count
