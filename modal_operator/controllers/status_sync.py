"""Generic status synchronization controller for Modal operator.

This controller synchronizes status from mirror pods back to original pods,
enabling proper integration with any Kubernetes workload controller.
"""

import logging
from typing import Any, Dict, Optional

from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class StatusSyncController:
    """Synchronizes status between mirror pods and original pods."""

    def __init__(self, k8s_client: client.CoreV1Api):
        self.k8s_client = k8s_client

    def sync_pod_status(self, original_pod_name: str, mirror_pod_name: str, namespace: str) -> bool:
        """Sync status from mirror pod to original pod.

        Args:
            original_pod_name: Name of the original pod (e.g., pytorch-job-master-0)
            mirror_pod_name: Name of the mirror pod (e.g., pytorch-job-master-0-modal-mirror)
            namespace: Kubernetes namespace

        Returns:
            bool: True if sync was successful, False otherwise
        """
        try:
            # Get mirror pod status
            mirror_pod = self.k8s_client.read_namespaced_pod(name=mirror_pod_name, namespace=namespace)

            # Get original pod
            original_pod = self.k8s_client.read_namespaced_pod(name=original_pod_name, namespace=namespace)

            # Create status patch based on mirror pod
            status_patch = self._create_status_patch(mirror_pod, original_pod)

            if status_patch:
                # Apply status patch to original pod
                self.k8s_client.patch_namespaced_pod_status(
                    name=original_pod_name, namespace=namespace, body=status_patch
                )

                logger.info(
                    f"Synced status from {mirror_pod_name} to {original_pod_name}: {status_patch['status']['phase']}"
                )
                return True

        except ApiException as e:
            if e.status == 404:
                logger.debug(f"Pod not found during status sync: {e}")
            else:
                logger.error(f"Failed to sync pod status: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during status sync: {e}")

        return False

    def _create_status_patch(self, mirror_pod: client.V1Pod, original_pod: client.V1Pod) -> Optional[Dict[str, Any]]:
        """Create status patch based on mirror pod status.

        Args:
            mirror_pod: The mirror pod with actual execution status
            original_pod: The original pod to update

        Returns:
            Dict containing the status patch, or None if no update needed
        """
        mirror_status = mirror_pod.status
        original_status = original_pod.status

        # Don't update if mirror pod status is not meaningful
        if not mirror_status or not mirror_status.phase:
            return None

        # Don't update if status hasn't changed
        if original_status and original_status.phase == mirror_status.phase:
            return None

        # Map mirror pod status to original pod status
        status_patch = {
            "status": {
                "phase": mirror_status.phase,
                "hostIP": "modal.com",  # Indicate this is running on Modal
                "podIP": mirror_status.pod_ip or "10.0.0.1",
                "startTime": mirror_status.start_time,
                "containerStatuses": self._map_container_statuses(mirror_status, original_pod),
            }
        }

        # Add completion time if pod is finished
        if mirror_status.phase in ["Succeeded", "Failed"] and hasattr(mirror_status, "container_statuses"):
            for container_status in mirror_status.container_statuses or []:
                if container_status.state and container_status.state.terminated:
                    status_patch["status"]["containerStatuses"][0]["state"] = {
                        "terminated": {
                            "exitCode": container_status.state.terminated.exit_code,
                            "finishedAt": container_status.state.terminated.finished_at,
                            "reason": container_status.state.terminated.reason or "Completed",
                            "message": f"Modal job completed on {mirror_status.host_ip or 'modal.com'}",
                        }
                    }
                    break

        return status_patch

    def _map_container_statuses(self, mirror_status: client.V1PodStatus, original_pod: client.V1Pod) -> list:
        """Map mirror pod container statuses to original pod format."""
        container_statuses = []

        # Get the first container from original pod spec
        if original_pod.spec and original_pod.spec.containers:
            original_container = original_pod.spec.containers[0]

            # Create container status based on mirror pod
            container_status = {
                "name": original_container.name,
                "image": original_container.image,
                "imageID": f"modal.com/{original_container.image}",
                "ready": mirror_status.phase == "Running",
                "restartCount": 0,
                "started": mirror_status.phase in ["Running", "Succeeded", "Failed"],
            }

            # Set container state based on pod phase
            if mirror_status.phase == "Running":
                container_status["state"] = {"running": {"startedAt": mirror_status.start_time}}
            elif mirror_status.phase == "Pending":
                container_status["state"] = {
                    "waiting": {"reason": "ModalJobStarting", "message": "Modal job is starting"}
                }

            container_statuses.append(container_status)

        return container_statuses

    def sync_mutated_pod_status(self, pod_name: str, namespace: str) -> bool:
        """Sync Modal job status to webhook-mutated pod.

        Args:
            pod_name: Name of the mutated pod
            namespace: Kubernetes namespace

        Returns:
            bool: True if sync was successful, False otherwise
        """
        try:
            # Get the mutated pod
            pod = self.k8s_client.read_namespaced_pod(name=pod_name, namespace=namespace)

            # Check if this is a mutated pod
            annotations = pod.metadata.annotations or {}
            if annotations.get("modal-operator.io/mutated") != "true":
                return False

            # Find corresponding ModalJob
            modal_job_name = f"{pod_name}-modal"

            # For now, just update the pod to show it's running on Modal
            # In a full implementation, we'd query the ModalJob status
            if pod.status.phase == "Pending":
                status_patch = {
                    "status": {
                        "phase": "Running",
                        "podIP": "10.0.0.1",
                        "containerStatuses": [
                            {
                                "name": pod.spec.containers[0].name,
                                "image": pod.spec.containers[0].image,
                                "imageID": (
                                    f"modal.com/{annotations.get('modal-operator.io/original-image', pod.spec.containers[0].image)}"
                                ),
                                "ready": True,
                                "restartCount": 0,
                                "started": True,
                                "state": {"running": {"startedAt": pod.status.start_time}},
                            }
                        ],
                    }
                }

                self.k8s_client.patch_namespaced_pod_status(name=pod_name, namespace=namespace, body=status_patch)

                logger.info(f"Updated mutated pod {pod_name} status to Running on Modal")
                return True

        except ApiException as e:
            if e.status == 404:
                logger.debug(f"Pod not found during mutated pod status sync: {e}")
            else:
                logger.error(f"Failed to sync mutated pod status: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during mutated pod status sync: {e}")

        return False

    def should_sync_status(self, pod_name: str, namespace: str) -> bool:
        """Check if a pod should have its status synced.

        Args:
            pod_name: Name of the original pod
            namespace: Kubernetes namespace

        Returns:
            bool: True if pod has Modal annotations and should be synced
        """
        try:
            pod = self.k8s_client.read_namespaced_pod(name=pod_name, namespace=namespace)
            annotations = pod.metadata.annotations or {}

            # Check for Modal annotations
            return annotations.get("modal-operator.io/use-modal") == "true" or any(
                key.startswith("modal-operator.io/") for key in annotations.keys()
            )
        except Exception:
            return False
