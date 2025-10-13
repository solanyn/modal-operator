"""Tests for Mirror Pod management."""

from unittest.mock import MagicMock, Mock

from modal_operator.mirror_pod import MirrorPodController


class TestMirrorPodController:
    """Test Mirror Pod management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_k8s_client = Mock()
        self.manager = MirrorPodController(self.mock_k8s_client)

    def test_create_mirror_pod_basic(self):
        """Test basic Mirror Pod creation."""
        mock_pod = MagicMock()
        mock_pod.metadata.name = "test-mirror"
        mock_pod.to_dict.return_value = {"metadata": {"name": "test-mirror"}}
        self.mock_k8s_client.create_namespaced_pod.return_value = mock_pod

        modal_job_spec = {"image": "python:3.11", "command": ["python", "-c", "print('hello')"]}

        result = self.manager.create_mirror_pod(
            name="test-job", namespace="default", modal_job_spec=modal_job_spec, modal_app_id="app-123"
        )

        # Verify pod creation was called
        self.mock_k8s_client.create_namespaced_pod.assert_called_once()
        call_args = self.mock_k8s_client.create_namespaced_pod.call_args

        assert call_args[1]["namespace"] == "default"
        pod_spec = call_args[1]["body"]
        assert pod_spec["metadata"]["name"] == "test-job-mirror"
        assert pod_spec["metadata"]["labels"]["modal-operator.io/type"] == "mirror-pod"
        assert pod_spec["metadata"]["annotations"]["modal-operator.io/modal-app-id"] == "app-123"

    def test_create_mirror_pod_with_tunnel(self):
        """Test Mirror Pod creation with tunnel enabled."""
        mock_pod = MagicMock()
        mock_pod.metadata.name = "test-mirror"
        mock_pod.to_dict.return_value = {"metadata": {"name": "test-mirror"}}
        self.mock_k8s_client.create_namespaced_pod.return_value = mock_pod

        modal_job_spec = {"image": "python:3.11", "tunnel_enabled": True, "tunnel_port": 9000}

        result = self.manager.create_mirror_pod(
            name="test-job",
            namespace="default",
            modal_job_spec=modal_job_spec,
            modal_app_id="app-123",
            tunnel_url="https://test.modal.run",
        )

        # Verify tunnel sidecar was added
        call_args = self.mock_k8s_client.create_namespaced_pod.call_args
        pod_spec = call_args[1]["body"]
        containers = pod_spec["spec"]["containers"]

        assert len(containers) == 2  # mirror + tunnel
        tunnel_container = containers[1]
        assert tunnel_container["name"] == "tunnel"
        assert tunnel_container["image"] == "alpine/socat:latest"

    def test_update_mirror_pod_status(self):
        """Test Mirror Pod status update."""
        self.manager.update_mirror_pod_status(
            name="test-job", namespace="default", phase="running", modal_app_id="app-123"
        )

        # Verify status patch was called
        self.mock_k8s_client.patch_namespaced_pod_status.assert_called_once()
        call_args = self.mock_k8s_client.patch_namespaced_pod_status.call_args

        assert call_args[1]["name"] == "test-job-mirror"
        assert call_args[1]["namespace"] == "default"

        status_patch = call_args[1]["body"]
        assert status_patch["status"]["phase"] == "Running"
        assert status_patch["status"]["containerStatuses"][0]["ready"] is True

    def test_delete_mirror_pod(self):
        """Test Mirror Pod deletion."""
        self.manager.delete_mirror_pod("test-job", "default")

        # Verify deletion was called
        self.mock_k8s_client.delete_namespaced_pod.assert_called_once_with(name="test-job-mirror", namespace="default")

    def test_get_container_state_running(self):
        """Test container state for running phase."""
        state = self.manager._get_container_state("Running")

        assert "running" in state
        assert "startedAt" in state["running"]

    def test_get_container_state_succeeded(self):
        """Test container state for succeeded phase."""
        state = self.manager._get_container_state("Succeeded")

        assert "terminated" in state
        assert state["terminated"]["exitCode"] == 0

    def test_get_container_state_failed(self):
        """Test container state for failed phase."""
        state = self.manager._get_container_state("Failed")

        assert "terminated" in state
        assert state["terminated"]["exitCode"] == 1
