"""Mutating admission webhook for Modal operator.

This webhook intercepts pod creation and mutates pods that should run on Modal,
eliminating the need for mirror pods and complex status synchronization.
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from kubernetes import client

logger = logging.getLogger(__name__)


class ModalWebhookController:
    """Mutating admission webhook controller for Modal pod interception."""

    def __init__(
        self,
        k8s_client: client.CoreV1Api,
        operator_image: str = "ghcr.io/solanyn/modal-operator:latest",
    ):
        self.k8s_client = k8s_client
        self.operator_image = operator_image

    def mutate_pod(self, admission_request: Dict[str, Any]) -> Dict[str, Any]:
        """Mutate pod if it should run on Modal.

        Args:
            admission_request: Kubernetes admission request

        Returns:
            Dict containing admission response with patches
        """
        uid = admission_request.get("uid", "")
        logger.info(f"Webhook called with UID: {uid}")

        try:
            # Extract pod from admission request
            pod_dict = admission_request["object"]
            metadata_dict = pod_dict.get("metadata", {})
            pod_name = metadata_dict.get("name", "unknown")
            pod_namespace = metadata_dict.get("namespace", "unknown")
            pod_annotations = metadata_dict.get("annotations", {})

            logger.info(
                f"Webhook processing pod: {pod_name} in namespace: {pod_namespace}, "
                f"annotations: {list(pod_annotations.keys())}"
            )

            # With objectSelector, we only get pods that need mutation
            logger.info(f"Mutating pod {pod_name} for Modal execution")

            # Generate mutation patches
            patches = self._generate_mutation_patches(pod_dict, "", None)

            return self._mutate_response(patches, "Mutated pod for Modal execution", uid)

        except Exception as e:
            logger.error(f"Failed to mutate pod: {e}")
            return self._deny_response(f"Mutation failed: {e}", uid)

    def _create_pod_spec_storage(self, pod: client.V1Pod) -> tuple[str, Optional[str]]:
        """Create ConfigMap and Secret for storing pod specification.

        Args:
            pod: Original pod object

        Returns:
            Tuple of (config_map_name, secret_name)
        """
        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace

        # Extract pod specification
        modal_spec = self.pod_mirror.extract_modal_spec(pod)

        # Separate sensitive and non-sensitive data
        sensitive_env = self._extract_sensitive_env(pod)
        non_sensitive_spec = {k: v for k, v in modal_spec.items() if k != "env"}

        # Create ConfigMap for pod spec
        config_map_name = f"modal-spec-{pod_name}"
        config_map = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name=config_map_name,
                namespace=namespace,
                owner_references=[
                    client.V1OwnerReference(
                        api_version="v1", kind="Pod", name=pod_name, uid=pod.metadata.uid, controller=True
                    )
                ],
            ),
            data={"modal-spec.json": json.dumps(non_sensitive_spec, indent=2)},
        )

        self.k8s_client.create_namespaced_config_map(namespace=namespace, body=config_map)

        # Create Secret for sensitive env vars (if any)
        secret_name = None
        if sensitive_env:
            secret_name = f"modal-env-{pod_name}"
            secret_data = {key: base64.b64encode(value.encode()).decode() for key, value in sensitive_env.items()}

            secret = client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=secret_name,
                    namespace=namespace,
                    owner_references=[
                        client.V1OwnerReference(
                            api_version="v1", kind="Pod", name=pod_name, uid=pod.metadata.uid, controller=True
                        )
                    ],
                ),
                data=secret_data,
            )

            self.k8s_client.create_namespaced_secret(namespace=namespace, body=secret)

        return config_map_name, secret_name

    def _generate_mutation_patches(
        self, pod_dict: Dict[str, Any], config_map_name: str, secret_name: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Generate JSON patches to mutate the pod.

        Args:
            pod_dict: Original pod dictionary from admission request
            config_map_name: Name of ConfigMap with pod spec
            secret_name: Name of Secret with env vars (optional)

        Returns:
            List of JSON patch operations
        """
        patches = []

        # Validate pod structure
        pod_spec = pod_dict.get("spec", {})
        containers = pod_spec.get("containers", [])
        if not containers or len(containers) == 0:
            raise ValueError("Pod must have at least one container")

        original_container = containers[0]

        # Validate container has required fields
        if not original_container.get("name"):
            raise ValueError(f"Container must have a name, got: {original_container}")
        if not original_container.get("image"):
            raise ValueError(f"Container must have an image, got: {original_container}")

        # Replace all containers with Modal log streaming
        metadata_dict = pod_dict.get("metadata", {})
        pod_name = metadata_dict.get("name", "unknown")

        # Get all original containers for environment variables
        original_containers = containers

        # Create environment variables from all containers
        all_images = [c.get("image") for c in original_containers]
        all_names = [c.get("name") for c in original_containers]
        all_commands = [c.get("command", []) for c in original_containers]
        all_args = [c.get("args", []) for c in original_containers]
        all_env = {}
        for c in original_containers:
            for env in c.get("env", []):
                all_env[env.get("name")] = env.get("value")

        # Replace entire containers array with Modal logger + proxy sidecar
        container_patch = {
            "op": "replace",
            "path": "/spec/containers",
            "value": [
                {
                    "name": original_containers[0].get("name", "logger"),
                    "image": self.operator_image,
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["modal-logger"],
                    "env": [
                        {"name": "POD_NAME", "value": pod_name},
                        {
                            "name": "POD_NAMESPACE",
                            "valueFrom": {"fieldRef": {"fieldPath": "metadata.namespace"}},
                        },
                        {"name": "MODAL_EXECUTION", "value": "true"},
                        {"name": "ORIGINAL_IMAGES", "value": json.dumps(all_images)},
                        {"name": "ORIGINAL_NAMES", "value": json.dumps(all_names)},
                        {"name": "ORIGINAL_COMMANDS", "value": json.dumps(all_commands)},
                        {"name": "ORIGINAL_ARGS", "value": json.dumps(all_args)},
                        {"name": "ORIGINAL_ENV", "value": json.dumps(all_env)},
                        {"name": "HTTP_PROXY", "value": "socks5://localhost:1080"},
                        {"name": "HTTPS_PROXY", "value": "socks5://localhost:1080"},
                        {"name": "MODAL_OPERATOR_PROXY", "value": "localhost:1080"},
                    ],
                    "ports": [{"containerPort": 8000, "name": "placeholder", "protocol": "TCP"}],
                    "resources": {},
                    "volumeMounts": [{"name": "modal-secret", "mountPath": "/etc/modal-secret", "readOnly": True}],
                },
                {
                    "name": "proxy",
                    "image": self.operator_image,
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["modal-proxy"],
                    "ports": [{"containerPort": 1080, "name": "proxy", "protocol": "TCP"}],
                    "env": [{"name": "PROXY_PORT", "value": "1080"}, {"name": "POD_NAME", "value": pod_name}],
                    "resources": {
                        "requests": {"memory": "64Mi", "cpu": "50m"},
                        "limits": {"memory": "128Mi", "cpu": "100m"},
                    },
                    "volumeMounts": [{"name": "modal-secret", "mountPath": "/etc/modal-secret", "readOnly": True}],
                },
            ],
        }
        patches.append(container_patch)

        # Add pod-level networking configuration
        pod_spec = pod_dict.get("spec", {})

        # Preserve original networking configuration in annotations
        networking_config = {
            "hostNetwork": pod_spec.get("hostNetwork", False),
            "dnsPolicy": pod_spec.get("dnsPolicy", "ClusterFirst"),
            "subdomain": pod_spec.get("subdomain"),
            "hostname": pod_spec.get("hostname"),
            "dnsConfig": pod_spec.get("dnsConfig"),
        }

        # Store original networking config for Modal execution
        networking_patch = {
            "op": "add",
            "path": "/metadata/annotations/modal-operator.io~1original-networking",
            "value": json.dumps(networking_config),
        }
        patches.append(networking_patch)

        # Override pod networking for placeholder pod
        if pod_spec.get("hostNetwork"):
            host_network_patch = {
                "op": "replace",
                "path": "/spec/hostNetwork",
                "value": False,  # Disable host networking for placeholder
            }
            patches.append(host_network_patch)

        # Ensure proper DNS for service discovery
        dns_policy_patch = {
            "op": "replace" if "dnsPolicy" in pod_spec else "add",
            "path": "/spec/dnsPolicy",
            "value": "ClusterFirst",
        }
        patches.append(dns_policy_patch)

        # Add Modal secret volume (same as operator uses)
        volume_patch = {
            "op": "add",
            "path": "/spec/volumes/-",
            "value": {
                "name": "modal-secret",
                "secret": {
                    "secretName": "modal-token",
                    "optional": False,  # Required - operator needs this too
                },
            },
        }
        patches.append(volume_patch)

        # Add annotation to indicate mutation
        annotation_patch = {"op": "add", "path": "/metadata/annotations/modal-operator.io~1mutated", "value": "true"}
        patches.append(annotation_patch)

        # Add tunnel service annotation
        tunnel_service_patch = {
            "op": "add",
            "path": "/metadata/annotations/modal-operator.io~1tunnel-enabled",
            "value": "true",
        }
        patches.append(tunnel_service_patch)

        # Add tunnel pod label for service selector (ensure labels exist first)
        if not metadata_dict.get("labels"):
            labels_patch = {
                "op": "add",
                "path": "/metadata/labels",
                "value": {"modal-operator.io/tunnel-pod": pod_name},
            }
            patches.append(labels_patch)
        else:
            tunnel_label_patch = {
                "op": "add",
                "path": "/metadata/labels/modal-operator.io~1tunnel-pod",
                "value": pod_name,
            }
            patches.append(tunnel_label_patch)

        return patches

    def _extract_sensitive_env(self, pod: client.V1Pod) -> Dict[str, str]:
        """Extract sensitive environment variables from pod.

        Args:
            pod: Pod object

        Returns:
            Dict of sensitive environment variables
        """
        sensitive_env = {}

        # Look for common sensitive env var patterns
        sensitive_patterns = ["PASSWORD", "SECRET", "KEY", "TOKEN", "CREDENTIAL", "AUTH", "CERT", "PRIVATE", "PASS"]

        for container in pod.spec.containers or []:
            for env_var in container.env or []:
                if env_var.value and any(pattern in env_var.name.upper() for pattern in sensitive_patterns):
                    sensitive_env[env_var.name] = env_var.value

        return sensitive_env

    def _allow_response(self, message: str, uid: str = "") -> Dict[str, Any]:
        """Generate admission response that allows the pod unchanged."""
        return {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {"uid": uid, "allowed": True, "status": {"message": message}},
        }

    def _mutate_response(self, patches: List[Dict[str, Any]], message: str, uid: str = "") -> Dict[str, Any]:
        """Generate admission response with mutations."""
        patch_bytes = json.dumps(patches).encode()
        patch_b64 = base64.b64encode(patch_bytes).decode()

        return {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {
                "uid": uid,
                "allowed": True,
                "patchType": "JSONPatch",
                "patch": patch_b64,
                "status": {"message": message},
            },
        }

    def _should_mutate_pod(self, pod: client.V1Pod) -> bool:
        """Check if a pod should be mutated for Modal execution."""

        if not pod.metadata or not pod.metadata.annotations:
            return False

        annotations = pod.metadata.annotations

        # Only check for workload-type annotation
        return annotations.get("modal-operator.io/workload-type") in ["job", "function"]

    def _get_modal_type(self, pod: client.V1Pod) -> str:
        """Get Modal workload type from annotation."""

        annotations = pod.metadata.annotations or {}
        return annotations.get("modal-operator.io/workload-type", "job")  # Default to job

    def _deny_response(self, message: str, uid: str = "") -> Dict[str, Any]:
        """Generate admission response that denies the pod."""
        return {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {"uid": uid, "allowed": False, "status": {"message": message}},
        }
