#!/usr/bin/env python3
"""Generate Kubernetes CRDs from Pydantic models."""

from pathlib import Path

import yaml

from modal_operator.crds import ModalEndpointSpec, ModalEndpointStatus, ModalJobSpec, ModalJobStatus


def pydantic_to_openapi_schema(model_class):
    """Convert Pydantic model to OpenAPI schema for CRD."""
    schema = model_class.model_json_schema()

    # Convert Pydantic schema to Kubernetes CRD schema format
    def convert_schema(obj):
        if isinstance(obj, dict):
            # Remove Pydantic-specific fields
            obj.pop("title", None)
            obj.pop("$defs", None)

            # Handle anyOf with null types (convert to nullable)
            if "anyOf" in obj:
                any_of = obj.pop("anyOf")
                # Find non-null type
                non_null_types = [item for item in any_of if item.get("type") != "null"]
                null_types = [item for item in any_of if item.get("type") == "null"]

                if null_types and non_null_types:
                    # Use the first non-null type and mark as nullable
                    obj.update(non_null_types[0])
                    obj["nullable"] = True
                elif non_null_types:
                    # Use the first non-null type
                    obj.update(non_null_types[0])

            # Convert type arrays to single types
            if "type" in obj and isinstance(obj["type"], list):
                # Handle nullable types
                if "null" in obj["type"]:
                    obj["nullable"] = True
                    obj["type"] = [t for t in obj["type"] if t != "null"][0]
                else:
                    obj["type"] = obj["type"][0]

            # Recursively convert nested objects
            for key, value in obj.items():
                obj[key] = convert_schema(value)

        elif isinstance(obj, list):
            return [convert_schema(item) for item in obj]

        return obj

    return convert_schema(schema)


def generate_crd(name, group, version, kind, spec_model, status_model=None):
    """Generate a complete CRD definition."""
    crd = {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": f"{name}.{group}"},
        "spec": {
            "group": group,
            "versions": [
                {
                    "name": version,
                    "served": True,
                    "storage": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                            "properties": {
                                "apiVersion": {"type": "string"},
                                "kind": {"type": "string"},
                                "metadata": {"type": "object"},
                                "spec": pydantic_to_openapi_schema(spec_model),
                            },
                            "required": ["apiVersion", "kind", "metadata", "spec"],
                        }
                    },
                }
            ],
            "scope": "Namespaced",
            "names": {"plural": name, "singular": name[:-1] if name.endswith("s") else name, "kind": kind},
        },
    }

    # Add status schema if provided
    if status_model:
        crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["status"] = pydantic_to_openapi_schema(
            status_model
        )

        # Add status subresource
        crd["spec"]["versions"][0]["subresources"] = {"status": {}}

    return crd


def main():
    """Generate all CRDs."""
    output_dir = Path("charts/modal-vgpu-operator/crds")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate ModalJob CRD
    modaljob_crd = generate_crd(
        name="modaljobs",
        group="modal-operator.io",
        version="v1alpha1",
        kind="ModalJob",
        spec_model=ModalJobSpec,
        status_model=ModalJobStatus,
    )

    # Generate ModalEndpoint CRD
    modalendpoint_crd = generate_crd(
        name="modalendpoints",
        group="modal-operator.io",
        version="v1alpha1",
        kind="ModalEndpoint",
        spec_model=ModalEndpointSpec,
        status_model=ModalEndpointStatus,
    )

    # Write CRDs to files
    with open(output_dir / "modaljobs.yaml", "w") as f:
        yaml.dump(modaljob_crd, f, default_flow_style=False, sort_keys=False)

    with open(output_dir / "modalendpoints.yaml", "w") as f:
        yaml.dump(modalendpoint_crd, f, default_flow_style=False, sort_keys=False)

    print(f"Generated CRDs in {output_dir}")
    print("- modaljobs.yaml")
    print("- modalendpoints.yaml")


if __name__ == "__main__":
    main()
