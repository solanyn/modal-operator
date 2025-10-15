#!/usr/bin/env python3
"""
Smart Modal placeholder that can run as ModalJob or ModalFunction.
Automatically detects workload type and routes accordingly.
"""

import asyncio
import json
import logging
import os

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModalPlaceholder:
    def __init__(self):
        self.original_image = os.getenv("ORIGINAL_IMAGE")
        self.original_command = json.loads(os.getenv("ORIGINAL_COMMAND", "[]"))
        self.original_args = json.loads(os.getenv("ORIGINAL_ARGS", "[]"))
        self.modal_proxy_url = os.getenv("MODAL_OPERATOR_PROXY", "http://modal-operator-proxy:8080")

        # Detect workload type
        self.workload_type = self._detect_workload_type()
        logger.info(f"Detected workload type: {self.workload_type}")

    def _detect_workload_type(self):
        """Detect if this should be a ModalJob or ModalFunction."""

        # Check for service/server indicators
        service_indicators = ["serve", "server", "api", "8080", "5000"]
        command_str = str(self.original_command + self.original_args)
        if any(port in command_str for port in service_indicators):
            return "function"

        # Check for batch/job indicators
        if any(cmd in str(self.original_command + self.original_args) for cmd in ["train", "batch", "process", "run"]):
            return "job"

        # Check image type
        if "torchserve" in self.original_image or "api" in self.original_image:
            return "function"

        # Default to job for one-time execution
        return "job"

    async def run_as_job(self):
        """Execute as ModalJob - one-time execution."""
        logger.info("Running as ModalJob")

        # Create ModalJob via operator API
        job_spec = {
            "image": self.original_image,
            "command": self.original_command,
            "args": self.original_args,
            "gpu": os.getenv("GPU_REQUEST", "T4:1"),
            "cpu": os.getenv("CPU_REQUEST", "1.0"),
            "memory": os.getenv("MEMORY_REQUEST", "2Gi"),
        }

        # Submit job and wait for completion
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.modal_proxy_url}/modal-job", json=job_spec) as response:
                result = await response.json()
                logger.info(f"ModalJob result: {result}")

        # Keep container running to maintain pod status
        await asyncio.sleep(3600)  # 1 hour

    async def run_as_function(self):
        """Execute as ModalFunction - serve requests."""
        logger.info("Running as ModalFunction server")

        # Create ModalFunction
        function_spec = {
            "image": self.original_image,
            "handler": self._extract_handler(),
            "gpu": os.getenv("GPU_REQUEST", "T4:1"),
            "cpu": os.getenv("CPU_REQUEST", "1.0"),
            "memory": os.getenv("MEMORY_REQUEST", "2Gi"),
            "concurrency": 10,
        }

        # Deploy function
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.modal_proxy_url}/modal-function", json=function_spec) as response:
                result = await response.json()
                function_url = result.get("function_url")
                logger.info(f"ModalFunction deployed: {function_url}")

        # Start local proxy server
        await self._start_proxy_server(function_url)

    def _extract_handler(self):
        """Extract handler from original command."""
        # Try to detect handler from command
        cmd_str = " ".join(self.original_command + self.original_args)

        if "torchserve" in cmd_str:
            return "torchserve.inference.predict"
        elif "uvicorn" in cmd_str or "fastapi" in cmd_str:
            return "app.main"
        else:
            return "app.handler"  # Default

    async def _start_proxy_server(self, function_url):
        """Start local server that proxies to Modal function."""
        app = web.Application()

        async def proxy_handler(request):
            """Proxy all requests to Modal function."""
            try:
                # Get request data
                if request.content_type == "application/json":
                    data = await request.json()
                else:
                    data = {"body": await request.text()}

                # Call Modal function
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.modal_proxy_url}/modal-function/{os.getenv('POD_NAME', 'default')}", json=data
                    ) as response:
                        result = await response.json()

                return web.json_response(result.get("result", result))

            except Exception as e:
                logger.error(f"Proxy error: {e}")
                return web.json_response({"error": str(e)}, status=500)

        # Route all requests to proxy
        app.router.add_route("*", "/{path:.*}", proxy_handler)

        # Start server on original port
        port = self._extract_port()
        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        logger.info(f"Proxy server started on port {port}")
        logger.info(f"Forwarding requests to Modal function: {function_url}")

        # Keep running
        await asyncio.Future()

    def _extract_port(self):
        """Extract port from original command."""
        cmd_str = " ".join(self.original_command + self.original_args)

        # Common port patterns
        for port in [8080, 5000, 3000, 8000, 80]:
            if str(port) in cmd_str:
                return port

        return 8080  # Default


async def main():
    placeholder = ModalPlaceholder()

    if placeholder.workload_type == "job":
        await placeholder.run_as_job()
    else:
        await placeholder.run_as_function()


if __name__ == "__main__":
    asyncio.run(main())
