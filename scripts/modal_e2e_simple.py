#!/usr/bin/env python3
"""Run simplified e2e tests in Modal without Docker-in-Docker."""

import modal

# Simpler image without Docker
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl", "git")
    .run_commands(
        # Install kubectl (for validation)
        "curl -LO https://dl.k8s.io/release/v1.28.0/bin/linux/amd64/kubectl",
        "chmod +x kubectl",
        "mv kubectl /usr/local/bin/kubectl",
        # Install uv
        "pip install uv",
    )
    .pip_install("pytest", "pytest-asyncio", "kubernetes", "pyyaml", "requests")
)

app = modal.App("mvgpu-e2e-simple", image=image)


@app.function(timeout=600, cpu=2, memory=4096)
def run_framework_tests():
    """Run framework validation tests."""
    import subprocess
    import tempfile
    from pathlib import Path

    print("🚀 Starting Modal vGPU Framework Tests")

    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir) / "mvgpu-operator"
        project_dir.mkdir()

        # Create test project structure
        create_test_project(project_dir)

        import os

        os.chdir(project_dir)

        try:
            # Install dependencies
            print("📦 Installing dependencies...")
            subprocess.run(["uv", "sync"], check=True)

            # Generate CRDs
            print("🔧 Generating CRDs...")
            subprocess.run(["uv", "run", "python", "scripts/generate-crds.py"], check=True)

            # Run unit tests (not requiring k8s cluster)
            print("🧪 Running framework tests...")
            result = subprocess.run(["uv", "run", "pytest", "tests/", "-v", "-s"], capture_output=True, text=True)

            print("📊 Test Results:")
            print("STDOUT:", result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)

            if result.returncode == 0:
                print("✅ Framework tests passed!")
                return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}
            else:
                print(f"❌ Framework tests failed with exit code {result.returncode}")
                return {
                    "status": "failed",
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }

        except Exception as e:
            print(f"❌ Error during tests: {e}")
            return {"status": "error", "error": str(e)}


def create_test_project(project_dir):
    """Create test project structure."""
    from pathlib import Path

    project_dir = Path(project_dir)

    # Create directories
    (project_dir / "mvgpu").mkdir()
    (project_dir / "tests").mkdir()
    (project_dir / "charts" / "modal-vgpu-operator" / "crds").mkdir(parents=True)
    (project_dir / "scripts").mkdir()

    # Create pyproject.toml
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

    # Create basic modules
    (project_dir / "mvgpu" / "__init__.py").write_text("")

    # Create CRD models
    crds_content = '''
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class ModalJobSpec(BaseModel):
    """Specification for a Modal job."""
    image: str = Field(description="Container image to run")
    command: List[str] = Field(default_factory=list, description="Command to execute")
    cpu: str = Field(default="1.0", description="CPU allocation")
    memory: str = Field(default="512Mi", description="Memory allocation")
    gpu: Optional[str] = Field(default=None, description="GPU specification")
    replicas: int = Field(default=1, description="Number of replicas")
    enable_i6pn: bool = Field(default=False, description="Enable i6pn networking")

class ModalJobStatus(BaseModel):
    """Status of a Modal job."""
    phase: str = Field(default="Pending", description="Job phase")
    modal_app_id: Optional[str] = Field(default=None, description="Modal app ID")
    message: Optional[str] = Field(default=None, description="Status message")
'''
    (project_dir / "mvgpu" / "crds.py").write_text(crds_content)

    # Create networking module
    networking_content = '''
from pydantic import BaseModel, Field
from typing import Optional

class NetworkingConfig(BaseModel):
    """Configuration for Modal networking features."""
    enable_i6pn: bool = Field(default=False, description="Enable IPv6 private networking")
    cluster_size: Optional[int] = Field(default=None, description="Number of replicas")

class NetworkingController:
    """Controls networking features for Modal vGPU operator."""
    
    def __init__(self, modal_controller):
        self.modal_controller = modal_controller
    
    def validate_networking_config(self, config: NetworkingConfig):
        """Validate networking configuration."""
        errors = []
        if config.cluster_size and config.cluster_size > 1 and not config.enable_i6pn:
            errors.append("Multi-replica jobs require i6pn networking to be enabled")
        return errors
'''
    (project_dir / "mvgpu" / "networking.py").write_text(networking_content)

    # Create CRD generation script
    crd_script = '''
import yaml
from pathlib import Path

def generate_crds():
    """Generate CRD YAML files."""
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
'''
    (project_dir / "scripts" / "generate-crds.py").write_text(crd_script)

    # Create unit tests
    test_content = '''
import pytest
from modal_operator.crds import ModalJobSpec, ModalJobStatus
from modal_operator.controllers.networking_controller import NetworkingConfig, NetworkingController

class TestCRDs:
    """Test CRD models."""
    
    def test_modal_job_spec_creation(self):
        """Test ModalJobSpec creation."""
        spec = ModalJobSpec(
            image="python:3.11",
            command=["python", "-c", "print('hello')"]
        )
        assert spec.image == "python:3.11"
        assert spec.command == ["python", "-c", "print('hello')"]
        assert spec.replicas == 1
        assert spec.enable_i6pn is False
    
    def test_modal_job_spec_with_networking(self):
        """Test ModalJobSpec with networking."""
        spec = ModalJobSpec(
            image="pytorch/pytorch:latest",
            command=["python", "train.py"],
            replicas=3,
            enable_i6pn=True
        )
        assert spec.replicas == 3
        assert spec.enable_i6pn is True
    
    def test_modal_job_status(self):
        """Test ModalJobStatus."""
        status = ModalJobStatus(
            phase="Running",
            modal_app_id="app-123",
            message="Job is running"
        )
        assert status.phase == "Running"
        assert status.modal_app_id == "app-123"

class TestNetworking:
    """Test networking functionality."""
    
    def test_networking_config(self):
        """Test networking configuration."""
        config = NetworkingConfig(enable_i6pn=True, cluster_size=2)
        assert config.enable_i6pn is True
        assert config.cluster_size == 2
    
    def test_networking_validation(self):
        """Test networking validation."""
        controller = NetworkingController(None)
        
        # Valid config
        valid_config = NetworkingConfig(enable_i6pn=True, cluster_size=2)
        errors = controller.validate_networking_config(valid_config)
        assert len(errors) == 0
        
        # Invalid config
        invalid_config = NetworkingConfig(enable_i6pn=False, cluster_size=3)
        errors = controller.validate_networking_config(invalid_config)
        assert len(errors) == 1
        assert "Multi-replica jobs require i6pn" in errors[0]

class TestFramework:
    """Test framework functionality."""
    
    def test_imports(self):
        """Test that all modules can be imported."""
        import modal_operator.crds
        import modal_operator.controllers.networking_controller
        assert True
    
    def test_pydantic_validation(self):
        """Test Pydantic validation works."""
        from modal_operator.crds import ModalJobSpec
        
        # Valid spec
        spec = ModalJobSpec(image="test:latest")
        assert spec.image == "test:latest"
        
        # Test defaults
        assert spec.cpu == "1.0"
        assert spec.memory == "512Mi"
        assert spec.replicas == 1
'''
    (project_dir / "tests" / "test_framework.py").write_text(test_content)


@app.local_entrypoint()
def main():
    """Run framework tests in Modal."""
    print("Running framework validation tests in Modal...")
    result = run_framework_tests.remote()

    print(f"\\n🎯 Final Result: {result['status']}")
    if result["status"] != "success":
        print(f"❌ Tests failed: {result.get('error', 'See logs above')}")
        exit(1)
    else:
        print("✅ All framework tests passed!")


if __name__ == "__main__":
    main()
