"""Tests for CRD models and functionality."""

from modal_operator.crds import ModalEndpointSpec, ModalEndpointStatus, ModalJobSpec, ModalJobStatus


class TestModalJobSpec:
    """Test ModalJob specification model."""

    def test_minimal_spec(self):
        """Test minimal ModalJob spec."""
        spec = ModalJobSpec(image="python:3.11")

        assert spec.image == "python:3.11"
        assert spec.cpu == "1.0"
        assert spec.memory == "512Mi"
        assert spec.timeout == 300
        assert spec.tunnel_enabled is False

    def test_full_spec(self):
        """Test complete ModalJob spec."""
        spec = ModalJobSpec(
            image="pytorch/pytorch:latest",
            command=["python", "train.py"],
            args=["--epochs", "10"],
            cpu="2.0",
            memory="1Gi",
            gpu="A100:1",
            env={"PYTHONPATH": "/app"},
            timeout=600,
            retries=3,
            tunnel_enabled=True,
            tunnel_port=9000,
        )

        assert spec.image == "pytorch/pytorch:latest"
        assert spec.command == ["python", "train.py"]
        assert spec.args == ["--epochs", "10"]
        assert spec.gpu == "A100:1"
        assert spec.env == {"PYTHONPATH": "/app"}
        assert spec.tunnel_enabled is True
        assert spec.tunnel_port == 9000


class TestModalJobStatus:
    """Test ModalJob status model."""

    def test_default_status(self):
        """Test default ModalJob status."""
        status = ModalJobStatus()

        assert status.phase == "Pending"
        assert status.modal_app_id is None
        assert status.conditions == []

    def test_running_status(self):
        """Test running ModalJob status."""
        status = ModalJobStatus(
            phase="Running",
            modal_app_id="app-123",
            modal_function_id="func-456",
            mirror_pod_name="test-mirror",
            tunnel_url="https://test.modal.run",
        )

        assert status.phase == "Running"
        assert status.modal_app_id == "app-123"
        assert status.modal_function_id == "func-456"
        assert status.tunnel_url == "https://test.modal.run"


class TestModalEndpointSpec:
    """Test ModalEndpoint specification model."""

    def test_minimal_endpoint_spec(self):
        """Test minimal ModalEndpoint spec."""
        spec = ModalEndpointSpec(image="python:3.11", handler="main.predict")

        assert spec.image == "python:3.11"
        assert spec.handler == "main.predict"
        assert spec.min_replicas == 0
        assert spec.max_replicas == 10

    def test_full_endpoint_spec(self):
        """Test complete ModalEndpoint spec."""
        spec = ModalEndpointSpec(
            image="tensorflow/serving:latest",
            handler="serve.predict",
            cpu="4.0",
            memory="2Gi",
            gpu="T4:1",
            min_replicas=1,
            max_replicas=5,
            env={"MODEL_PATH": "/models"},
        )

        assert spec.handler == "serve.predict"
        assert spec.cpu == "4.0"
        assert spec.gpu == "T4:1"
        assert spec.min_replicas == 1
        assert spec.max_replicas == 5


class TestModalEndpointStatus:
    """Test ModalEndpoint status model."""

    def test_default_endpoint_status(self):
        """Test default ModalEndpoint status."""
        status = ModalEndpointStatus()

        assert status.phase == "Pending"
        assert status.ready_replicas == 0
        assert status.endpoint_url is None

    def test_ready_endpoint_status(self):
        """Test ready ModalEndpoint status."""
        status = ModalEndpointStatus(
            phase="Ready", modal_app_id="endpoint-123", endpoint_url="https://my-endpoint.modal.run", ready_replicas=2
        )

        assert status.phase == "Ready"
        assert status.endpoint_url == "https://my-endpoint.modal.run"
        assert status.ready_replicas == 2
