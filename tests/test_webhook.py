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

        # New implementation generates multiple patches (container, networking, annotations, labels)
        assert len(patches) >= 5  # At least: containers, networking-annotation, dns, volume, mutated-annotation

        # Check container replacement patch (replaces entire containers array)
        container_patch = patches[0]
        assert container_patch["op"] == "replace"
        assert container_patch["path"] == "/spec/containers"

        # Should have logger and proxy containers
        assert len(container_patch["value"]) == 2
        logger_container = container_patch["value"][0]
        proxy_container = container_patch["value"][1]

        # Both containers use the same operator image with different commands
        assert logger_container["image"] == "ghcr.io/solanyn/modal-operator:latest"
        assert proxy_container["image"] == "ghcr.io/solanyn/modal-operator:latest"

        # Verify different commands (using console scripts)
        assert logger_container["command"] == ["modal-logger"]
        assert proxy_container["command"] == ["modal-proxy"]

        # Check environment variables (plural arrays now)
        env_vars = logger_container["env"]
        assert any(env["name"] == "MODAL_EXECUTION" and env["value"] == "true" for env in env_vars)
        assert any(env["name"] == "ORIGINAL_IMAGES" for env in env_vars)  # Note: plural

        # Verify original image is stored in ORIGINAL_IMAGES array
        original_images_env = next(env for env in env_vars if env["name"] == "ORIGINAL_IMAGES")
        original_images = json.loads(original_images_env["value"])
        assert original_images == ["python:3.11-slim"]

        # Check mutated annotation exists
        annotation_patches = [p for p in patches if "modal-operator.io~1mutated" in p.get("path", "")]
        assert len(annotation_patches) == 1
        assert annotation_patches[0]["value"] == "true"

    def test_mutate_pod_without_annotation(self):
        """Test webhook mutates pod when called (objectSelector filters upstream)."""
        # Note: The webhook relies on objectSelector in the webhook configuration
        # to filter which pods reach it. When the webhook is called, it always mutates.
        admission_request = {
            "uid": "test-uid-456",
            "object": {
                "metadata": {"name": "regular-pod", "namespace": "default", "annotations": {}},
                "spec": {"containers": [{"name": "regular-container", "image": "nginx:latest"}]},
            },
        }

        response = self.webhook.mutate_pod(admission_request)

        # Webhook always mutates when called (filtering happens via objectSelector)
        assert response["apiVersion"] == "admission.k8s.io/v1"
        assert response["kind"] == "AdmissionReview"
        assert response["response"]["uid"] == "test-uid-456"
        assert response["response"]["allowed"] is True
        assert "patch" in response["response"]  # Always mutates
        assert response["response"]["patchType"] == "JSONPatch"

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

        # Verify original images are preserved in env var (note: plural)
        import base64

        patch_data = base64.b64decode(response["response"]["patch"]).decode()
        patches = json.loads(patch_data)
        container_patch = patches[0]
        env_vars = container_patch["value"][0]["env"]  # First container (logger)
        original_images_env = next(env for env in env_vars if env["name"] == "ORIGINAL_IMAGES")
        original_images = json.loads(original_images_env["value"])
        assert original_images == ["alpine:latest"]

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

    @patch("modal_operator.controllers.webhook_controller.logger")
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
