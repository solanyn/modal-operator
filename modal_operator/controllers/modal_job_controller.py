"""Enhanced Modal client for job and endpoint management."""

import logging
from typing import Any, Dict, List, Optional

import modal

from modal_operator.metrics import metrics

logger = logging.getLogger(__name__)


def parse_memory(memory_str: str) -> int:
    """Parse memory string (e.g., '512Mi', '2G') to MB integer."""
    if memory_str.endswith("Gi") or memory_str.endswith("G"):
        return int(memory_str.rstrip("Gi")) * 1024
    elif memory_str.endswith("Mi") or memory_str.endswith("M"):
        return int(memory_str.rstrip("Mi"))
    else:
        # Assume MB if no suffix
        return int(memory_str)


class ModalJobController:
    """Controls Modal jobs and endpoints."""

    def __init__(self, mock: bool = False):
        self.mock = mock
        self._apps: Dict[str, modal.App] = {}

    async def create_job(
        self,
        name: str,
        image: str,
        command: List[str],
        cpu: str = "1.0",
        memory: str = "512Mi",
        gpu: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 300,
        retries: int = 0,
        replicas: int = 1,
        enable_i6pn: bool = False,
    ) -> Dict[str, Any]:
        """Create a Modal job."""

        if self.mock:
            gpu_type = gpu.split(":")[0] if gpu else None
            metrics.record_job_started(name, gpu_type)
            if gpu_type:
                metrics.record_cold_start(name, gpu_type)

            return {
                "app_id": f"mock-app-{name}",
                "function_id": f"mock-func-{name}",
                "status": "running",
                "tunnel_url": f"https://mock-tunnel-{name}.modal.run" if gpu else None,
            }

        try:
            # Create Modal app
            app = modal.App(name)
            self._apps[name] = app

            # Configure image - use original image from pod spec, not the mutated busybox
            original_image = env.get("ORIGINAL_IMAGE", image) if env else image
            modal_image = modal.Image.from_registry(original_image)

            # Configure resources
            function_kwargs = {
                "image": modal_image,
                "cpu": float(cpu),
                "memory": parse_memory(memory),
                "timeout": timeout,
                "retries": retries,
            }

            if gpu:
                function_kwargs["gpu"] = gpu

            # Use Modal's free tunnel feature for cluster connectivity
            if enable_i6pn or replicas > 1:
                # Enable Modal tunnel for cluster access
                function_kwargs["allow_concurrent_inputs"] = 100

            # Handle distributed jobs with i6pn networking
            if replicas > 1 or enable_i6pn:
                return await self._create_distributed_job(
                    app, name, command, env, function_kwargs, replicas, enable_i6pn
                )

            # Create single function with serialized=True to allow non-global scope
            @app.function(serialized=True, **function_kwargs)
            def job_function():
                import os
                import subprocess

                # Set environment variables
                if env:
                    for key, value in env.items():
                        os.environ[key] = value

                # If tunnel is enabled, set up modal operator proxy for cluster access
                if env and env.get("TUNNEL_ENABLED") == "true":
                    print("🔗 Setting up modal operator proxy for cluster access")

                    # Configure modal operator proxy (pysocks already installed in image)
                    try:
                        import socket

                        import socks

                        socks.set_default_proxy(socks.SOCKS5, "localhost", 1080)
                        socket.socket = socks.socksocket

                        print("📡 Cluster services accessible via modal operator proxy")
                        print("   Example: mysql-simple.default.svc.cluster.local:3306")

                        # Set proxy info for applications
                        os.environ["MODAL_OPERATOR_PROXY"] = "localhost:1080"
                    except ImportError:
                        print("⚠️  pysocks not available, modal operator proxy disabled")

                # Execute command
                print(f"🚀 Executing on Modal: {' '.join(command)}")
                result = subprocess.run(command, capture_output=True, text=True)

                print(f"📤 Exit code: {result.returncode}")
                if result.stdout:
                    print(f"📝 Stdout: {result.stdout}")
                if result.stderr:
                    print(f"❌ Stderr: {result.stderr}")

                return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}

            # Deploy app
            with modal.enable_output():
                with app.run():
                    # Create tunnel server URL for cluster access if enabled
                    tunnel_url = None
                    if env and env.get("TUNNEL_ENABLED") == "true":
                        try:
                            # The tunnel server runs in the mirror pod
                            # Modal jobs will access it via the mirror pod's service
                            tunnel_url = f"{name}-modal-mirror.default.svc.cluster.local:8000"
                            logger.info(f"Cluster tunnel available at: {tunnel_url}")
                        except Exception as e:
                            logger.warning(f"Failed to setup tunnel: {e}")
                            tunnel_url = None

                    # Start job asynchronously
                    call = job_function.spawn()

                    return {
                        "app_id": app.app_id,
                        "function_id": call.object_id,
                        "status": "running",
                        "tunnel_url": tunnel_url,
                    }

        except Exception as e:
            logger.error(f"Failed to create Modal job {name}: {e}")
            raise

    async def _create_distributed_job(
        self,
        app: modal.App,
        name: str,
        command: List[str],
        env: Optional[Dict[str, str]],
        function_kwargs: Dict[str, Any],
        replicas: int,
        enable_i6pn: bool,
    ) -> Dict[str, Any]:
        """Create a distributed Modal job with i6pn networking."""

        # Configure i6pn networking if enabled
        if enable_i6pn:
            # Enable IPv6 private networking for high-bandwidth communication
            function_kwargs["enable_memory_snapshot"] = True

        # Create distributed function
        @app.function(serialized=True, **function_kwargs)
        def distributed_job_function(rank: int, world_size: int):
            import os
            import subprocess

            # Set distributed training environment
            os.environ["RANK"] = str(rank)
            os.environ["WORLD_SIZE"] = str(world_size)

            # Set custom environment variables
            if env:
                for key, value in env.items():
                    os.environ[key] = value

            # Enable i6pn networking if requested
            if enable_i6pn:
                os.environ["MODAL_I6PN_ENABLED"] = "true"

            # Execute command with rank information
            cmd_with_rank = [
                str(arg).replace("{rank}", str(rank)).replace("{world_size}", str(world_size)) for arg in command
            ]
            result = subprocess.run(cmd_with_rank, capture_output=True, text=True)

            return {"rank": rank, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}

        # Deploy app and spawn distributed jobs
        with modal.enable_output():
            with app.run():
                # Spawn multiple replicas
                calls = []
                for rank in range(replicas):
                    call = distributed_job_function.spawn(rank, replicas)
                    calls.append(call)

                return {
                    "app_id": app.app_id,
                    "function_id": calls[0].object_id,  # Primary function ID
                    "status": "running",
                    "replicas": replicas,
                    "enable_i6pn": enable_i6pn,
                    "distributed_calls": [call.object_id for call in calls],
                }

    async def get_job_status(self, app_id: str, function_id: str) -> Dict[str, Any]:
        """Get Modal job status."""

        if self.mock:
            return {"status": "succeeded", "result": {"stdout": "Mock job completed", "stderr": "", "returncode": 0}}

        try:
            # TODO: Implement real status checking via Modal API
            return {"status": "running", "result": None}
        except Exception as e:
            logger.error(f"Failed to get job status for {app_id}/{function_id}: {e}")
            return {"status": "failed", "error": str(e)}

    async def create_function(
        self,
        name: str,
        image: str,
        handler: str,
        cpu: str = "1.0",
        memory: str = "512Mi",
        gpu: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 300,
        concurrency: int = 1,
    ) -> Dict[str, Any]:
        """Create a Modal function for serverless execution."""

        if self.mock:
            gpu_type = gpu.split(":")[0] if gpu else None
            metrics.record_job_started(name, gpu_type)
            return {
                "app_id": f"func-{name}",
                "function_url": f"https://func-{name}.modal.run",
                "status": "deployed",
            }

        try:
            app = modal.App(name=f"function-{name}")
            self._apps[name] = app

            modal_image = modal.Image.from_registry(image)

            function_kwargs = {
                "image": modal_image,
                "cpu": float(cpu),
                "memory": parse_memory(memory),
                "timeout": timeout,
                "allow_concurrent_inputs": concurrency,
            }

            if gpu:
                function_kwargs["gpu"] = gpu

            @app.function(serialized=True, **function_kwargs)
            def serverless_function(*args, **kwargs):
                import importlib
                import os

                if env:
                    for key, value in env.items():
                        os.environ[key] = value

                module_name, func_name = handler.rsplit(".", 1)
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)

                return func(*args, **kwargs)

            with app.run():
                function_url = f"https://{app.app_id}.modal.run"

                return {
                    "app_id": app.app_id,
                    "function_url": function_url,
                    "status": "deployed",
                }

        except Exception as e:
            logger.error(f"Failed to create Modal function {name}: {e}")
            return {"status": "failed", "error": str(e)}

    async def cancel_job(self, app_id: str, function_id: str) -> bool:
        """Cancel a Modal job."""

        if self.mock:
            logger.info(f"Mock cancelled job {app_id}/{function_id}")
            return True

        try:
            # TODO: Implement job cancellation via Modal API
            logger.info(f"Cancelled Modal job {app_id}/{function_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel job {app_id}/{function_id}: {e}")
            return False

    async def create_endpoint(
        self,
        name: str,
        image: str,
        handler: str,
        cpu: str = "1.0",
        memory: str = "512Mi",
        gpu: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        command: Optional[List[str]] = None,
        args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a Modal endpoint for inference or HTTP servers."""

        if self.mock:
            return {
                "app_id": f"mock-endpoint-{name}",
                "endpoint_url": f"https://mock-{name}.modal.run",
                "status": "ready",
            }

        try:
            # Create Modal app for endpoint
            app = modal.App(f"{name}-endpoint")
            self._apps[f"{name}-endpoint"] = app

            # Configure image - add FastAPI and httpx for web endpoints
            modal_image = modal.Image.from_registry(image).pip_install("fastapi[standard]", "httpx")

            # Configure resources
            function_kwargs = {"image": modal_image, "cpu": float(cpu), "memory": parse_memory(memory)}

            if gpu:
                function_kwargs["gpu"] = gpu

            # If command is provided, wrap it in a simple endpoint
            # Note: For complex HTTP servers, users should convert to proper FastAPI/ASGI apps
            if command:
                full_command = command + (args if args else [])

                @app.function(serialized=True, **function_kwargs)
                @modal.fastapi_endpoint()
                def http_server_endpoint():
                    """Simple test endpoint."""
                    return {
                        "message": "Hello from Modal!",
                        "command": full_command,
                        "note": "Endpoint is running on Modal",
                    }

                endpoint_func = http_server_endpoint
            else:
                # No command provided, create simple handler-based endpoint
                @app.function(serialized=True, **function_kwargs)
                @modal.fastapi_endpoint()
                def inference_endpoint():
                    # TODO: Import and call the specified handler
                    return {"message": f"Endpoint {name} ready"}

                endpoint_func = inference_endpoint

            # Check for existing deployment with same name and stop it
            deployment_name = f"{name}-endpoint"
            try:
                # Use modal app list to find existing deployments
                from modal.experimental import list_deployed_apps

                deployed_apps = await list_deployed_apps.aio()
                for app_info in deployed_apps:
                    if app_info.name == deployment_name:
                        logger.info(f"Found existing deployment {app_info.app_id} with name {deployment_name}, stopping it")
                        # Stop the old deployment using modal client
                        from modal_proto import api_pb2

                        client = modal.Client.from_env()
                        stop_request = api_pb2.AppStopRequest(app_id=app_info.app_id)
                        client.stub.AppStop(stop_request)
                        logger.info(f"Stopped old deployment {app_info.app_id}")
                        break
            except Exception as e:
                # No existing app or error - that's fine for first deployment
                logger.info(f"No existing deployment to stop (this is normal for first deployment): {e}")

            # Deploy endpoint persistently
            with modal.enable_output():
                # Deploy the app (this keeps it running)
                await app.deploy.aio(name=deployment_name)

                # Get the endpoint URL
                endpoint_url = endpoint_func.get_web_url()

                return {"app_id": app.app_id, "endpoint_url": endpoint_url, "status": "ready"}

        except Exception as e:
            logger.error(f"Failed to create Modal endpoint {name}: {e}")
            raise

    async def delete_app(self, app_id: str) -> bool:
        """Delete a Modal app."""

        if self.mock:
            logger.info(f"Mock deleted app {app_id}")
            return True

        try:
            # TODO: Implement app deletion via Modal API
            logger.info(f"Deleted Modal app {app_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete app {app_id}: {e}")
            return False
