"""End-to-end tests for Modal vGPU operator."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from kubernetes import client

from modal_operator.controllers.modal_job_controller import ModalJobController
from modal_operator.controllers.networking_controller import NetworkingController
from modal_operator.operator import _pod_to_modal_job_spec


class TestE2E:
    """End-to-end operator tests."""

    @pytest.fixture
    def k8s_client(self):
        """Mock Kubernetes client."""
        return MagicMock(spec=client.CoreV1Api)

    @pytest.fixture
    def modal_controller(self):
        """Mock Modal controller."""
        controller = ModalJobController(mock=True)
        # Mock async methods
        controller.create_job = AsyncMock(
            return_value={"app_id": "app-test-123", "function_id": "func-test-456", "status": "running"}
        )
        controller.get_job_status = AsyncMock(return_value={"status": "completed", "exit_code": 0})
        return controller

    # Mirror Pod controller removed in Phase 8 - using webhook mutation instead
    # @pytest.fixture
    # def mirror_controller(self, k8s_client):
    #     """Mock Mirror Pod controller."""
    #     return MirrorPodController(k8s_client)

    @pytest.fixture
    def networking_controller(self, modal_controller):
        """Mock Networking controller."""
        return NetworkingController(modal_controller)

    @pytest.mark.skip(reason="Mirror Pod controller removed in Phase 8 - using webhook mutation instead")
    @pytest.mark.asyncio
    async def test_gpu_pod_to_modal_job_workflow(self, modal_controller, mirror_controller, networking_controller):
        """Test complete workflow: GPU pod -> Modal job -> Mirror pod."""

        # 1. Create a GPU pod spec
        gpu_pod = {
            "metadata": {"name": "gpu-training", "namespace": "default"},
            "spec": {
                "containers": [
                    {
                        "name": "training",
                        "image": "pytorch/pytorch:latest",
                        "command": ["python", "train.py"],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                        "env": [{"name": "CUDA_VISIBLE_DEVICES", "value": "0"}],
                    }
                ]
            },
        }

        # 2. Convert pod to Modal job spec
        annotations = {}  # No special annotations for this test
        modal_job_spec_dict = _pod_to_modal_job_spec(gpu_pod, annotations)

        assert modal_job_spec_dict["image"] == "pytorch/pytorch:latest"
        assert modal_job_spec_dict["command"] == ["python", "train.py"]
        assert modal_job_spec_dict["env"]["CUDA_VISIBLE_DEVICES"] == "0"

        # 3. Create Modal job
        modal_result = await modal_controller.create_job(
            name="gpu-training",
            image=modal_job_spec_dict["image"],
            command=modal_job_spec_dict["command"],
            env=modal_job_spec_dict["env"],
        )

        assert modal_result["app_id"] == "app-test-123"
        assert modal_result["status"] == "running"

        # 4. Verify Mirror Pod creation would work
        # (Skip actual creation to avoid complex mocking)
        assert modal_job_spec_dict["image"] == "pytorch/pytorch:latest"
        assert modal_result["app_id"] is not None

        # 5. Check job status
        status = await modal_controller.get_job_status("app-test-123", "func-test-456")
        assert status["status"] == "completed"
        assert status["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_networking_workflow(self, networking_controller):
        """Test networking workflow with i6pn clustering."""

        # Create a multi-replica job spec
        job_spec = {
            "name": "distributed-training",
            "image": "pytorch/pytorch:latest",
            "command": ["python", "-m", "torch.distributed.launch", "train.py"],
        }

        # Test single replica (no clustering)
        from modal_operator.controllers.networking_controller import NetworkingConfig

        single_config = NetworkingConfig(enable_i6pn=False, cluster_size=1)

        result = networking_controller.create_networked_job(job_spec, single_config)
        assert result["status"] == "created"
        assert result["job"]["name"] == "distributed-training"

        # Test validation for multi-replica without i6pn
        multi_config = NetworkingConfig(enable_i6pn=False, cluster_size=3)
        errors = networking_controller.validate_networking_config(multi_config)
        assert len(errors) == 1
        assert "Multi-replica jobs require i6pn" in errors[0]

        # Test valid multi-replica config
        valid_config = NetworkingConfig(enable_i6pn=True, cluster_size=3)
        errors = networking_controller.validate_networking_config(valid_config)
        assert len(errors) == 0

    def test_crd_spec_validation(self):
        """Test CRD spec validation."""
        from modal_operator.crds import ModalJobSpec

        # Valid minimal spec
        spec = ModalJobSpec(image="python:3.11", command=["python", "-c", "print('hello')"])
        assert spec.image == "python:3.11"
        assert spec.replicas == 1  # default
        assert spec.enable_i6pn is False  # default

        # Valid networking spec
        networking_spec = ModalJobSpec(
            image="pytorch/pytorch:latest", command=["python", "train.py"], replicas=3, enable_i6pn=True
        )
        assert networking_spec.replicas == 3
        assert networking_spec.enable_i6pn is True

    def test_mock_mode_integration(self):
        """Test that mock mode works for development."""
        # Modal controller in mock mode
        controller = ModalJobController(mock=True)
        assert controller.mock is True

        # Should not require actual Modal credentials
        # All operations should work with mock responses
