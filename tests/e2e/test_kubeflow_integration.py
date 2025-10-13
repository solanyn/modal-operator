"""E2E tests for Kubeflow integration."""

import pytest

from .conftest import E2ETestBase


class TestKubeflowIntegration(E2ETestBase):
    """Test Kubeflow component integration."""

    def test_pytorch_job_offloading(self):
        """Test PyTorchJob gets offloaded to Modal."""
        pytorch_job = {
            "apiVersion": "kubeflow.org/v1",
            "kind": "PyTorchJob",
            "metadata": {"name": "pytorch-modal", "namespace": "default"},
            "spec": {
                "pytorchReplicaSpecs": {
                    "Master": {
                        "replicas": 1,
                        "template": {
                            "metadata": {"annotations": {"modal-operator.io/offload": "true"}},
                            "spec": {
                                "containers": [
                                    {
                                        "name": "pytorch",
                                        "image": "pytorch/pytorch:latest",
                                        "command": [
                                            "python",
                                            "-c",
                                            "import torch; print(f'PyTorch {torch.__version__}')",
                                        ],
                                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                                    }
                                ],
                                "restartPolicy": "Never",
                            },
                        },
                    }
                }
            },
        }

        self.apply_yaml(pytorch_job)

        # Wait for ModalJob creation (PyTorchJob creates pods which get intercepted)
        self.wait_for_condition(
            lambda: len(self.list_resources("modaljobs")) > 0,
            timeout=60,
            message="ModalJob should be created from PyTorchJob",
        )

        # Verify ModalJob has correct PyTorch image
        modaljobs = self.list_resources("modaljobs")
        pytorch_modaljob = next((job for job in modaljobs if "pytorch" in job["spec"]["image"]), None)
        assert pytorch_modaljob is not None
        assert pytorch_modaljob["spec"]["image"] == "pytorch/pytorch:latest"

    def test_distributed_pytorch_job(self):
        """Test multi-replica PyTorchJob with i6pn networking."""
        distributed_job = {
            "apiVersion": "kubeflow.org/v1",
            "kind": "PyTorchJob",
            "metadata": {"name": "distributed-pytorch", "namespace": "default"},
            "spec": {
                "pytorchReplicaSpecs": {
                    "Master": {
                        "replicas": 1,
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "modal-operator.io/offload": "true",
                                    "modal-operator.io/enable-i6pn": "true",
                                }
                            },
                            "spec": {
                                "containers": [
                                    {
                                        "name": "pytorch",
                                        "image": "pytorch/pytorch:latest",
                                        "command": ["python", "-m", "torch.distributed.launch", "train.py"],
                                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                                    }
                                ],
                                "restartPolicy": "Never",
                            },
                        },
                    },
                    "Worker": {
                        "replicas": 2,
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "modal-operator.io/offload": "true",
                                    "modal-operator.io/enable-i6pn": "true",
                                }
                            },
                            "spec": {
                                "containers": [
                                    {
                                        "name": "pytorch",
                                        "image": "pytorch/pytorch:latest",
                                        "command": ["python", "-m", "torch.distributed.launch", "train.py"],
                                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                                    }
                                ],
                                "restartPolicy": "Never",
                            },
                        },
                    },
                }
            },
        }

        self.apply_yaml(distributed_job)

        # Wait for multiple ModalJobs (master + workers)
        self.wait_for_condition(
            lambda: len(self.list_resources("modaljobs")) >= 3,
            timeout=90,
            message="Should create ModalJobs for master and worker replicas",
        )

        # Verify i6pn is enabled for distributed jobs
        modaljobs = self.list_resources("modaljobs")
        for job in modaljobs:
            if "distributed-pytorch" in job["metadata"]["name"]:
                assert job["spec"]["enable_i6pn"] is True

    def test_job_status_propagation(self):
        """Test status propagation from Modal → Pod → PyTorchJob."""
        simple_job = {
            "apiVersion": "kubeflow.org/v1",
            "kind": "PyTorchJob",
            "metadata": {"name": "status-propagation", "namespace": "default"},
            "spec": {
                "pytorchReplicaSpecs": {
                    "Master": {
                        "replicas": 1,
                        "template": {
                            "metadata": {"annotations": {"modal-operator.io/offload": "true"}},
                            "spec": {
                                "containers": [
                                    {
                                        "name": "pytorch",
                                        "image": "python:3.11",
                                        "command": ["python", "-c", "print('Job completed successfully')"],
                                        "resources": {"requests": {"nvidia.com/gpu": "1"}},
                                    }
                                ],
                                "restartPolicy": "Never",
                            },
                        },
                    }
                }
            },
        }

        self.apply_yaml(simple_job)

        # Wait for job completion (in mock mode should be fast)
        self.wait_for_condition(
            lambda: self.get_resource("pytorchjobs", "status-propagation")["status"].get("conditions", []),
            timeout=120,
            message="PyTorchJob should have status conditions",
        )

        # Verify final status
        job = self.get_resource("pytorchjobs", "status-propagation")
        conditions = job["status"].get("conditions", [])
        assert any(condition["type"] == "Succeeded" for condition in conditions)

    @pytest.mark.skip(reason="Katib not installed in minimal setup")
    def test_katib_experiment(self):
        """Test Katib experiment with Modal GPU offloading."""
        # This would test hyperparameter tuning with Modal scaling
        # Requires full Katib installation
        pass
