#!/usr/bin/env python3
"""Modal Proxy Container - Executes original pod workloads on Modal.

This container runs inside mutated pods and executes the original workload
on Modal's infrastructure, then reports status back to Kubernetes.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import modal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModalProxy:
    """Proxy that executes original pod workloads on Modal."""

    def __init__(self, config_path: str, secrets_path: Optional[str] = None):
        self.config_path = config_path
        self.secrets_path = secrets_path
        self.modal_spec = self._load_config()
        self.env_vars = self._load_secrets() if secrets_path else {}

    def _load_config(self) -> Dict[str, Any]:
        """Load Modal job specification from ConfigMap."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            logger.info(f"Loaded Modal config: {config}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            sys.exit(1)

    def _load_secrets(self) -> Dict[str, str]:
        """Load sensitive environment variables from Secret."""
        env_vars = {}
        try:
            secrets_dir = Path(self.secrets_path)
            for secret_file in secrets_dir.iterdir():
                if secret_file.is_file():
                    env_vars[secret_file.name] = secret_file.read_text().strip()
            logger.info(f"Loaded {len(env_vars)} secret environment variables")
            return env_vars
        except Exception as e:
            logger.error(f"Failed to load secrets from {self.secrets_path}: {e}")
            return {}

    def run(self) -> int:
        """Execute the original workload on Modal and return exit code."""
        try:
            logger.info("Starting Modal proxy execution")

            # Create Modal app
            app = modal.App("modal-proxy-job")

            # Create Modal image from original container image
            image = modal.Image.from_registry(self.modal_spec["image"])

            # Configure resources
            gpu_config = None
            if self.modal_spec.get("gpu"):
                gpu_type, gpu_count = self._parse_gpu_spec(self.modal_spec["gpu"])
                gpu_config = f"{gpu_type}:{gpu_count}"

            # Create Modal function
            @app.function(
                image=image,
                cpu=float(self.modal_spec.get("cpu", "1.0")),
                memory=self._parse_memory(self.modal_spec.get("memory", "512Mi")),
                gpu=gpu_config,
                timeout=int(self.modal_spec.get("timeout", "3600")),
                retries=int(self.modal_spec.get("retries", "0")),
            )
            def execute_workload():
                """Execute the original container workload."""
                import os
                import subprocess

                # Set environment variables
                for key, value in self.env_vars.items():
                    os.environ[key] = value

                # Execute original command
                command = self.modal_spec.get("command", [])
                args = self.modal_spec.get("args", [])

                if command:
                    full_command = command + args
                    logger.info(f"Executing command: {full_command}")

                    result = subprocess.run(full_command, capture_output=False, text=True)

                    return result.returncode
                else:
                    logger.info("No command specified, container completed successfully")
                    return 0

            # Run the function on Modal
            logger.info("Submitting job to Modal...")
            with app.run():
                exit_code = execute_workload.remote()

            logger.info(f"Modal job completed with exit code: {exit_code}")
            return exit_code

        except Exception as e:
            logger.error(f"Modal proxy execution failed: {e}")
            return 1

    def _parse_gpu_spec(self, gpu_spec: str) -> tuple[str, int]:
        """Parse GPU specification like 'T4:1' or 'A100:2'."""
        if ":" in gpu_spec:
            gpu_type, gpu_count = gpu_spec.split(":", 1)
            return gpu_type, int(gpu_count)
        else:
            return gpu_spec, 1

    def _parse_memory(self, memory_str: str) -> int:
        """Parse memory string to MB integer."""
        if memory_str.endswith("Gi") or memory_str.endswith("G"):
            return int(memory_str.rstrip("Gi")) * 1024
        elif memory_str.endswith("Mi") or memory_str.endswith("M"):
            return int(memory_str.rstrip("Mi"))
        else:
            return int(memory_str)


def main():
    """Main entry point for Modal proxy container."""
    parser = argparse.ArgumentParser(description="Modal Proxy Container")
    parser.add_argument("--config", required=True, help="Path to Modal config file")
    parser.add_argument("--secrets", help="Path to secrets directory")

    args = parser.parse_args()

    # Create and run proxy
    proxy = ModalProxy(args.config, args.secrets)
    exit_code = proxy.run()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
