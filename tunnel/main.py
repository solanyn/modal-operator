#!/usr/bin/env python3
"""
Custom tunnel proxy to connect Modal workloads to cluster services.
Runs as a pod in the cluster and exposes cluster services via HTTP.
"""

import asyncio
import logging
import os

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TunnelProxy:
    def __init__(self, port=8080):
        self.port = port
        self.app = web.Application()
        self.setup_routes()

        # Modal credentials for function calls
        self.modal_token_id = os.getenv("MODAL_TOKEN_ID")
        self.modal_token_secret = os.getenv("MODAL_TOKEN_SECRET")

    def setup_routes(self):
        self.app.router.add_route("*", "/proxy/{service}/{port}/{path:.*}", self.proxy_request)
        self.app.router.add_route("*", "/proxy/{service}/{port}", self.proxy_request)
        self.app.router.add_post("/modal-function/{function_name}", self.call_modal_function)
        self.app.router.add_route("*", "/modal/{path:.*}", self.proxy_modal_api)
        self.app.router.add_get("/health", self.health_check)

    async def health_check(self, request):
        return web.json_response({"status": "healthy"})

    async def call_modal_function(self, request):
        """Call Modal function with authentication."""

        function_name = request.match_info["function_name"]

        try:
            payload = await request.json()

            # Get function URL from Kubernetes
            function_url = await self.get_function_url(function_name)
            if not function_url:
                return web.json_response(
                    {"error": f"Function {function_name} not found"},
                    status=404
                )

            # CRITICAL: Intercept and merge authorization headers
            headers = dict(request.headers)  # Copy original headers

            # Inject Modal authentication (overrides any existing auth)
            headers["Authorization"] = f"Bearer {self.modal_token_id}:{self.modal_token_secret}"
            headers["Content-Type"] = "application/json"

            # Remove hop-by-hop headers
            for hop_header in ["connection", "upgrade", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding"]:
                headers.pop(hop_header, None)

            logger.info(f"Calling Modal function: {function_url} with injected auth")

            # Forward to Modal with injected credentials
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    function_url,
                    json=payload,
                    headers=headers
                ) as response:
                    result = await response.json()

                    return web.json_response({
                        "status": "success",
                        "result": result,
                        "function": function_name
                    })

        except Exception as e:
            logger.error(f"Error calling function {function_name}: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def proxy_modal_api(self, request):
        """Proxy any Modal API call with authentication injection."""

        path = request.match_info["path"]
        modal_url = f"https://api.modal.com/{path}"

        try:
            # Intercept and merge headers
            headers = dict(request.headers)

            # Inject Modal authentication
            headers["Authorization"] = f"Bearer {self.modal_token_id}:{self.modal_token_secret}"

            # Remove hop-by-hop headers
            for hop_header in ["host", "connection", "upgrade", "proxy-authenticate", "proxy-authorization"]:
                headers.pop(hop_header, None)

            logger.info(f"Proxying Modal API: {request.method} {modal_url}")

            # Forward to Modal API with injected credentials
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=request.method,
                    url=modal_url,
                    headers=headers,
                    data=await request.read()
                ) as response:
                    body = await response.read()

                    # Forward response
                    return web.Response(
                        body=body,
                        status=response.status,
                        headers=dict(response.headers)
                    )

        except Exception as e:
            logger.error(f"Error proxying Modal API {path}: {e}")
            return web.json_response({"error": str(e)}, status=502)

    async def get_function_url(self, function_name: str) -> str:
        """Get Modal function URL from Kubernetes."""

        try:
            # TODO: Query Kubernetes API for ModalFunction resource
            namespace = os.getenv("NAMESPACE", "default")
            return f"https://func-{function_name}-{namespace}.modal.run"

        except Exception as e:
            logger.error(f"Failed to get function URL for {function_name}: {e}")
            return None

    async def proxy_request(self, request):
        service = request.match_info["service"]
        port = int(request.match_info["port"])
        path = request.match_info.get("path", "")

        # Resolve service to cluster DNS
        if not service.endswith(".svc.cluster.local"):
            if "." not in service:
                service = f"{service}.default.svc.cluster.local"
            elif service.count(".") == 1:
                service = f"{service}.svc.cluster.local"

        target_url = f"http://{service}:{port}/{path}"
        logger.info(f"Proxying {request.method} {request.url} -> {target_url}")

        try:
            # Forward request to cluster service
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=request.method, url=target_url, headers=dict(request.headers), data=await request.read()
                ) as response:
                    body = await response.read()
                    return web.Response(body=body, status=response.status, headers=dict(response.headers))
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return web.json_response({"error": f"Failed to connect to {service}:{port}", "details": str(e)}, status=502)


async def main():
    proxy = TunnelProxy()
    runner = web.AppRunner(proxy.app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", proxy.port)
    await site.start()

    logger.info(f"Tunnel proxy started on port {proxy.port}")
    logger.info("Usage: http://proxy:8080/proxy/<service>/<port>[/<path>]")
    logger.info("Modal Functions: POST http://proxy:8080/modal-function/<name>")

    # Keep running
    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
