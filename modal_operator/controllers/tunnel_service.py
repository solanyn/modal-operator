"""Tunnel service controller for kubectl exec support."""

import logging
from typing import Optional

from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class TunnelServiceController:
    """Controller for managing tunnel services for Modal pods."""

    def __init__(self, k8s_client: client.CoreV1Api):
        self.k8s_client = k8s_client

    def create_tunnel_service(self, pod_name: str, namespace: str) -> Optional[str]:
        """Create a service for tunnel access to Modal pod.

        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace

        Returns:
            Service name if created successfully
        """
        service_name = f"{pod_name}-tunnel"

        try:
            # Check if service already exists
            try:
                self.k8s_client.read_namespaced_service(service_name, namespace)
                logger.info(f"Tunnel service {service_name} already exists")
                return service_name
            except ApiException as e:
                if e.status != 404:
                    raise

            # Create service
            service = client.V1Service(
                metadata=client.V1ObjectMeta(
                    name=service_name,
                    namespace=namespace,
                    labels={"app": pod_name, "modal-operator.io/tunnel": "true"},
                    annotations={"modal-operator.io/original-pod": pod_name},
                ),
                spec=client.V1ServiceSpec(
                    selector={"modal-operator.io/tunnel-pod": pod_name},
                    ports=[client.V1ServicePort(name="tunnel", port=8080, target_port=8080, protocol="TCP")],
                    type="ClusterIP",
                ),
            )

            self.k8s_client.create_namespaced_service(namespace, service)
            logger.info(f"Created tunnel service {service_name}")
            return service_name

        except Exception as e:
            logger.error(f"Failed to create tunnel service for {pod_name}: {e}")
            return None

    def delete_tunnel_service(self, pod_name: str, namespace: str) -> bool:
        """Delete tunnel service for a pod.

        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace

        Returns:
            True if deleted successfully
        """
        service_name = f"{pod_name}-tunnel"

        try:
            self.k8s_client.delete_namespaced_service(service_name, namespace)
            logger.info(f"Deleted tunnel service {service_name}")
            return True
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Tunnel service {service_name} not found")
                return True
            logger.error(f"Failed to delete tunnel service {service_name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete tunnel service {service_name}: {e}")
            return False

    def get_tunnel_endpoint(self, pod_name: str, namespace: str) -> Optional[str]:
        """Get tunnel endpoint URL for a pod.

        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace

        Returns:
            Tunnel endpoint URL
        """
        service_name = f"{pod_name}-tunnel"

        try:
            service = self.k8s_client.read_namespaced_service(service_name, namespace)
            cluster_ip = service.spec.cluster_ip
            port = service.spec.ports[0].port

            return f"ws://{cluster_ip}:{port}/exec"

        except Exception as e:
            logger.error(f"Failed to get tunnel endpoint for {pod_name}: {e}")
            return None
