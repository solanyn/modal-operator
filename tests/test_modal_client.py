"""Tests for Modal client functionality."""

import pytest

from modal_operator.controllers.modal_job_controller import ModalJobController


class TestModalJobController:
    """Test Modal job management."""

    @pytest.mark.asyncio
    async def test_create_job_mock(self):
        """Test creating a job in mock mode."""
        manager = ModalJobController(mock=True)

        result = await manager.create_job(
            name="test-job", image="python:3.11", command=["python", "-c", "print('hello')"], gpu="T4:1"
        )

        assert result["app_id"] == "mock-app-test-job"
        assert result["function_id"] == "mock-func-test-job"
        assert result["status"] == "running"
        assert result["tunnel_url"] == "https://mock-tunnel-test-job.modal.run"

    @pytest.mark.asyncio
    async def test_get_job_status_mock(self):
        """Test getting job status in mock mode."""
        manager = ModalJobController(mock=True)

        status = await manager.get_job_status("app-123", "func-456")

        assert status["status"] == "succeeded"
        assert "result" in status

    @pytest.mark.asyncio
    async def test_cancel_job_mock(self):
        """Test cancelling a job in mock mode."""
        manager = ModalJobController(mock=True)

        result = await manager.cancel_job("app-123", "func-456")

        assert result is True

    @pytest.mark.asyncio
    async def test_create_endpoint_mock(self):
        """Test creating an endpoint in mock mode."""
        manager = ModalJobController(mock=True)

        result = await manager.create_endpoint(
            name="test-endpoint", image="python:3.11", handler="main.predict", gpu="T4:1"
        )

        assert result["app_id"] == "mock-endpoint-test-endpoint"
        assert result["endpoint_url"] == "https://mock-test-endpoint.modal.run"
        assert result["status"] == "ready"

    @pytest.mark.asyncio
    async def test_delete_app_mock(self):
        """Test deleting an app in mock mode."""
        manager = ModalJobController(mock=True)

        result = await manager.delete_app("app-123")

        assert result is True
