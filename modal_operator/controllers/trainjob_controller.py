"""TrainJob controller for Kubeflow Trainer v2 integration."""

import logging
from typing import Any, Dict

import kopf

from modal_operator.controllers.modal_job_controller import ModalJobController
from modal_operator.crds import ModalJobSpec

logger = logging.getLogger(__name__)


@kopf.on.create("trainer.kubeflow.org", "v1alpha1", "trainjobs")
@kopf.on.update("trainer.kubeflow.org", "v1alpha1", "trainjobs")
async def handle_trainjob(spec: Dict[str, Any], name: str, namespace: str, **kwargs) -> Dict[str, Any]:
    """Handle TrainJob creation and updates by creating corresponding ModalJob."""

    # Extract runtime reference
    runtime_ref = spec.get("runtimeRef", {})
    runtime_name = runtime_ref.get("name")

    if not runtime_name:
        raise kopf.PermanentError("TrainJob must specify runtimeRef.name")

    # Check if this TrainJob should be handled by Modal
    if not _should_handle_trainjob(spec, runtime_name):
        logger.info(f"TrainJob {name} not configured for Modal, skipping")
        return {}

    # Create ModalJob from TrainJob spec
    modal_job_spec = _create_modal_job_spec(spec, name, namespace)

    # Delegate to ModalJobController
    controller = ModalJobController()
    job_name = f"trainjob-{name}"

    await controller.create_job(
        name=job_name,
        image=modal_job_spec.image,
        command=modal_job_spec.command,
        cpu=modal_job_spec.cpu,
        memory=modal_job_spec.memory,
        gpu=modal_job_spec.gpu,
        env=modal_job_spec.env,
        timeout=modal_job_spec.timeout,
        retries=modal_job_spec.retries,
        replicas=modal_job_spec.replicas,
        enable_i6pn=modal_job_spec.enable_i6pn,
    )

    return {"modalJobName": f"trainjob-{name}", "status": "Created"}


@kopf.on.delete("trainer.kubeflow.org", "v1alpha1", "trainjobs")
async def cleanup_trainjob(name: str, namespace: str, **kwargs):
    """Clean up Modal resources when TrainJob is deleted."""
    # TODO: Implement cleanup once ModalJobController has cancel/cleanup methods
    # controller = ModalJobController()
    # await controller.cancel_job(app_id, function_id)

    logger.info(f"TrainJob {name} deleted - Modal cleanup not yet implemented")


def _should_handle_trainjob(spec: Dict[str, Any], runtime_name: str) -> bool:
    """Check if TrainJob should be handled by Modal operator."""
    # Check for Modal-specific annotations or runtime names
    trainer_config = spec.get("trainer", {})

    # Look for Modal annotations or specific runtime patterns
    return (
        runtime_name.startswith("modal-")
        or trainer_config.get("env", [{}])[0].get("name") == "MODAL_ENABLED"
        or spec.get("annotations", {}).get("modal.com/enabled") == "true"
    )


def _create_modal_job_spec(trainjob_spec: Dict[str, Any], name: str, namespace: str) -> ModalJobSpec:
    """Convert TrainJob spec to ModalJob spec."""
    trainer = trainjob_spec.get("trainer", {})

    # Extract training configuration
    command = trainer.get("command", [])
    args = trainer.get("args", [])
    env = trainer.get("env", [])

    # Convert to Modal environment variables
    modal_env = {}
    for env_var in env:
        if "name" in env_var and "value" in env_var:
            modal_env[env_var["name"]] = env_var["value"]

    # Determine replicas for distributed training
    replicas = 1
    if "podSpecOverrides" in trainjob_spec:
        # Extract replica count from pod spec overrides
        for override in trainjob_spec["podSpecOverrides"]:
            target_jobs = override.get("targetJobs", [])
            if target_jobs:
                replicas = max(replicas, len(target_jobs))

    return ModalJobSpec(
        image="python:3.11-slim",  # Default, should be configurable
        command=command if command else ["python"],
        args=args,
        env=modal_env,
        replicas=replicas,
        enable_i6pn=replicas > 1,  # Enable networking for distributed jobs
        cpu="2.0",
        memory="4Gi",
        gpu="T4:1" if _requires_gpu(trainjob_spec) else None,
        timeout=3600,
    )


def _requires_gpu(trainjob_spec: Dict[str, Any]) -> bool:
    """Check if TrainJob requires GPU resources."""
    # Check pod spec overrides for GPU requests
    for override in trainjob_spec.get("podSpecOverrides", []):
        containers = override.get("containers", [])
        for container in containers:
            resources = container.get("resources", {})
            requests = resources.get("requests", {})
            if "nvidia.com/gpu" in requests:
                return True

    return False
