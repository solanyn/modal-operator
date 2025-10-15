"""Tests for the Modal vGPU operator."""

import pytest

from modal_operator.controllers.modal_job_controller import ModalJobController
from modal_operator.operator import _has_gpu_request, _pod_to_modal_job_spec


class TestModalJobController:
    """Test Modal job manager."""

    @pytest.mark.asyncio
    async def test_mock_client(self):
        """Test mock Modal client."""
        manager = ModalJobController(mock=True)
        result = await manager.create_job(
            name="test-job", image="python:3.11", command=["echo", "hello"], cpu="1.0", memory="512Mi"
        )
        assert result["app_id"] == "mock-app-test-job"


class TestPodAnalysis:
    """Test pod analysis functions."""

    def test_has_gpu_request_true(self):
        """Test GPU request detection - positive case."""
        container = {"resources": {"requests": {"nvidia.com/gpu": "1"}}}
        assert _has_gpu_request(container) is True

    def test_has_gpu_request_false(self):
        """Test GPU request detection - negative case."""
        container = {"resources": {"requests": {"cpu": "1", "memory": "512Mi"}}}
        assert _has_gpu_request(container) is False

    def test_pod_to_modal_job_spec_basic(self):
        """Test basic pod to ModalJob conversion."""
        pod_spec = {
            "spec": {
                "containers": [
                    {
                        "image": "pytorch/pytorch:latest",
                        "command": ["python", "train.py"],
                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                    }
                ]
            }
        }
        annotations = {"modal-operator.io/gpu-type": "A100"}

        modal_spec = _pod_to_modal_job_spec(pod_spec, annotations)

        assert modal_spec["image"] == "pytorch/pytorch:latest"
        assert modal_spec["command"] == ["python", "train.py"]
        assert modal_spec["gpu"] == "A100:1"

    def test_pod_to_modal_job_spec_with_env(self):
        """Test pod to ModalJob conversion with environment variables."""
        pod_spec = {
            "spec": {"containers": [{"image": "python:3.11", "env": [{"name": "PYTHONPATH", "value": "/app"}]}]}
        }
        annotations = {"modal-operator.io/env-MODEL_PATH": "/models"}

        modal_spec = _pod_to_modal_job_spec(pod_spec, annotations)

        assert modal_spec["env"] == {"PYTHONPATH": "/app", "MODEL_PATH": "/models"}
