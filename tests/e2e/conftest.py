"""E2E test configuration and base classes."""

import pytest
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml
from kubernetes import client, config


class E2ETestBase:
    """Base class for E2E tests with common utilities."""

    @classmethod
    def setup_class(cls):
        """Set up test environment."""
        cls.setup_kind_cluster()
        cls.install_operator()
        cls.wait_for_operator_ready()

    @classmethod
    def teardown_class(cls):
        """Clean up test environment."""
        cls.cleanup_kind_cluster()

    @classmethod
    def setup_kind_cluster(cls):
        """Create kind cluster for testing."""
        cluster_name = "mvgpu-e2e"

        # Create kind cluster
        kind_config = """
apiVersion: kind.x-k8s.io/v1alpha4
kind: Cluster
name: mvgpu-e2e
nodes:
- role: control-plane
- role: worker
"""

        config_path = Path("/tmp/kind-e2e-config.yaml")
        config_path.write_text(kind_config)

        subprocess.run(["kind", "create", "cluster", "--name", cluster_name, "--config", str(config_path)], check=True)

        # Load kubeconfig
        subprocess.run(["kind", "export", "kubeconfig", "--name", cluster_name], check=True)

        config.load_kube_config()
        cls.k8s_client = client.ApiClient()
        cls.core_v1 = client.CoreV1Api()
        cls.apps_v1 = client.AppsV1Api()
        cls.custom_objects = client.CustomObjectsApi()

    @classmethod
    def install_operator(cls):
        """Install Modal vGPU operator."""
        # Generate and apply CRDs
        project_root = Path(__file__).parent.parent.parent
        subprocess.run(["uv", "run", "python", "scripts/generate-crds.py"], cwd=project_root, check=True)

        subprocess.run(["kubectl", "apply", "-f", "charts/modal-vgpu-operator/crds/"], cwd=project_root, check=True)

        # Create operator namespace
        cls.apply_yaml({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "modal-system"}})

        # Create service account and RBAC
        cls.apply_yaml(
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {"name": "modal-vgpu-operator", "namespace": "modal-system"},
            }
        )

        cls.apply_yaml(
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {"name": "modal-vgpu-operator"},
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["pods", "pods/status"],
                        "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"],
                    },
                    {
                        "apiGroups": ["modal-operator.io"],
                        "resources": ["modaljobs", "modalendpoints"],
                        "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"],
                    },
                    {
                        "apiGroups": ["modal-operator.io"],
                        "resources": ["modaljobs/status", "modalendpoints/status"],
                        "verbs": ["get", "update", "patch"],
                    },
                ],
            }
        )

        cls.apply_yaml(
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": "modal-vgpu-operator"},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": "modal-vgpu-operator",
                },
                "subjects": [{"kind": "ServiceAccount", "name": "modal-vgpu-operator", "namespace": "modal-system"}],
            }
        )

        # Deploy operator in mock mode (using busybox for simplicity in e2e tests)
        operator_deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "modal-vgpu-operator", "namespace": "modal-system"},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "modal-vgpu-operator"}},
                "template": {
                    "metadata": {"labels": {"app": "modal-vgpu-operator"}},
                    "spec": {
                        "serviceAccountName": "modal-vgpu-operator",
                        "containers": [
                            {
                                "name": "operator",
                                "image": "busybox:latest",
                                "command": ["sleep", "3600"],  # Mock operator for e2e tests
                                "env": [{"name": "MODAL_MOCK", "value": "true"}],
                                "imagePullPolicy": "IfNotPresent",
                            }
                        ],
                    },
                },
            },
        }

        cls.apply_yaml(operator_deployment)

    @classmethod
    def wait_for_operator_ready(cls):
        """Wait for operator to be ready."""

        def check_operator_ready():
            try:
                # Check if deployment has ready replicas
                ready_replicas = cls.get_deployment_ready_replicas("modal-vgpu-operator", "modal-system")
                return ready_replicas > 0
            except Exception:
                return False

        cls.wait_for_condition(
            check_operator_ready,
            timeout=60,  # Reduced timeout for mock deployment
            message="Operator should be ready",
        )

    @classmethod
    def cleanup_kind_cluster(cls):
        """Delete kind cluster."""
        subprocess.run(["kind", "delete", "cluster", "--name", "mvgpu-e2e"], capture_output=True)

    @classmethod
    def apply_yaml(cls, resource: Dict[str, Any]):
        """Apply a Kubernetes resource."""
        yaml_str = yaml.dump(resource)
        subprocess.run(["kubectl", "apply", "-f", "-"], input=yaml_str, text=True, check=True)

    @classmethod
    def get_resource(cls, resource_type: str, name: str, namespace: str = "default") -> Dict[str, Any]:
        """Get a Kubernetes resource."""
        if resource_type == "pods":
            pod = cls.core_v1.read_namespaced_pod(name, namespace)
            return cls.k8s_client.sanitize_for_serialization(pod)
        elif resource_type == "modaljobs":
            return cls.custom_objects.get_namespaced_custom_object(
                group="modal-operator.io", version="v1alpha1", namespace=namespace, plural="modaljobs", name=name
            )
        elif resource_type == "pytorchjobs":
            return cls.custom_objects.get_namespaced_custom_object(
                group="kubeflow.org", version="v1", namespace=namespace, plural="pytorchjobs", name=name
            )
        else:
            raise ValueError(f"Unsupported resource type: {resource_type}")

    @classmethod
    def list_resources(cls, resource_type: str, namespace: str = "default") -> List[Dict[str, Any]]:
        """List Kubernetes resources."""
        if resource_type == "modaljobs":
            result = cls.custom_objects.list_namespaced_custom_object(
                group="modal-operator.io", version="v1alpha1", namespace=namespace, plural="modaljobs"
            )
            return result.get("items", [])
        else:
            raise ValueError(f"Unsupported resource type: {resource_type}")

    @classmethod
    def resource_exists(cls, resource_type: str, name: str, namespace: str = "default") -> bool:
        """Check if a resource exists."""
        try:
            cls.get_resource(resource_type, name, namespace)
            return True
        except Exception:
            return False

    @classmethod
    def wait_for_resource(cls, resource_type: str, name: str, namespace: str = "default", timeout: int = 60):
        """Wait for a resource to exist."""
        cls.wait_for_condition(
            lambda: cls.resource_exists(resource_type, name, namespace),
            timeout=timeout,
            message=f"{resource_type}/{name} should exist",
        )

    @classmethod
    def wait_for_condition(cls, condition_func, timeout: int = 60, message: str = "Condition should be met"):
        """Wait for a condition to be true."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if condition_func():
                    return
            except Exception:
                pass
            time.sleep(2)

        raise TimeoutError(f"Timeout waiting for condition: {message}")

    @classmethod
    def get_deployment_ready_replicas(cls, name: str, namespace: str) -> int:
        """Get number of ready replicas for a deployment."""
        try:
            deployment = cls.apps_v1.read_namespaced_deployment(name, namespace)
            return deployment.status.ready_replicas or 0
        except Exception:
            return 0


@pytest.fixture(scope="session", autouse=True)
def e2e_setup():
    """Session-wide setup for e2e tests."""
    # This ensures setup/teardown happens once per test session
    pass
