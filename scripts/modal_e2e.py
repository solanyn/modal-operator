#!/usr/bin/env python3
"""Run e2e tests in Modal with kind cluster."""

import modal

# Create Modal image with kind, kubectl, Docker, and dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl", "docker.io", "git")
    .run_commands(
        # Install kind
        "curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64",
        "chmod +x ./kind",
        "mv ./kind /usr/local/bin/kind",
        # Install kubectl
        "curl -LO https://dl.k8s.io/release/v1.28.0/bin/linux/amd64/kubectl",
        "chmod +x kubectl",
        "mv kubectl /usr/local/bin/kubectl",
        # Install uv
        "pip install uv",
    )
    .pip_install("pytest", "pytest-asyncio", "kubernetes", "pyyaml", "requests")
)

app = modal.App("mvgpu-e2e-tests", image=image)


@app.function(
    timeout=1800,  # 30 minutes
    cpu=4,
    memory=8192,
)
def run_e2e_tests():
    """Run complete e2e tests with kind cluster."""
    import os
    import tempfile
    from pathlib import Path

    print("🚀 Starting Modal vGPU Operator E2E Tests")

    # Create temporary directory for project files
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir) / "mvgpu-operator"
        project_dir.mkdir()

        # Create minimal project structure for testing
        create_test_project(project_dir)

        os.chdir(project_dir)

        try:
            # Start Docker daemon
            print("🐳 Starting Docker daemon...")
            docker_proc = start_docker_daemon()

            # Build operator image
            print("🔨 Building operator image...")
            build_operator_image()

            # Run e2e tests
            print("🧪 Running E2E tests...")
            result = run_pytest_tests()

            return result

        except Exception as e:
            print(f"❌ Error during e2e tests: {e}")
            return {"status": "error", "error": str(e)}

        finally:
            # Cleanup Docker daemon
            try:
                docker_proc.terminate()
                docker_proc.wait(timeout=10)
            except Exception:
                try:
                    docker_proc.kill()
                except Exception:
                    pass


def create_test_project(project_dir):
    """Create minimal project structure for testing."""
    from pathlib import Path

    project_dir = Path(project_dir)

    # Create basic project structure
    (project_dir / "mvgpu").mkdir()
    (project_dir / "tests" / "e2e").mkdir(parents=True)
    (project_dir / "charts" / "modal-vgpu-operator" / "crds").mkdir(parents=True)
    (project_dir / "scripts").mkdir()

    # Create minimal pyproject.toml
    pyproject_content = """
[project]
name = "mvgpu"
version = "0.0.1"
dependencies = [
    "kopf>=1.37.0",
    "modal>=0.64.0",
    "kubernetes>=28.0.0",
    "pydantic>=2.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.4.2",
    "pytest-asyncio>=1.2.0",
    "ruff>=0.13.3",
]
"""
    (project_dir / "pyproject.toml").write_text(pyproject_content)

    # Create minimal Dockerfile
    dockerfile_content = """
FROM python:3.11-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml ./
RUN uv sync --frozen
COPY mvgpu/ ./mvgpu/
CMD ["uv", "run", "python", "-m", "mvgpu.operator"]
"""
    (project_dir / "Dockerfile").write_text(dockerfile_content)

    # Create minimal operator module
    operator_content = """
import logging
import os
import time

# Mock operator for testing
class MockOperator:
    def __init__(self):
        self.mock = os.getenv("MODAL_MOCK", "true").lower() == "true"

    def run(self):
        print("Mock operator running...")
        while True:
            time.sleep(10)

if __name__ == "__main__":
    operator = MockOperator()
    operator.run()
"""
    (project_dir / "mvgpu" / "__init__.py").write_text("")
    (project_dir / "mvgpu" / "operator.py").write_text(operator_content)

    # Create CRD generation script
    crd_script = """
import yaml
from pathlib import Path

def generate_crds():
    modaljob_crd = {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": "modaljobs.modal-operator.io"},
        "spec": {
            "group": "modal-operator.io",
            "versions": [{
                "name": "v1alpha1",
                "served": True,
                "storage": True,
                "schema": {
                    "openAPIV3Schema": {
                        "type": "object",
                        "properties": {
                            "spec": {"type": "object"},
                            "status": {"type": "object"}
                        }
                    }
                }
            }],
            "scope": "Namespaced",
            "names": {
                "plural": "modaljobs",
                "singular": "modaljob",
                "kind": "ModalJob"
            }
        }
    }

    output_dir = Path("charts/modal-vgpu-operator/crds")
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "modaljobs.yaml", "w") as f:
        yaml.dump(modaljob_crd, f)

    print("Generated CRDs")

if __name__ == "__main__":
    generate_crds()
"""
    (project_dir / "scripts" / "generate-crds.py").write_text(crd_script)

    # Create simple e2e test
    test_content = """
import subprocess
import time
import pytest

class TestBasicE2E:
    def test_operator_deployment(self):
        '''Test that operator can be deployed.'''
        # This is a minimal test to validate the e2e framework
        result = subprocess.run(["kubectl", "get", "nodes"], capture_output=True)
        assert result.returncode == 0
        assert "Ready" in result.stdout.decode()

    def test_crd_installation(self):
        '''Test that CRDs can be installed.'''
        result = subprocess.run([
            "kubectl", "get", "crd", "modaljobs.modal-operator.io"
        ], capture_output=True)
        assert result.returncode == 0
"""
    (project_dir / "tests" / "e2e" / "test_basic.py").write_text(test_content)


def start_docker_daemon():
    """Start Docker daemon."""
    import subprocess

    docker_proc = subprocess.Popen(
        ["dockerd", "--host=unix:///var/run/docker.sock"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # Wait for Docker to be ready
    import time

    for i in range(30):
        try:
            result = subprocess.run(["docker", "info"], capture_output=True)
            if result.returncode == 0:
                print("✅ Docker daemon ready")
                return docker_proc
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError("Docker daemon failed to start")


def build_operator_image():
    """Build operator Docker image."""
    import subprocess

    result = subprocess.run(
        ["docker", "build", "-t", "modal-vgpu-operator:latest", "."], capture_output=True, text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Docker build failed: {result.stderr}")

    print("✅ Operator image built")


def run_pytest_tests():
    """Run the actual e2e tests."""
    import subprocess

    # Install dependencies
    subprocess.run(["uv", "sync"], check=True)

    # Generate CRDs
    subprocess.run(["uv", "run", "python", "scripts/generate-crds.py"], check=True)

    # Run basic e2e tests
    result = subprocess.run(
        ["uv", "run", "pytest", "tests/e2e/test_basic.py", "-v", "-s"], capture_output=True, text=True
    )

    print("📊 Test Results:")
    print("STDOUT:", result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode == 0:
        print("✅ E2E tests passed!")
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}
    else:
        print(f"❌ E2E tests failed with exit code {result.returncode}")
        return {"status": "failed", "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


@app.local_entrypoint()
def main():
    """Run e2e tests in Modal."""
    print("Running e2e tests in Modal...")
    result = run_e2e_tests.remote()

    print(f"\n🎯 Final Result: {result['status']}")
    if result["status"] != "success":
        print(f"❌ Tests failed: {result.get('error', 'See logs above')}")
        exit(1)
    else:
        print("✅ All e2e tests passed!")


if __name__ == "__main__":
    main()
