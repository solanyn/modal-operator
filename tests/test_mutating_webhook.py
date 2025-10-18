"""Tests for ModalWebhookController."""

import pytest
from unittest.mock import Mock

from kubernetes import client

from modal_operator.controllers.webhook_controller import ModalWebhookController


class TestModalWebhookController:
    """Test cases for ModalWebhookController."""

    @pytest.fixture
    def mock_k8s_client(self):
        """Mock Kubernetes client."""
        return Mock(spec=client.CoreV1Api)

    @pytest.fixture
    def webhook(self, mock_k8s_client):
        """ModalWebhookController instance with mocked client."""
        return ModalWebhookController(mock_k8s_client)

    def test_mutate_pod_with_modal_annotation(self, webhook, mock_k8s_client):
        """Test pod mutation with Modal annotation."""
        admission_request = {
            "uid": "test-uid",
            "object": {
                "metadata": {
                    "name": "test-pod",
                    "namespace": "default",
                    "uid": "test-uid",
                    "annotations": {"modal-operator.io/use-modal": "true"},
                },
                "spec": {
                    "containers": [
                        {
                            "name": "test-container",
                            "image": "pytorch/pytorch:latest",
                            "command": ["python", "-c", "print('hello')"],
                            "resources": {"requests": {"nvidia.com/gpu": "1"}},
                        }
                    ]
                },
            },
        }

        response = webhook.mutate_pod(admission_request)

        assert response["response"]["allowed"] is True
        assert "patch" in response["response"]
        assert response["response"]["patchType"] == "JSONPatch"

    def test_mutate_pod_without_modal_indicators(self, webhook):
        """Test pod mutation - webhook now always mutates due to objectSelector."""
        admission_request = {
            "uid": "test-uid-2",
            "object": {
                "metadata": {"name": "test-pod", "namespace": "default", "annotations": {}},
                "spec": {"containers": [{"name": "test-container", "image": "nginx:latest"}]},
            },
        }

        response = webhook.mutate_pod(admission_request)

        # With objectSelector, webhook only receives pods that need mutation
        # So all pods that reach this handler will be mutated
        assert response["response"]["allowed"] is True
        assert "patch" in response["response"]

    def test_generate_mutation_patches_replaces_containers(self, webhook):
        """Test that mutation patches replace containers with Modal logger and proxy."""
        pod_dict = {
            "metadata": {"name": "test-pod", "namespace": "default", "annotations": {}},
            "spec": {
                "containers": [
                    {
                        "name": "test-container",
                        "image": "pytorch/pytorch:latest",
                        "command": ["python"],
                        "args": ["-c", "print('hello')"],
                    }
                ]
            },
        }

        patches = webhook._generate_mutation_patches(pod_dict, "", None)

        # Find container replacement patch
        container_patch = next((p for p in patches if p["path"] == "/spec/containers"), None)
        assert container_patch is not None
        assert container_patch["op"] == "replace"
        assert len(container_patch["value"]) == 2  # logger + proxy
        assert container_patch["value"][0]["image"] == "modal-operator/logger:latest"
        assert container_patch["value"][1]["image"] == "modal-operator/proxy:latest"

    def test_generate_mutation_patches_preserves_networking_config(self, webhook):
        """Test that mutation patches preserve original networking configuration."""
        pod_dict = {
            "metadata": {"name": "test-pod", "namespace": "default", "annotations": {}},
            "spec": {
                "hostNetwork": True,
                "dnsPolicy": "ClusterFirstWithHostNet",
                "containers": [{"name": "test-container", "image": "nginx:latest"}],
            },
        }

        patches = webhook._generate_mutation_patches(pod_dict, "", None)

        # Find networking annotation patch
        networking_patch = next((p for p in patches if "original-networking" in p["path"]), None)
        assert networking_patch is not None

        # Verify hostNetwork is disabled for placeholder
        host_network_patch = next((p for p in patches if p["path"] == "/spec/hostNetwork"), None)
        assert host_network_patch is not None
        assert host_network_patch["value"] is False

    def test_generate_mutation_patches_adds_volumes(self, webhook):
        """Test generation of mutation patches adds Modal secret volume."""
        pod_dict = {
            "metadata": {"name": "test-pod", "namespace": "default", "annotations": {}},
            "spec": {"containers": [{"name": "original-container", "image": "nginx:latest"}]},
        }

        patches = webhook._generate_mutation_patches(pod_dict, "", None)

        # Check that modal-secret volume is added
        volume_patch = next((p for p in patches if p["path"] == "/spec/volumes/-"), None)
        assert volume_patch is not None
        assert volume_patch["op"] == "add"
        assert volume_patch["value"]["name"] == "modal-secret"
        assert volume_patch["value"]["secret"]["secretName"] == "modal-token"

    def test_generate_mutation_patches_adds_annotations(self, webhook):
        """Test generation of mutation patches adds Modal annotations."""
        pod_dict = {
            "metadata": {"name": "test-pod", "namespace": "default", "annotations": {}},
            "spec": {"containers": [{"name": "test-container", "image": "nginx:latest"}]},
        }

        patches = webhook._generate_mutation_patches(pod_dict, "", None)

        # Check for mutation annotations
        mutated_patch = next((p for p in patches if "mutated" in p["path"]), None)
        assert mutated_patch is not None
        assert mutated_patch["value"] == "true"

        # Check for tunnel annotation
        tunnel_patch = next((p for p in patches if "tunnel-enabled" in p["path"]), None)
        assert tunnel_patch is not None
        assert tunnel_patch["value"] == "true"

    def test_extract_sensitive_env(self, webhook):
        """Test extraction of sensitive environment variables."""
        pod = Mock(spec=client.V1Pod)
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]

        # Mock environment variables
        env_vars = []

        # Sensitive env var
        sensitive_env = Mock()
        sensitive_env.name = "DATABASE_PASSWORD"
        sensitive_env.value = "secret123"
        env_vars.append(sensitive_env)

        # Non-sensitive env var
        normal_env = Mock()
        normal_env.name = "LOG_LEVEL"
        normal_env.value = "INFO"
        env_vars.append(normal_env)

        pod.spec.containers[0].env = env_vars

        result = webhook._extract_sensitive_env(pod)

        assert "DATABASE_PASSWORD" in result
        assert result["DATABASE_PASSWORD"] == "secret123"
        assert "LOG_LEVEL" not in result  # Not sensitive

    def test_allow_response(self, webhook):
        """Test generation of allow response."""
        response = webhook._allow_response("Test message")

        assert response["response"]["allowed"] is True
        assert response["response"]["status"]["message"] == "Test message"

    def test_deny_response(self, webhook):
        """Test generation of deny response."""
        response = webhook._deny_response("Error message")

        assert response["response"]["allowed"] is False
        assert response["response"]["status"]["message"] == "Error message"
