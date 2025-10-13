"""Enhanced networking support for Modal vGPU operator with i6pn integration."""

from typing import Any, Dict, List, Optional

import modal
from pydantic import BaseModel, Field

from modal_operator.modal_client import ModalJobController


class NetworkingConfig(BaseModel):
    """Configuration for Modal networking features."""

    enable_i6pn: bool = Field(default=False, description="Enable IPv6 private networking")
    cluster_size: Optional[int] = Field(default=None, description="Number of replicas for clustered jobs")


class ClusterCoordinator:
    """Manages clustered Modal functions for distributed workloads."""

    def __init__(self, modal_controller: ModalJobController):
        self.modal_controller = modal_controller
        # Use ephemeral dict for testing, or None for mock mode
        if modal_controller.mock:
            self.cluster_registry = {}  # Use regular dict for mock mode
        else:
            self.cluster_registry = modal.Dict.ephemeral()

    def create_clustered_job(
        self, job_name: str, replicas: int, config: NetworkingConfig, image: str, command: List[str]
    ) -> Dict[str, Any]:
        """Create a clustered Modal job with i6pn networking."""

        app = modal.App(f"{job_name}-cluster")

        # Configure function with i6pn if enabled
        function_kwargs = {"image": modal.Image.from_registry(image), "cpu": 2.0, "memory": 4096}

        if config.enable_i6pn:
            function_kwargs["i6pn"] = True

        @app.function(**function_kwargs)
        def clustered_worker(replica_id: int, total_replicas: int):
            """Worker function for clustered job."""
            import socket

            result = {"replica_id": replica_id, "total_replicas": total_replicas, "status": "running"}

            if config.enable_i6pn:
                # Get i6pn address
                try:
                    i6pn_addr = socket.getaddrinfo("i6pn.modal.local", None, socket.AF_INET6)[0][4][0]
                    result["i6pn_address"] = i6pn_addr

                    # Register address in cluster registry
                    if self.modal_controller.mock:
                        self.cluster_registry[f"{job_name}-replica-{replica_id}"] = i6pn_addr
                    else:
                        self.cluster_registry[f"{job_name}-replica-{replica_id}"] = i6pn_addr
                except Exception as e:
                    result["i6pn_error"] = str(e)

            # Execute the actual command
            import subprocess

            try:
                proc_result = subprocess.run(command, capture_output=True, text=True)
                result["command_output"] = proc_result.stdout
                result["command_error"] = proc_result.stderr
                result["exit_code"] = proc_result.returncode
            except Exception as e:
                result["execution_error"] = str(e)
                result["exit_code"] = 1

            return result

        # Launch all replicas
        with app.run():
            futures = []
            for i in range(replicas):
                future = clustered_worker.spawn(i, replicas)
                futures.append(future)

            # Wait for all replicas to complete
            results = []
            for future in futures:
                try:
                    result = future.get()
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e), "status": "failed"})

        return {
            "job_name": job_name,
            "replicas": replicas,
            "results": results,
            "networking": {
                "i6pn_enabled": config.enable_i6pn,
                "cluster_addresses": dict(self.cluster_registry) if config.enable_i6pn else {},
            },
        }

    def get_cluster_status(self, job_name: str) -> Dict[str, Any]:
        """Get status of a clustered job."""
        cluster_data = {}

        # Get all entries for this job from registry
        if self.modal_controller.mock:
            # Regular dict for mock mode
            for key, value in self.cluster_registry.items():
                if key.startswith(f"{job_name}-replica-"):
                    cluster_data[key] = value
        else:
            # Modal Dict for real mode
            for key in self.cluster_registry.keys():
                if key.startswith(f"{job_name}-replica-"):
                    cluster_data[key] = self.cluster_registry[key]

        return {"job_name": job_name, "active_replicas": len(cluster_data), "replica_addresses": cluster_data}


class NetworkingController:
    """Controls networking features for Modal vGPU operator."""

    def __init__(self, modal_controller: ModalJobController):
        self.modal_controller = modal_controller
        self.coordinator = ClusterCoordinator(modal_controller)

    def create_networked_job(self, job_spec: Dict[str, Any], networking_config: NetworkingConfig) -> Dict[str, Any]:
        """Create a job with enhanced networking capabilities."""

        job_name = job_spec.get("name", "networked-job")
        replicas = networking_config.cluster_size or 1

        if replicas > 1 and networking_config.enable_i6pn:
            # Use clustered approach for multi-replica jobs
            return self.coordinator.create_clustered_job(
                job_name=job_name,
                replicas=replicas,
                config=networking_config,
                image=job_spec.get("image", "python:3.11"),
                command=job_spec.get("command", ["echo", "Hello from Modal cluster"]),
            )
        else:
            # Single replica or non-clustered job - use synchronous call
            # Note: This would need to be adapted based on actual ModalJobManager API
            job_data = {
                "name": job_name,
                "image": job_spec.get("image", "python:3.11"),
                "command": job_spec.get("command", ["echo", "Hello"]),
            }
            # For now, return the job spec - actual implementation would call modal_manager
            return {"status": "created", "job": job_data}

    def validate_networking_config(self, config: NetworkingConfig) -> List[str]:
        """Validate networking configuration."""
        errors = []

        if config.cluster_size and config.cluster_size > 1 and not config.enable_i6pn:
            errors.append("Multi-replica jobs require i6pn networking to be enabled")

        return errors
