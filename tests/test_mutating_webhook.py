"""Tests for ModalMutatingWebhook."""

import pytest
from unittest.mock import Mock

from kubernetes import client

from modal_operator.webhook import ModalMutatingWebhook


class TestModalMutatingWebhook:
    """Test cases for ModalMutatingWebhook."""

    @pytest.fixture
    def mock_k8s_client(self):
        """Mock Kubernetes client."""
        return Mock(spec=client.CoreV1Api)

    @pytest.fixture
    def webhook(self, mock_k8s_client):
        """ModalMutatingWebhook instance with mocked client."""
        return ModalMutatingWebhook(mock_k8s_client)

    def test_mutate_pod_with_modal_annotation(self, webhook, mock_k8s_client):
        """Test pod mutation with Modal annotation."""
        admission_request = {
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
            }
        }

        # Mock ConfigMap creation
        mock_k8s_client.create_namespaced_config_map.return_value = None

        response = webhook.mutate_pod(admission_request)

        assert response["response"]["allowed"] is True
        assert "patch" in response["response"]

        # Verify ConfigMap was created
        mock_k8s_client.create_namespaced_config_map.assert_called_once()

    def test_mutate_pod_without_modal_indicators(self, webhook):
        """Test pod mutation without Modal indicators."""
        admission_request = {
            "object": {
                "metadata": {"name": "test-pod", "namespace": "default", "annotations": {}},
                "spec": {"containers": [{"name": "test-container", "image": "nginx:latest"}]},
            }
        }

        response = webhook.mutate_pod(admission_request)

        assert response["response"]["allowed"] is True
        assert "patch" not in response["response"]
        assert "does not need Modal mutation" in response["response"]["status"]["message"]

    def test_create_pod_spec_storage_basic(self, webhook, mock_k8s_client):
        """Test ConfigMap creation for pod spec storage."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.name = "test-pod"
        pod.metadata.namespace = "default"
        pod.metadata.uid = "test-uid"
        pod.metadata.annotations = {"modal-operator.io/use-modal": "true"}
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]
        pod.spec.containers[0].image = "test-image"
        pod.spec.containers[0].command = None
        pod.spec.containers[0].args = None
        pod.spec.containers[0].resources = None
        pod.spec.containers[0].env = None

        mock_k8s_client.create_namespaced_config_map.return_value = None

        config_map_name, secret_name = webhook._create_pod_spec_storage(pod)

        assert config_map_name == "modal-spec-test-pod"
        assert secret_name is None  # No sensitive env vars
        mock_k8s_client.create_namespaced_config_map.assert_called_once()

    def test_create_pod_spec_storage_with_secrets(self, webhook, mock_k8s_client):
        """Test ConfigMap and Secret creation with sensitive env vars."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.name = "test-pod"
        pod.metadata.namespace = "default"
        pod.metadata.uid = "test-uid"
        pod.metadata.annotations = {"modal-operator.io/use-modal": "true"}
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]
        pod.spec.containers[0].image = "test-image"
        pod.spec.containers[0].command = None
        pod.spec.containers[0].args = None
        pod.spec.containers[0].resources = None

        # Mock sensitive env var
        env_var = Mock()
        env_var.name = "DATABASE_PASSWORD"
        env_var.value = "secret123"
        pod.spec.containers[0].env = [env_var]

        mock_k8s_client.create_namespaced_config_map.return_value = None
        mock_k8s_client.create_namespaced_secret.return_value = None

        config_map_name, secret_name = webhook._create_pod_spec_storage(pod)

        assert config_map_name == "modal-spec-test-pod"
        assert secret_name == "modal-env-test-pod"
        mock_k8s_client.create_namespaced_config_map.assert_called_once()
        mock_k8s_client.create_namespaced_secret.assert_called_once()

    def test_generate_mutation_patches_basic(self, webhook):
        """Test generation of basic mutation patches."""
        pod = Mock(spec=client.V1Pod)
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]
        pod.spec.containers[0].name = "original-container"
        pod.spec.volumes = None

        patches = webhook._generate_mutation_patches(pod, "test-config", None)

        assert len(patches) >= 2  # Container replacement + volume addition + annotation

        # Check container replacement patch
        container_patch = next(p for p in patches if p["path"] == "/spec/containers/0")
        assert container_patch["op"] == "replace"
        assert container_patch["value"]["image"] == "modal-operator/proxy:latest"
        assert container_patch["value"]["command"] == ["modal-proxy"]

    def test_generate_mutation_patches_with_secret(self, webhook):
        """Test generation of mutation patches with secret mount."""
        pod = Mock(spec=client.V1Pod)
        pod.spec = Mock(spec=client.V1PodSpec)
        pod.spec.containers = [Mock(spec=client.V1Container)]
        pod.spec.containers[0].name = "original-container"
        pod.spec.volumes = None

        patches = webhook._generate_mutation_patches(pod, "test-config", "test-secret")

        # Check that secret mount is added
        container_patch = next(p for p in patches if p["path"] == "/spec/containers/0")
        volume_mounts = container_patch["value"]["volumeMounts"]

        assert len(volume_mounts) == 2  # Config + Secret mounts
        assert any(vm["name"] == "modal-secrets" for vm in volume_mounts)

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
