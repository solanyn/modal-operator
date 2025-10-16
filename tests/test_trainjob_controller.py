"""Tests for TrainJob controller."""

import pytest
from unittest.mock import AsyncMock, patch

from modal_operator.controllers.trainjob_controller import (
    _create_modal_job_spec,
    _requires_gpu,
    _should_handle_trainjob,
    handle_trainjob,
)


class TestTrainJobController:
    """Test TrainJob controller functionality."""

    def test_should_handle_trainjob_with_modal_runtime(self):
        """Test TrainJob detection with Modal runtime name."""
        spec = {"trainer": {}}
        assert _should_handle_trainjob(spec, "modal-pytorch-runtime")

    def test_should_handle_trainjob_with_annotation(self):
        """Test TrainJob detection with Modal annotation."""
        spec = {"annotations": {"modal.com/enabled": "true"}, "trainer": {}}
        assert _should_handle_trainjob(spec, "standard-runtime")

    def test_should_handle_trainjob_with_env_var(self):
        """Test TrainJob detection with Modal environment variable."""
        spec = {"trainer": {"env": [{"name": "MODAL_ENABLED", "value": "true"}]}}
        assert _should_handle_trainjob(spec, "standard-runtime")

    def test_should_not_handle_regular_trainjob(self):
        """Test that regular TrainJobs are not handled."""
        spec = {"trainer": {}}
        assert not _should_handle_trainjob(spec, "standard-runtime")

    def test_requires_gpu_detection(self):
        """Test GPU requirement detection."""
        spec_with_gpu = {"podSpecOverrides": [{"containers": [{"resources": {"requests": {"nvidia.com/gpu": "1"}}}]}]}
        assert _requires_gpu(spec_with_gpu)

        spec_without_gpu = {"trainer": {}}
        assert not _requires_gpu(spec_without_gpu)

    def test_create_modal_job_spec_basic(self):
        """Test basic ModalJob spec creation."""
        trainjob_spec = {
            "trainer": {
                "command": ["python"],
                "args": ["train.py"],
                "env": [{"name": "PYTHONPATH", "value": "/workspace"}, {"name": "EPOCHS", "value": "10"}],
            }
        }

        modal_spec = _create_modal_job_spec(trainjob_spec, "test-job", "default")

        assert modal_spec.command == ["python"]
        assert modal_spec.args == ["train.py"]
        assert modal_spec.env["PYTHONPATH"] == "/workspace"
        assert modal_spec.env["EPOCHS"] == "10"
        assert modal_spec.replicas == 1
        assert not modal_spec.enable_i6pn

    def test_create_modal_job_spec_distributed(self):
        """Test ModalJob spec creation for distributed training."""
        trainjob_spec = {
            "trainer": {
                "command": ["python", "-m", "torch.distributed.run"],
                "args": ["--nproc_per_node=2", "train.py"],
            },
            "podSpecOverrides": [
                {
                    "targetJobs": ["trainer-node-0", "trainer-node-1"],
                    "containers": [{"resources": {"requests": {"nvidia.com/gpu": "1"}}}],
                }
            ],
        }

        modal_spec = _create_modal_job_spec(trainjob_spec, "distributed-job", "default")

        assert modal_spec.replicas == 2
        assert modal_spec.enable_i6pn
        assert modal_spec.gpu == "T4:1"

    @pytest.mark.asyncio
    @patch("modal_operator.controllers.trainjob_controller.ModalJobController")
    async def test_handle_trainjob_creation(self, mock_controller_class):
        """Test TrainJob handling and ModalJob creation."""
        mock_controller = AsyncMock()
        mock_controller_class.return_value = mock_controller

        spec = {
            "runtimeRef": {"name": "modal-pytorch-runtime"},
            "trainer": {"command": ["python"], "args": ["train.py"]},
        }

        result = await handle_trainjob(spec=spec, name="test-trainjob", namespace="default", uid="test-uid")

        assert result["modalJobName"] == "trainjob-test-trainjob"
        assert result["status"] == "Created"
        mock_controller.create_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_trainjob_skip_non_modal(self):
        """Test that non-Modal TrainJobs are skipped."""
        spec = {"runtimeRef": {"name": "standard-runtime"}, "trainer": {}}

        result = await handle_trainjob(spec=spec, name="standard-trainjob", namespace="default")

        assert result == {}

    @pytest.mark.asyncio
    async def test_handle_trainjob_missing_runtime_ref(self):
        """Test error handling for missing runtime reference."""
        spec = {"trainer": {}}

        with pytest.raises(Exception):  # kopf.PermanentError in real usage
            await handle_trainjob(spec=spec, name="test-job", namespace="default")
