"""Custom Resource Definitions for Modal vGPU operator."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModalJobSpec(BaseModel):
    """Specification for a Modal job."""

    image: str = Field(description="Container image to run")
    command: List[str] = Field(default_factory=list, description="Command to execute")
    args: List[str] = Field(default_factory=list, description="Arguments to command")

    # Resources
    cpu: str = Field(default="1.0", description="CPU allocation")
    memory: str = Field(default="512Mi", description="Memory allocation")
    gpu: Optional[str] = Field(default=None, description="GPU specification (e.g., T4:1)")

    # Environment
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")

    # Modal-specific
    timeout: int = Field(default=300, description="Job timeout in seconds")
    retries: int = Field(default=0, description="Number of retries")

    # Networking
    tunnel_enabled: bool = Field(default=False, description="Enable tunnel to cluster")
    tunnel_port: int = Field(default=8000, description="Tunnel port")

    # Enhanced networking (Phase 2)
    replicas: int = Field(default=1, description="Number of replicas for distributed jobs")
    enable_i6pn: bool = Field(default=False, description="Enable IPv6 private networking")


class ModalJobStatus(BaseModel):
    """Status of a Modal job."""

    phase: str = Field(default="Pending", description="Job phase")
    modal_app_id: Optional[str] = Field(default=None, description="Modal app ID")
    modal_function_id: Optional[str] = Field(default=None, description="Modal function ID")

    # Networking
    tunnel_url: Optional[str] = Field(default=None, description="Tunnel URL if enabled")
    log_url: Optional[str] = Field(default=None, description="Modal app logs URL")

    # Timestamps
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    started_at: Optional[str] = Field(default=None, description="Start timestamp")
    finished_at: Optional[str] = Field(default=None, description="Finish timestamp")

    # Conditions
    conditions: List[Dict[str, Any]] = Field(default_factory=list, description="Status conditions")


class ModalFunctionSpec(BaseModel):
    """Specification for a Modal function."""

    image: str = Field(description="Container image for the function")
    handler: str = Field(description="Python handler function (e.g., 'app.process_image')")

    # Resources
    cpu: str = Field(default="1.0", description="CPU allocation")
    memory: str = Field(default="512Mi", description="Memory allocation")
    gpu: Optional[str] = Field(default=None, description="GPU specification (e.g., T4:1)")

    # Environment
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")

    # Function-specific
    timeout: int = Field(default=300, description="Function timeout in seconds")
    concurrency: int = Field(default=1, description="Max concurrent executions")


class ModalFunctionStatus(BaseModel):
    """Status of a Modal function."""

    phase: str = Field(default="Pending", description="Function phase")
    modal_app_id: Optional[str] = Field(default=None, description="Modal app ID")
    function_url: Optional[str] = Field(default=None, description="Function invocation URL")
    message: Optional[str] = Field(default=None, description="Status message")

    # Timestamps
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    deployed_at: Optional[str] = Field(default=None, description="Deployment timestamp")

    # Conditions
    conditions: List[Dict[str, Any]] = Field(default_factory=list, description="Status conditions")


class ModalEndpointSpec(BaseModel):
    """Specification for a Modal endpoint."""

    image: str = Field(description="Container image for endpoint")
    handler: str = Field(description="Handler function name")

    # Command execution for HTTP servers
    command: List[str] = Field(default_factory=list, description="Command to execute for HTTP server")
    args: List[str] = Field(default_factory=list, description="Arguments to command")

    # Resources
    cpu: str = Field(default="1.0", description="CPU allocation")
    memory: str = Field(default="512Mi", description="Memory allocation")
    gpu: Optional[str] = Field(default=None, description="GPU specification")

    # Scaling
    min_replicas: int = Field(default=0, description="Minimum replicas")
    max_replicas: int = Field(default=10, description="Maximum replicas")

    # Environment
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")


class ModalEndpointStatus(BaseModel):
    """Status of a Modal endpoint."""

    phase: str = Field(default="Pending", description="Endpoint phase")
    modal_app_id: Optional[str] = Field(default=None, description="Modal app ID")
    endpoint_url: Optional[str] = Field(default=None, description="Endpoint URL")

    # Replicas
    ready_replicas: int = Field(default=0, description="Ready replicas")

    # Conditions
    conditions: List[Dict[str, Any]] = Field(default_factory=list, description="Status conditions")


# CRD manifests for Kubernetes
MODAL_JOB_CRD = {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "modaljobs.modal-operator.io"},
    "spec": {
        "group": "modal-operator.io",
        "versions": [
            {
                "name": "v1alpha1",
                "served": True,
                "storage": True,
                "schema": {
                    "openAPIV3Schema": {
                        "type": "object",
                        "properties": {
                            "spec": {
                                "type": "object",
                                "properties": {
                                    "image": {"type": "string"},
                                    "command": {"type": "array", "items": {"type": "string"}},
                                    "args": {"type": "array", "items": {"type": "string"}},
                                    "cpu": {"type": "string"},
                                    "memory": {"type": "string"},
                                    "gpu": {"type": "string"},
                                    "env": {
                                        "type": "object",
                                        "x-kubernetes-preserve-unknown-fields": True,
                                        "additionalProperties": {"type": "string"},
                                    },
                                    "timeout": {"type": "integer"},
                                    "retries": {"type": "integer"},
                                    "tunnel_enabled": {"type": "boolean"},
                                    "tunnel_port": {"type": "integer"},
                                },
                                "required": ["image"],
                            },
                            "status": {
                                "type": "object",
                                "properties": {
                                    "phase": {"type": "string"},
                                    "modal_app_id": {"type": "string"},
                                    "modal_function_id": {"type": "string"},
                                    "tunnel_url": {"type": "string"},
                                    "log_url": {"type": "string"},
                                    "created_at": {"type": "string"},
                                    "started_at": {"type": "string"},
                                    "finished_at": {"type": "string"},
                                    "conditions": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "status": {"type": "string"},
                                                "lastTransitionTime": {"type": "string"},
                                                "reason": {"type": "string"},
                                                "message": {"type": "string"},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    }
                },
                "subresources": {"status": {}},
            }
        ],
        "scope": "Namespaced",
        "names": {"plural": "modaljobs", "singular": "modaljob", "kind": "ModalJob"},
    },
}

MODAL_ENDPOINT_CRD = {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "modalendpoints.modal-operator.io"},
    "spec": {
        "group": "modal-operator.io",
        "versions": [
            {
                "name": "v1alpha1",
                "served": True,
                "storage": True,
                "schema": {
                    "openAPIV3Schema": {
                        "type": "object",
                        "properties": {
                            "spec": {
                                "type": "object",
                                "properties": {
                                    "image": {"type": "string"},
                                    "handler": {"type": "string"},
                                    "command": {"type": "array", "items": {"type": "string"}},
                                    "args": {"type": "array", "items": {"type": "string"}},
                                    "cpu": {"type": "string"},
                                    "memory": {"type": "string"},
                                    "gpu": {"type": "string"},
                                    "min_replicas": {"type": "integer"},
                                    "max_replicas": {"type": "integer"},
                                    "env": {
                                        "type": "object",
                                        "x-kubernetes-preserve-unknown-fields": True,
                                        "additionalProperties": {"type": "string"},
                                    },
                                },
                                "required": ["image", "handler"],
                            },
                            "status": {
                                "type": "object",
                                "properties": {
                                    "phase": {"type": "string"},
                                    "modal_app_id": {"type": "string"},
                                    "endpoint_url": {"type": "string"},
                                    "ready_replicas": {"type": "integer"},
                                    "conditions": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "status": {"type": "string"},
                                                "lastTransitionTime": {"type": "string"},
                                                "reason": {"type": "string"},
                                                "message": {"type": "string"},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    }
                },
                "subresources": {"status": {}},
            }
        ],
        "scope": "Namespaced",
        "names": {"plural": "modalendpoints", "singular": "modalendpoint", "kind": "ModalEndpoint"},
    },
}

MODAL_FUNCTION_CRD = {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "modalfunctions.modal-operator.io"},
    "spec": {
        "group": "modal-operator.io",
        "versions": [
            {
                "name": "v1alpha1",
                "served": True,
                "storage": True,
                "schema": {
                    "openAPIV3Schema": {
                        "type": "object",
                        "properties": {
                            "spec": {
                                "type": "object",
                                "properties": {
                                    "image": {"type": "string"},
                                    "handler": {"type": "string"},
                                    "cpu": {"type": "string"},
                                    "memory": {"type": "string"},
                                    "gpu": {"type": "string"},
                                    "env": {
                                        "type": "object",
                                        "x-kubernetes-preserve-unknown-fields": True,
                                        "additionalProperties": {"type": "string"},
                                    },
                                    "timeout": {"type": "integer"},
                                    "concurrency": {"type": "integer"},
                                },
                                "required": ["image", "handler"],
                            },
                            "status": {
                                "type": "object",
                                "properties": {
                                    "phase": {"type": "string"},
                                    "modal_app_id": {"type": "string"},
                                    "function_url": {"type": "string"},
                                    "message": {"type": "string"},
                                    "created_at": {"type": "string"},
                                    "deployed_at": {"type": "string"},
                                    "conditions": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "status": {"type": "string"},
                                                "lastTransitionTime": {"type": "string"},
                                                "reason": {"type": "string"},
                                                "message": {"type": "string"},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    }
                },
                "subresources": {"status": {}},
            }
        ],
        "scope": "Namespaced",
        "names": {"plural": "modalfunctions", "singular": "modalfunction", "kind": "ModalFunction"},
    },
}
