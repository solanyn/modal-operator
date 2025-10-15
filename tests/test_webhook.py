"""Tests for mutating admission webhook functionality."""

import json
from unittest.mock import Mock, patch

from kubernetes import client

from modal_operator.controllers.webhook_controller import ModalWebhookController


class TestModalWebhookController:
    """Test cases for ModalWebhookController."""

    def setup_method(self):
        """Set up test fixtures."""
        self.k8s_client = Mock(spec=client.CoreV1Api)
        self.webhook = ModalWebhookController(self.k8s_client)

    def test_mutate_pod_with_offload_annotation(self):
        """Test pod mutation with modal-operator.io/offload annotation."""
        admission_request = {
            "uid": "test-uid-123",
            "object": {
                "metadata": {
                    "name": "test-pod",
                    "namespace": "default",
                    "annotations": {"modal-operator.io/offload": "true"},
                },
                "spec": {
                    "containers": [
                        {
                            "name": "test-container",
                            "image": "python:3.11-slim",
                            "command": ["python", "-c", "print('test')"],
                            "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}},
                        }
                    ]
                },
            },
        }

        response = self.webhook.mutate_pod(admission_request)

        # Verify response structure
        assert response["apiVersion"] == "admission.k8s.io/v1"
        assert response["kind"] == "AdmissionReview"
        assert response["response"]["uid"] == "test-uid-123"
        assert response["response"]["allowed"] is True
        assert "patchType" in response["response"]
        assert response["response"]["patchType"] == "JSONPatch"
        assert "patch" in response["response"]

        # Decode and verify patches
        import base64

        patch_data = base64.b64decode(response["response"]["patch"]).decode()
        patches = json.loads(patch_data)

        # Should have container replacement and annotation patches
        assert len(patches) == 2

        # Check container replacement patch
        container_patch = patches[0]
        assert container_patch["op"] == "replace"
        assert container_patch["path"] == "/spec/containers/0"
        assert container_patch["value"]["image"] == "busybox:latest"
        assert container_patch["value"]["command"] == ["sh", "-c"]
        assert "Running on Modal via webhook mutation" in container_patch["value"]["args"][0]

        # Check environment variables
        env_vars = container_patch["value"]["env"]
        assert any(env["name"] == "MODAL_EXECUTION" and env["value"] == "true" for env in env_vars)
        assert any(env["name"] == "ORIGINAL_IMAGE" and env["value"] == "python:3.11-slim" for env in env_vars)

        # Check annotation patch
        annotation_patch = patches[1]
        assert annotation_patch["op"] == "add"
        assert annotation_patch["path"] == "/metadata/annotations/modal-operator.io~1mutated"
        assert annotation_patch["value"] == "true"

    def test_mutate_pod_without_annotation(self):
        """Test pod is allowed through without mutation when no annotation."""
        admission_request = {
            "uid": "test-uid-456",
            "object": {
                "metadata": {"name": "regular-pod", "namespace": "default", "annotations": {}},
                "spec": {"containers": [{"name": "regular-container", "image": "nginx:latest"}]},
            },
        }

        response = self.webhook.mutate_pod(admission_request)

        # Should allow without mutation
        assert response["apiVersion"] == "admission.k8s.io/v1"
        assert response["kind"] == "AdmissionReview"
        assert response["response"]["uid"] == "test-uid-456"
        assert response["response"]["allowed"] is True
        assert "patch" not in response["response"]
        assert "Pod does not need Modal mutation" in response["response"]["status"]["message"]

    def test_mutate_pod_with_use_modal_annotation(self):
        """Test pod mutation with modal-operator.io/use-modal annotation."""
        admission_request = {
            "uid": "test-uid-789",
            "object": {
                "metadata": {
                    "name": "modal-pod",
                    "namespace": "default",
                    "annotations": {"modal-operator.io/use-modal": "true"},
                },
                "spec": {
                    "containers": [{"name": "modal-container", "image": "alpine:latest", "command": ["echo", "hello"]}]
                },
            },
        }

        response = self.webhook.mutate_pod(admission_request)

        # Should mutate the pod
        assert response["response"]["allowed"] is True
        assert "patchType" in response["response"]

        # Verify original image is preserved in env var
        import base64

        patch_data = base64.b64decode(response["response"]["patch"]).decode()
        patches = json.loads(patch_data)
        container_patch = patches[0]
        env_vars = container_patch["value"]["env"]
        assert any(env["name"] == "ORIGINAL_IMAGE" and env["value"] == "alpine:latest" for env in env_vars)

    def test_mutate_pod_error_handling(self):
        """Test webhook error handling for malformed requests."""
        # Missing required fields
        admission_request = {
            "uid": "test-uid-error",
            "object": {
                "metadata": {
                    "name": "broken-pod"
                    # Missing namespace and other required fields
                }
            },
        }

        response = self.webhook.mutate_pod(admission_request)

        # Should deny with error message
        assert response["apiVersion"] == "admission.k8s.io/v1"
        assert response["kind"] == "AdmissionReview"
        assert response["response"]["uid"] == "test-uid-error"
        assert response["response"]["allowed"] is False
        assert "Mutation failed" in response["response"]["status"]["message"]

    @patch("modal_operator.webhook.logger")
    def test_mutation_logging(self, mock_logger):
        """Test that mutation activities are properly logged."""
        admission_request = {
            "uid": "test-uid-logging",
            "object": {
                "metadata": {
                    "name": "logging-test-pod",
                    "namespace": "default",
                    "annotations": {"modal-operator.io/offload": "true"},
                },
                "spec": {"containers": [{"name": "test", "image": "python:3.11"}]},
            },
        }

        self.webhook.mutate_pod(admission_request)

        # Verify logging was called
        mock_logger.info.assert_called_with("Mutating pod logging-test-pod for Modal execution")


class TestPodTemplateMirror:
    """Test cases for PodTemplateMirror functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        from modal_operator.controllers.pod_mirror import PodTemplateMirror

        self.pod_mirror = PodTemplateMirror()

    def test_should_mirror_pod_with_offload_annotation(self):
        """Test pod detection with offload annotation."""
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="test-pod", annotations={"modal-operator.io/offload": "true"}),
            spec=client.V1PodSpec(containers=[client.V1Container(name="test", image="python:3.11")]),
        )

        assert self.pod_mirror.should_mirror_pod(pod) is True

    def test_should_mirror_pod_with_use_modal_annotation(self):
        """Test pod detection with use-modal annotation."""
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="test-pod", annotations={"modal-operator.io/use-modal": "true"}),
            spec=client.V1PodSpec(containers=[client.V1Container(name="test", image="python:3.11")]),
        )

        assert self.pod_mirror.should_mirror_pod(pod) is True

    def test_should_not_mirror_pod_without_annotation(self):
        """Test pod is not mirrored without annotations."""
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name="regular-pod", annotations={}),
            spec=client.V1PodSpec(containers=[client.V1Container(name="test", image="nginx:latest")]),
        )

        assert self.pod_mirror.should_mirror_pod(pod) is False
