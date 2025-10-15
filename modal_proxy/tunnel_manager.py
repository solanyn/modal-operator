#!/usr/bin/env python3
"""Bidirectional tunnel manager for Modal-Kubernetes connectivity."""

import json
import logging
import time
from typing import Any, Dict, Optional

import modal
import websockets

logger = logging.getLogger(__name__)


class TunnelManager:
    """Manages bidirectional tunneling between Modal and Kubernetes cluster."""

    def __init__(self):
        self.tunnel_url: Optional[str] = None
        self.tunnel_app = None
        self.websocket_server = None

    async def start_tunnel(self) -> str:
        """Start bidirectional tunnel."""
        try:
            # Create Modal tunnel app
            self.tunnel_app = modal.App("modal-k8s-tunnel")

            # Create tunnel endpoint on Modal
            @self.tunnel_app.function(keep_warm=1, timeout=3600, allow_concurrent_inputs=10)
            @modal.web_endpoint(method="GET", label="tunnel")
            async def tunnel_endpoint():
                return {"status": "tunnel_active", "timestamp": time.time()}

            # Create WebSocket tunnel for bidirectional communication
            @self.tunnel_app.function(keep_warm=1, timeout=3600)
            @modal.web_endpoint(method="GET", label="ws-tunnel")
            async def websocket_tunnel():
                """WebSocket endpoint for bidirectional communication."""
                return await self._handle_websocket_connection()

            # Deploy tunnel
            with self.tunnel_app.run():
                self.tunnel_url = tunnel_endpoint.web_url
                logger.info(f"Modal tunnel deployed: {self.tunnel_url}")

                # Start local WebSocket server for kubectl exec support
                await self._start_local_websocket_server()

                return self.tunnel_url

        except Exception as e:
            logger.error(f"Failed to start tunnel: {e}")
            raise

    async def _start_local_websocket_server(self):
        """Start local WebSocket server for kubectl exec."""

        async def handle_exec_connection(websocket, path):
            """Handle kubectl exec WebSocket connections."""
            logger.info(f"New exec connection: {path}")

            try:
                # Forward exec commands to Modal
                async for message in websocket:
                    data = json.loads(message)

                    if data.get("type") == "exec":
                        # Execute command on Modal and return result
                        result = await self._execute_on_modal(data["command"])
                        await websocket.send(json.dumps({"type": "exec_result", "result": result}))

                    elif data.get("type") == "service_request":
                        # Forward service request to cluster
                        result = await self._forward_to_cluster(data)
                        await websocket.send(json.dumps({"type": "service_response", "result": result}))

            except websockets.exceptions.ConnectionClosed:
                logger.info("Exec connection closed")
            except Exception as e:
                logger.error(f"Exec connection error: {e}")

        # Start WebSocket server on port 8080 for kubectl exec
        self.websocket_server = await websockets.serve(handle_exec_connection, "0.0.0.0", 8080)
        logger.info("WebSocket server started on port 8080")

    async def _handle_websocket_connection(self):
        """Handle WebSocket connections from Modal."""
        # This would be implemented as a proper WebSocket handler
        # For now, return a simple response
        return {"status": "websocket_ready"}

    async def _execute_on_modal(self, command: str) -> Dict[str, Any]:
        """Execute command on Modal container."""
        # This would forward the command to the actual Modal function
        # For now, simulate execution
        return {"stdout": f"Executed on Modal: {command}", "stderr": "", "returncode": 0}

    async def _forward_to_cluster(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Forward service request to Kubernetes cluster."""
        try:
            # Extract service details
            service_host = request.get("host")
            service_port = request.get("port")

            # Use kubectl proxy or direct service access
            # For now, simulate cluster access
            return {
                "status": "success",
                "data": f"Connected to {service_host}:{service_port}",
                "cluster_accessible": True,
            }

        except Exception as e:
            return {"status": "error", "error": str(e), "cluster_accessible": False}

    async def get_tunnel_url(self) -> Optional[str]:
        """Get current tunnel URL."""
        return self.tunnel_url

    async def stop_tunnel(self):
        """Stop the tunnel."""
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()

        if self.tunnel_app:
            # Modal apps are automatically cleaned up
            pass

        logger.info("Tunnel stopped")
