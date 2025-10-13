"""Tests for StatusSyncController."""

import pytest
from unittest.mock import Mock

from kubernetes import client

from modal_operator.controllers.status_sync import StatusSyncController


class TestStatusSyncController:
    """Test cases for StatusSyncController."""

    @pytest.fixture
    def mock_k8s_client(self):
        """Mock Kubernetes client."""
        return Mock(spec=client.CoreV1Api)

    @pytest.fixture
    def status_sync_controller(self, mock_k8s_client):
        """StatusSyncController instance with mocked client."""
        return StatusSyncController(mock_k8s_client)

    def test_sync_pod_status_success(self, status_sync_controller, mock_k8s_client):
        """Test successful pod status synchronization."""
        # Mock mirror pod (running)
        mirror_pod = Mock(spec=client.V1Pod)
        mirror_pod.status = Mock(spec=client.V1PodStatus)
        mirror_pod.status.phase = "Running"
        mirror_pod.status.pod_ip = "10.0.0.1"
        mirror_pod.status.start_time = "2023-01-01T00:00:00Z"

        # Mock original pod (pending)
        original_pod = Mock(spec=client.V1Pod)
        original_pod.status = Mock(spec=client.V1PodStatus)
        original_pod.status.phase = "Pending"
        original_pod.spec = Mock(spec=client.V1PodSpec)
        original_pod.spec.containers = [Mock(spec=client.V1Container)]
        original_pod.spec.containers[0].name = "test-container"
        original_pod.spec.containers[0].image = "test-image"

        mock_k8s_client.read_namespaced_pod.side_effect = [mirror_pod, original_pod]

        # Test sync
        result = status_sync_controller.sync_pod_status("original-pod", "mirror-pod", "default")

        assert result is True
        mock_k8s_client.patch_namespaced_pod_status.assert_called_once()

        # Verify patch content
        call_args = mock_k8s_client.patch_namespaced_pod_status.call_args
        patch_body = call_args[1]["body"]
        assert patch_body["status"]["phase"] == "Running"
        assert patch_body["status"]["hostIP"] == "modal.com"

    def test_sync_pod_status_no_change_needed(self, status_sync_controller, mock_k8s_client):
        """Test sync when no status change is needed."""
        # Both pods have same status
        pod_status = Mock(spec=client.V1PodStatus)
        pod_status.phase = "Running"

        mirror_pod = Mock(spec=client.V1Pod)
        mirror_pod.status = pod_status

        original_pod = Mock(spec=client.V1Pod)
        original_pod.status = pod_status

        mock_k8s_client.read_namespaced_pod.side_effect = [mirror_pod, original_pod]

        result = status_sync_controller.sync_pod_status("original-pod", "mirror-pod", "default")

        assert result is False
        mock_k8s_client.patch_namespaced_pod_status.assert_not_called()

    def test_sync_pod_status_pod_not_found(self, status_sync_controller, mock_k8s_client):
        """Test sync when pod is not found."""
        from kubernetes.client.rest import ApiException

        mock_k8s_client.read_namespaced_pod.side_effect = ApiException(status=404)

        result = status_sync_controller.sync_pod_status("original-pod", "mirror-pod", "default")

        assert result is False

    def test_should_sync_status_with_modal_annotation(self, status_sync_controller, mock_k8s_client):
        """Test should_sync_status with Modal annotation."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.annotations = {"modal-operator.io/use-modal": "true"}

        mock_k8s_client.read_namespaced_pod.return_value = pod

        result = status_sync_controller.should_sync_status("test-pod", "default")

        assert result is True

    def test_should_sync_status_without_modal_annotation(self, status_sync_controller, mock_k8s_client):
        """Test should_sync_status without Modal annotation."""
        pod = Mock(spec=client.V1Pod)
        pod.metadata = Mock(spec=client.V1ObjectMeta)
        pod.metadata.annotations = {}

        mock_k8s_client.read_namespaced_pod.return_value = pod

        result = status_sync_controller.should_sync_status("test-pod", "default")

        assert result is False

    def test_create_status_patch_completed_job(self, status_sync_controller):
        """Test status patch creation for completed job."""
        # Mock mirror pod (succeeded)
        mirror_pod = Mock(spec=client.V1Pod)
        mirror_pod.status = Mock(spec=client.V1PodStatus)
        mirror_pod.status.phase = "Succeeded"
        mirror_pod.status.pod_ip = "10.0.0.1"
        mirror_pod.status.start_time = "2023-01-01T00:00:00Z"
        mirror_pod.status.container_statuses = [Mock()]
        mirror_pod.status.container_statuses[0].state = Mock()
        mirror_pod.status.container_statuses[0].state.terminated = Mock()
        mirror_pod.status.container_statuses[0].state.terminated.exit_code = 0
        mirror_pod.status.container_statuses[0].state.terminated.finished_at = "2023-01-01T00:01:00Z"
        mirror_pod.status.container_statuses[0].state.terminated.reason = "Completed"

        # Mock original pod
        original_pod = Mock(spec=client.V1Pod)
        original_pod.status = Mock(spec=client.V1PodStatus)
        original_pod.status.phase = "Running"
        original_pod.spec = Mock(spec=client.V1PodSpec)
        original_pod.spec.containers = [Mock(spec=client.V1Container)]
        original_pod.spec.containers[0].name = "test-container"
        original_pod.spec.containers[0].image = "test-image"

        patch = status_sync_controller._create_status_patch(mirror_pod, original_pod)

        assert patch is not None
        assert patch["status"]["phase"] == "Succeeded"
        assert patch["status"]["containerStatuses"][0]["state"]["terminated"]["exitCode"] == 0
