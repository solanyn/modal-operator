"""Modal Functions proxy for secure function calling."""

import asyncio
import logging
import os

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModalFunctionProxy:
    """Proxy for calling Modal functions securely."""

    def __init__(self, port=8080):
        self.port = port
        self.app = web.Application()
        self.setup_routes()

        # Get Modal credentials from operator secret
        self.modal_token_id = os.getenv("MODAL_TOKEN_ID")
        self.modal_token_secret = os.getenv("MODAL_TOKEN_SECRET")

    def setup_routes(self):
        self.app.router.add_post("/modal-function/{function_name}", self.call_modal_function)
        self.app.router.add_get("/health", self.health_check)

    async def health_check(self, request):
        return web.json_response({"status": "healthy", "service": "modal-function-proxy"})

    async def call_modal_function(self, request):
        """Proxy calls to Modal functions with authentication."""

        function_name = request.match_info["function_name"]

        try:
            # Get request payload
            payload = await request.json()

            # Get function URL from Kubernetes
            function_url = await self.get_function_url(function_name)
            if not function_url:
                return web.json_response({"error": f"Function {function_name} not found"}, status=404)

            # Call Modal function with operator credentials
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.modal_token_id}:{self.modal_token_secret}",
                    "Content-Type": "application/json",
                }

                logger.info(f"Calling Modal function: {function_url}")

                async with session.post(function_url, json=payload, headers=headers) as response:
                    result = await response.json()

                    return web.json_response({"status": "success", "result": result, "function": function_name})

        except Exception as e:
            logger.error(f"Error calling function {function_name}: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def get_function_url(self, function_name: str) -> str:
        """Get Modal function URL from Kubernetes."""

        try:
            # In real implementation, query Kubernetes API
            # For now, return mock URL
            namespace = os.getenv("NAMESPACE", "default")
            return f"https://func-{function_name}-{namespace}.modal.run"

        except Exception as e:
            logger.error(f"Failed to get function URL for {function_name}: {e}")
            return None


async def main():
    proxy = ModalFunctionProxy()
    runner = web.AppRunner(proxy.app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", proxy.port)
    await site.start()

    logger.info(f"Modal Function Proxy started on port {proxy.port}")
    logger.info("Routes:")
    logger.info("  POST /modal-function/{name} - Call Modal function")
    logger.info("  GET /health - Health check")

    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
