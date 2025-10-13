#!/usr/bin/env python3
"""Modal proxy that executes workloads on Modal with bidirectional tunneling."""

import asyncio
import json
import logging
import os
import subprocess
from typing import Any, Dict

import modal
from tunnel_manager import TunnelManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModalProxy:
    """Proxy that executes workloads on Modal with cluster access."""

    def __init__(self):
        self.tunnel_manager = TunnelManager()
        self.modal_app = None
        self.modal_function = None

    async def run(self):
        """Main proxy execution."""
        try:
            # Load original pod spec
            spec = self._load_pod_spec()
            logger.info(f"Loaded pod spec: {spec['image']}")

            # Start tunnel for cluster access
            tunnel_url = await self.tunnel_manager.start_tunnel()
            logger.info(f"Tunnel started: {tunnel_url}")

            # Create Modal app and function
            await self._create_modal_function(spec, tunnel_url)

            # Execute on Modal
            result = await self._execute_on_modal(spec)
            logger.info(f"Modal execution completed: {result}")

        except Exception as e:
            logger.error(f"Proxy execution failed: {e}")
            raise

    def _load_pod_spec(self) -> Dict[str, Any]:
        """Load original pod specification."""
        # Get from environment variables set by webhook
        return {
            "image": os.getenv("ORIGINAL_IMAGE", "python:3.11-slim"),
            "command": json.loads(os.getenv("ORIGINAL_COMMAND", '["python"]')),
            "args": json.loads(os.getenv("ORIGINAL_ARGS", '["-c", "print(\\"Hello from Modal!\\")"]')),
            "env": json.loads(os.getenv("ORIGINAL_ENV", "{}")),
        }

    async def _create_modal_function(self, spec: Dict[str, Any], tunnel_url: str):
        """Create Modal app and function."""
        self.modal_app = modal.App("modal-proxy")

        # Create image with original container image as base
        image = modal.Image.from_registry(spec["image"])

        @self.modal_app.function(image=image, cpu=1.0, memory=512, timeout=300, keep_warm=1)
        async def execute_workload(command, args, env_vars, tunnel_url):
            """Execute the original workload on Modal with cluster access."""
            import os

            # Set up environment
            for key, value in env_vars.items():
                os.environ[key] = value

            # Set tunnel URL for cluster access
            os.environ["CLUSTER_TUNNEL_URL"] = tunnel_url

            # Execute original command
            full_command = command + args
            logger.info(f"Executing on Modal: {full_command}")

            try:
                result = subprocess.run(full_command, capture_output=True, text=True, timeout=300)
                return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
            except subprocess.TimeoutExpired:
                return {"returncode": 124, "stdout": "", "stderr": "Command timed out"}

        self.modal_function = execute_workload

    async def _execute_on_modal(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Execute workload on Modal."""
        with self.modal_app.run():
            result = await self.modal_function.remote.aio(
                command=spec["command"],
                args=spec["args"],
                env_vars=spec["env"],
                tunnel_url=await self.tunnel_manager.get_tunnel_url(),
            )
            return result


if __name__ == "__main__":
    proxy = ModalProxy()
    asyncio.run(proxy.run())
