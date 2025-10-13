#!/usr/bin/env python3
"""Tunnel server running in cluster to provide Modal access to cluster services."""

import asyncio
import logging

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


class ClusterTunnelServer:
    """HTTP tunnel server that forwards requests from Modal to cluster services."""

    def __init__(self, port: int = 8000):
        self.port = port
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        """Setup tunnel routes."""
        # Proxy any request to cluster services
        self.app.router.add_route("*", "/proxy/{service_host}/{service_port}/{path:.*}", self.proxy_request)
        self.app.router.add_route("*", "/proxy/{service_host}/{service_port}", self.proxy_request)
        self.app.router.add_get("/health", self.health_check)

    async def health_check(self, request):
        """Health check endpoint."""
        return web.json_response({"status": "healthy", "tunnel": "active"})

    async def proxy_request(self, request):
        """Proxy request to cluster service."""
        service_host = request.match_info["service_host"]
        service_port = int(request.match_info["service_port"])
        path = request.match_info.get("path", "")

        # Construct target URL
        target_url = f"http://{service_host}:{service_port}"
        if path:
            target_url += f"/{path}"

        # Add query parameters
        if request.query_string:
            target_url += f"?{request.query_string}"

        logger.info(f"Proxying {request.method} {request.url} -> {target_url}")

        try:
            # Forward request to cluster service
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=dict(request.headers),
                    data=await request.read() if request.can_read_body else None,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    # Forward response back
                    body = await response.read()
                    return web.Response(body=body, status=response.status, headers=dict(response.headers))

        except aiohttp.ClientError as e:
            logger.error(f"Proxy error for {target_url}: {e}")
            return web.json_response({"error": f"Service unavailable: {e}"}, status=503)
        except Exception as e:
            logger.error(f"Unexpected proxy error: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def start_server(self):
        """Start the tunnel server."""
        runner = web.AppRunner(self.app)
        await runner.setup()

        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()

        logger.info(f"Cluster tunnel server started on port {self.port}")
        logger.info("Modal jobs can access cluster services via:")
        logger.info("  http://tunnel-server:8000/proxy/mysql.kubeflow.svc.cluster.local/3306")

        # Keep server running
        while True:
            await asyncio.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    server = ClusterTunnelServer()
    asyncio.run(server.start_server())
