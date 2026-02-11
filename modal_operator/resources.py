import logging
from typing import Any
from urllib.parse import urlparse

from kubernetes import client
from kubernetes.client.exceptions import ApiException

logger = logging.getLogger(__name__)


class ResourceManager:
    def __init__(self):
        self.core_api = client.CoreV1Api()

    def create_external_service(
        self,
        name: str,
        namespace: str,
        modal_url: str,
        service_port: int,
        owner_ref: Any,
    ) -> Any:
        parsed = urlparse(modal_url)
        external_hostname = parsed.netloc or parsed.path

        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=namespace,
                labels={"modal.internal.io/app": name},
                annotations={"modal.internal.io/url": modal_url},
                owner_references=[owner_ref],
            ),
            spec=client.V1ServiceSpec(
                type="ExternalName",
                external_name=external_hostname,
                ports=[
                    client.V1ServicePort(
                        port=service_port,
                        target_port=443,
                        protocol="TCP",
                    )
                ],
            ),
        )

        logger.info(f"Creating ExternalName service {name} -> {external_hostname}")
        return self.core_api.create_namespaced_service(namespace=namespace, body=service)

    def update_external_service(
        self,
        name: str,
        namespace: str,
        modal_url: str,
        service_port: int,
    ) -> Any:
        try:
            parsed = urlparse(modal_url)
            external_hostname = parsed.netloc or parsed.path

            service = self.core_api.read_namespaced_service(name, namespace)
            service.spec.external_name = external_hostname
            service.metadata.annotations["modal.internal.io/url"] = modal_url

            logger.info(f"Updating ExternalName service {name} -> {external_hostname}")
            return self.core_api.replace_namespaced_service(name, namespace, service)
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    def delete_service(self, name: str, namespace: str) -> bool:
        try:
            self.core_api.delete_namespaced_service(name, namespace)
            logger.info(f"Deleted service {name} in {namespace}")
            return True
        except ApiException as e:
            if e.status == 404:
                return True
            logger.error(f"Failed to delete service {name}: {e}")
            return False
