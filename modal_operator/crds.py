from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EnvFromSource(BaseModel):
    secretRef: Optional[Dict[str, str]] = None
    configMapRef: Optional[Dict[str, str]] = None


class ModalAppSpec(BaseModel):
    source: str = Field(description="Inline Python source code")
    appName: Optional[str] = Field(default=None, description="Modal app name (defaults to metadata.name)")
    envFrom: List[EnvFromSource] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    servicePort: int = Field(default=80)


class ModalAppStatus(BaseModel):
    phase: str = Field(default="Pending")
    url: Optional[str] = None
    appId: Optional[str] = None
    lastDeployed: Optional[str] = None
    message: Optional[str] = None


MODAL_APP_CRD = {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "modalapps.modal.internal.io"},
    "spec": {
        "group": "modal.internal.io",
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
                                "required": ["source"],
                                "properties": {
                                    "source": {"type": "string"},
                                    "appName": {"type": "string"},
                                    "envFrom": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "secretRef": {
                                                    "type": "object",
                                                    "properties": {"name": {"type": "string"}},
                                                },
                                                "configMapRef": {
                                                    "type": "object",
                                                    "properties": {"name": {"type": "string"}},
                                                },
                                            },
                                        },
                                    },
                                    "env": {
                                        "type": "object",
                                        "x-kubernetes-preserve-unknown-fields": True,
                                        "additionalProperties": {"type": "string"},
                                    },
                                    "servicePort": {"type": "integer", "default": 80},
                                },
                            },
                            "status": {
                                "type": "object",
                                "properties": {
                                    "phase": {"type": "string"},
                                    "url": {"type": "string"},
                                    "appId": {"type": "string"},
                                    "lastDeployed": {"type": "string"},
                                    "message": {"type": "string"},
                                },
                            },
                        },
                    }
                },
                "subresources": {"status": {}},
                "additionalPrinterColumns": [
                    {"name": "Phase", "type": "string", "jsonPath": ".status.phase"},
                    {"name": "URL", "type": "string", "jsonPath": ".status.url"},
                    {"name": "Age", "type": "date", "jsonPath": ".metadata.creationTimestamp"},
                ],
            }
        ],
        "scope": "Namespaced",
        "names": {
            "plural": "modalapps",
            "singular": "modalapp",
            "kind": "ModalApp",
            "shortNames": ["ma"],
        },
    },
}
