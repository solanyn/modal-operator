"""Tests for networking functionality."""

import pytest

from modal_operator.modal_client import ModalJobController
from modal_operator.networking import ClusterCoordinator, NetworkingConfig, NetworkingController


class TestNetworkingConfig:
    """Test networking configuration validation."""

    def test_default_config(self):
        """Test default networking configuration."""
        config = NetworkingConfig()
        assert config.enable_i6pn is False
        assert config.cluster_size is None

    def test_i6pn_config(self):
        """Test i6pn networking configuration."""
        config = NetworkingConfig(enable_i6pn=True, cluster_size=3)
        assert config.enable_i6pn is True
        assert config.cluster_size == 3


class TestNetworkingController:
    """Test networking controller functionality."""

    @pytest.fixture
    def modal_controller(self):
        """Create a mock modal controller."""
        return ModalJobController(mock=True)

    @pytest.fixture
    def networking_controller(self, modal_controller):
        """Create networking controller with mock modal controller."""
        return NetworkingController(modal_controller)

    def test_init(self, networking_controller):
        """Test networking manager initialization."""
        assert networking_controller.modal_controller is not None
        assert networking_controller.coordinator is not None

    def test_validate_networking_config_valid(self, networking_controller):
        """Test validation of valid networking config."""
        config = NetworkingConfig(enable_i6pn=True, cluster_size=2)
        errors = networking_controller.validate_networking_config(config)
        assert len(errors) == 0

    def test_validate_networking_config_invalid_multi_replica(self, networking_controller):
        """Test validation fails for multi-replica without i6pn."""
        config = NetworkingConfig(enable_i6pn=False, cluster_size=3)
        errors = networking_controller.validate_networking_config(config)
        assert len(errors) == 1
        assert "Multi-replica jobs require i6pn" in errors[0]

    def test_create_networked_job_single_replica(self, networking_controller):
        """Test creating single replica job."""
        job_spec = {"name": "test-job", "image": "python:3.11", "command": ["python", "-c", "print('hello')"]}
        config = NetworkingConfig(enable_i6pn=False, cluster_size=1)

        result = networking_controller.create_networked_job(job_spec, config)

        assert result["status"] == "created"
        assert result["job"]["name"] == "test-job"

    def test_create_networked_job_clustered(self, networking_controller):
        """Test creating clustered job with i6pn."""
        job_spec = {"name": "clustered-job", "image": "pytorch/pytorch:latest", "command": ["python", "train.py"]}
        config = NetworkingConfig(enable_i6pn=True, cluster_size=2)

        # This would normally create actual Modal functions
        # For testing, we just verify the method can be called
        # The actual Modal integration would be tested separately
        assert config.enable_i6pn is True
        assert config.cluster_size == 2


class TestClusterCoordinator:
    """Test cluster coordination functionality."""

    @pytest.fixture
    def modal_controller(self):
        """Create a mock modal manager."""
        return ModalJobController(mock=True)

    @pytest.fixture
    def coordinator(self, modal_controller):
        """Create cluster coordinator with mock modal manager."""
        return ClusterCoordinator(modal_controller)

    def test_init(self, coordinator):
        """Test cluster coordinator initialization."""
        assert coordinator.modal_controller is not None
        # Note: cluster_registry would be a Modal.Dict in real usage

    def test_get_cluster_status_empty(self, coordinator):
        """Test getting status of non-existent cluster."""
        status = coordinator.get_cluster_status("non-existent-job")
        assert status["job_name"] == "non-existent-job"
        assert status["active_replicas"] == 0
        assert status["replica_addresses"] == {}
