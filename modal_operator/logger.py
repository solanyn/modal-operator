#!/usr/bin/env python3
"""
Modal log streamer for placeholder pods.

Waits for ModalJob/ModalEndpoint resource to be created, then streams logs
from the Modal app to stdout in structured JSON format.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from kubernetes import client, config

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class ModalLogStreamer:
    """Streams logs from Modal apps to stdout."""

    def __init__(self):
        self.pod_name = os.getenv("POD_NAME", "unknown")
        self.modaljob_name = f"{self.pod_name}-modal"
        self.namespace = os.getenv("POD_NAMESPACE", "default")

        # Load Kubernetes config
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self.k8s_custom = client.CustomObjectsApi()

        # Load Modal credentials
        self._load_modal_credentials()

    def _load_modal_credentials(self):
        """Load Modal credentials from mounted secret."""
        secret_path = Path("/etc/modal-secret")

        # Try new format first
        token_id_path = secret_path / "MODAL_TOKEN_ID"
        token_secret_path = secret_path / "MODAL_TOKEN_SECRET"

        # Fall back to old format
        if not token_id_path.exists():
            token_id_path = secret_path / "token-id"
            token_secret_path = secret_path / "token-secret"

        if not token_id_path.exists() or not token_secret_path.exists():
            logger.error("❌ Modal credentials not found")
            sys.exit(1)

        os.environ["MODAL_TOKEN_ID"] = token_id_path.read_text().strip()
        os.environ["MODAL_TOKEN_SECRET"] = token_secret_path.read_text().strip()
        logger.info("✅ Using operator's Modal credentials")

    async def wait_for_modal_resource(self) -> Tuple[Optional[str], str, Optional[str]]:
        """Wait for ModalJob or ModalEndpoint to be created.

        Returns:
            Tuple of (app_id, resource_type, endpoint_url)
        """
        logger.info(f"Waiting for Modal resource {self.modaljob_name}...")

        while True:
            # Try ModalJob first (batch workloads)
            try:
                modaljob = self.k8s_custom.get_namespaced_custom_object(
                    group="modal-operator.io",
                    version="v1alpha1",
                    namespace=self.namespace,
                    plural="modaljobs",
                    name=self.modaljob_name,
                )

                app_id = modaljob.get("status", {}).get("modal_app_id")
                if app_id:
                    logger.info(f"📡 Found ModalJob with Modal app: {app_id}")
                    return app_id, "ModalJob", None

            except client.exceptions.ApiException as e:
                if e.status != 404:
                    logger.error(f"Error checking ModalJob: {e}")

            # Try ModalEndpoint (HTTP services)
            try:
                modalendpoint = self.k8s_custom.get_namespaced_custom_object(
                    group="modal-operator.io",
                    version="v1alpha1",
                    namespace=self.namespace,
                    plural="modalendpoints",
                    name=self.modaljob_name,
                )

                app_id = modalendpoint.get("status", {}).get("modal_app_id")
                endpoint_url = modalendpoint.get("status", {}).get("endpoint_url")
                if app_id:
                    logger.info(f"📡 Found ModalEndpoint with Modal app: {app_id}")
                    if endpoint_url:
                        logger.info(f"🌐 HTTP Endpoint: {endpoint_url}")
                    return app_id, "ModalEndpoint", endpoint_url

            except client.exceptions.ApiException as e:
                if e.status != 404:
                    logger.error(f"Error checking ModalEndpoint: {e}")

            # Wait before retry
            await asyncio.sleep(2)

    async def stream_logs(self, app_id: str):
        """Stream logs from Modal app.

        Args:
            app_id: Modal app ID to stream logs from
        """
        import subprocess

        logger.info(f"Streaming logs from Modal app {app_id}...")

        try:
            # Use modal CLI to stream logs
            process = subprocess.Popen(
                ["modal", "app", "logs", app_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Stream and format logs
            for line in process.stdout:
                log_entry = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "pod": self.pod_name,
                    "container": "modal",
                    "message": line.strip(),
                }
                print(json.dumps(log_entry), flush=True)

            process.wait()
            logger.info("Modal app completed")

        except Exception as e:
            logger.error(f"Error streaming logs: {e}")

    async def run(self):
        """Main entry point."""
        logger.info(f"🚀 Modal execution for pod: {self.pod_name}")

        # Show original container info
        original_images = os.getenv("ORIGINAL_IMAGES")
        if original_images:
            logger.info(f"Original containers: {original_images}")
        else:
            original_image = os.getenv("ORIGINAL_IMAGE")
            if original_image:
                logger.info(f"Original image: {original_image}")

        # Wait for Modal resource
        app_id, resource_type, endpoint_url = await self.wait_for_modal_resource()

        if not app_id:
            logger.error("❌ Failed to find Modal resource")
            sys.exit(1)

        # Stream logs
        await self.stream_logs(app_id)

        logger.info("✅ Modal execution completed")

        # Keep container running (matches original behavior)
        while True:
            await asyncio.sleep(3600)


def main():
    """Main entry point."""
    streamer = ModalLogStreamer()
    asyncio.run(streamer.run())


if __name__ == "__main__":
    main()
