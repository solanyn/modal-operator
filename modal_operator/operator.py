"""Main operator implementation using Kopf framework."""
# Force rebuild - change 1

import asyncio
import json
import logging
import os
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

import kopf
from kubernetes import client, config

from modal_operator.controllers.modal_job_controller import ModalJobController
from modal_operator.controllers.networking_controller import NetworkingController
from modal_operator.controllers.status_sync import StatusSyncController
from modal_operator.controllers.webhook_controller import ModalWebhookController
from modal_operator.crds import ModalJobSpec
from modal_operator.metrics import metrics
from modal_operator.tunnel import TunnelManager

logger = logging.getLogger(__name__)

# Global instances
modal_controller: Optional[ModalJobController] = None
tunnel_manager: Optional[TunnelManager] = None
networking_controller: Optional[NetworkingController] = None
status_sync_controller: Optional[StatusSyncController] = None
mutating_webhook: Optional[ModalWebhookController] = None
webhook_task: Optional[asyncio.Task] = None


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Configure operator settings."""
    global modal_controller, networking_controller, status_sync_controller, mutating_webhook

    settings.posting.level = logging.INFO
    settings.watching.connect_timeout = 1 * 60
    settings.watching.server_timeout = 10 * 60

    # Initialize Kubernetes client
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration")
    except config.ConfigException:
        try:
            config.load_kube_config()
            logger.info("Loaded local Kubernetes configuration")
        except Exception as e:
            logger.error(f"Failed to load Kubernetes configuration: {e}")
            raise

    k8s_client = client.CoreV1Api()

    # Validate Kubernetes connectivity
    try:
        version = k8s_client.get_api_resources()
        logger.info("Kubernetes API connectivity validated")
    except Exception as e:
        logger.error(f"Failed to connect to Kubernetes API: {e}")
        raise

    # Initialize controllers
    mock_mode = os.getenv("MODAL_MOCK", "false").lower() == "true"
    logger.info(f"Initializing Modal operator (mock_mode={mock_mode})")

    try:
        modal_controller = ModalJobController(mock=mock_mode)
        networking_controller = NetworkingController(modal_controller)
        status_sync_controller = StatusSyncController(k8s_client)
        mutating_webhook = ModalWebhookController(k8s_client)
        logger.info("All controllers initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize controllers: {e}")
        raise

    # Start metrics server
    try:
        metrics.start_metrics_server(port=8081)
        metrics.record_operator_restart()
        logger.info("Metrics server started on port 8081")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
        # Don't fail startup if metrics fail

    logger.info(f"Modal vGPU Operator started successfully (mock_mode={mock_mode})")


# ModalJob CRD handlers
@kopf.on.create("modal-operator.io", "v1alpha1", "modaljobs")
async def create_modal_job(spec, name, namespace, logger, **kwargs):
    """Handle ModalJob creation."""
    start_time = datetime.utcnow()
    logger.info(f"Creating ModalJob {name} in namespace {namespace}")

    try:
        # Parse spec with validation
        try:
            job_spec = ModalJobSpec(**spec)
            logger.debug(
                f"Parsed ModalJob spec: image={job_spec.image}, cpu={job_spec.cpu}, "
                f"memory={job_spec.memory}, gpu={job_spec.gpu}"
            )
        except Exception as parse_error:
            logger.error(f"Failed to parse ModalJob spec for {name}: {parse_error}")
            raise ValueError(f"Invalid ModalJob specification: {parse_error}")

        # Create Modal job
        # Add tunnel info to env if enabled
        env_vars = job_spec.env or {}
        if job_spec.tunnel_enabled:
            env_vars["TUNNEL_ENABLED"] = "true"
            env_vars["TUNNEL_PORT"] = str(job_spec.tunnel_port)
            logger.debug(f"Tunnel enabled for ModalJob {name} on port {job_spec.tunnel_port}")

        logger.info(f"Creating Modal job for {name} with image {job_spec.image}")
        modal_result = await modal_controller.create_job(
            name=name,
            image=job_spec.image,
            command=job_spec.command,
            cpu=job_spec.cpu,
            memory=job_spec.memory,
            gpu=job_spec.gpu,
            env=env_vars,
            timeout=job_spec.timeout,
            retries=job_spec.retries,
            replicas=job_spec.replicas,
            enable_i6pn=job_spec.enable_i6pn,
        )

        creation_duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            f"Modal job created successfully for {name}: app_id={modal_result['app_id']}, "
            f"function_id={modal_result['function_id']}, duration={creation_duration:.2f}s"
        )

        # Record metrics
        gpu_type = job_spec.gpu.split(":")[0] if job_spec.gpu else None
        metrics.record_job_created(
            job_name=name, gpu_type=gpu_type, replicas=job_spec.replicas, enable_i6pn=job_spec.enable_i6pn
        )

        # Update status using direct patching
        try:
            custom_api = client.CustomObjectsApi()

            # Create log URL for easy access
            log_url = f"https://modal.com/apps/{modal_result['app_id']}"

            status_patch = {
                "status": {
                    "phase": "Running",
                    "modal_app_id": modal_result["app_id"],
                    "modal_function_id": modal_result["function_id"],
                    "tunnel_url": modal_result.get("tunnel_url"),
                    "log_url": log_url,
                    "created_at": datetime.utcnow().isoformat(),
                    "started_at": datetime.utcnow().isoformat(),
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "True",
                            "lastTransitionTime": datetime.utcnow().isoformat(),
                            "reason": "JobCreated",
                            "message": f"Modal job created successfully. View logs at {log_url}",
                        }
                    ],
                }
            }

            custom_api.patch_namespaced_custom_object_status(
                group="modal-operator.io",
                version="v1alpha1",
                namespace=namespace,
                plural="modaljobs",
                name=name,
                body=status_patch,
            )
            logger.info(f"Successfully updated status for ModalJob {name} to Running. Logs: {log_url}")

        except Exception as status_error:
            logger.error(f"Failed to update status for ModalJob {name}: {status_error}")
            # Don't fail the whole operation if status update fails
            metrics.record_error(error_type="status_update_failed", component="kubernetes_api")

        return None

    except Exception as e:
        logger.error(f"Failed to create ModalJob {name}: {e}", exc_info=True)

        # Record error metrics with more detail
        error_type = type(e).__name__
        metrics.record_error(error_type=f"job_creation_failed_{error_type.lower()}", component="modal_client")

        # Update status to Failed with detailed error info
        try:
            custom_api = client.CustomObjectsApi()
            status_patch = {
                "status": {
                    "phase": "Failed",
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "False",
                            "lastTransitionTime": datetime.utcnow().isoformat(),
                            "reason": f"CreationFailed_{error_type}",
                            "message": f"{error_type}: {str(e)[:200]}",
                        }
                    ],
                }
            }

            custom_api.patch_namespaced_custom_object_status(
                group="modal-operator.io",
                version="v1alpha1",
                namespace=namespace,
                plural="modaljobs",
                name=name,
                body=status_patch,
            )
            logger.info(f"Updated ModalJob {name} status to Failed")
        except Exception as status_error:
            logger.error(f"Failed to update error status for ModalJob {name}: {status_error}")

        return None


@kopf.on.delete("modal-operator.io", "v1alpha1", "modaljobs")
async def delete_modal_job(spec, name, namespace, status, logger, **kwargs):
    """Handle ModalJob deletion."""
    logger.info(f"Deleting ModalJob {name} in namespace {namespace}")

    try:
        # Cancel Modal job if it exists
        if status and status.get("modal_app_id"):
            await modal_controller.cancel_job(status["modal_app_id"], status.get("modal_function_id", ""))

        # Record job completion metrics
        if spec:
            gpu_type = spec.get("gpu", "").split(":")[0] if spec.get("gpu") else None
            metrics.record_job_completed(job_name=name, status="completed", gpu_type=gpu_type)

        logger.info(f"Successfully deleted ModalJob {name}")

    except Exception as e:
        logger.error(f"Failed to delete ModalJob {name}: {e}")


@kopf.on.update("modal-operator.io", "v1alpha1", "modaljobs")
async def update_modal_job(spec, name, namespace, status, logger, **kwargs):
    """Handle ModalJob updates."""
    logger.info(f"Updating ModalJob {name} in namespace {namespace}")

    # For now, just log the update
    # TODO: Implement job updates (e.g., scaling, configuration changes)


# ModalEndpoint CRD handlers
@kopf.on.create("modal-operator.io", "v1alpha1", "modalfunctions")
async def create_modal_function(spec, name, namespace, **kwargs):
    """Handle ModalFunction creation."""

    logger.info(f"Creating Modal function {name} in namespace {namespace}")

    try:
        result = await modal_controller.create_function(
            name=name,
            image=spec["image"],
            handler=spec["handler"],
            cpu=spec.get("cpu", "1.0"),
            memory=spec.get("memory", "512Mi"),
            gpu=spec.get("gpu"),
            env=spec.get("env", {}),
            timeout=spec.get("timeout", 300),
            concurrency=spec.get("concurrency", 1),
        )

        # Create Kubernetes Service for the ModalFunction
        if result["status"] == "deployed" and result.get("function_url"):
            try:
                from urllib.parse import urlparse

                parsed_url = urlparse(result["function_url"])
                external_hostname = parsed_url.netloc

                k8s_core = client.CoreV1Api()

                service = client.V1Service(
                    metadata=client.V1ObjectMeta(
                        name=name,
                        namespace=namespace,
                        labels={"modal-operator.io/function": name, "modal-operator.io/managed": "true"},
                        annotations={"modal-operator.io/function-url": result["function_url"]},
                    ),
                    spec=client.V1ServiceSpec(
                        type="ExternalName", external_name=external_hostname, ports=[client.V1ServicePort(port=443)]
                    ),
                )

                k8s_core.create_namespaced_service(namespace=namespace, body=service)
                logger.info(
                    f"Created Kubernetes Service {name} in namespace {namespace} pointing to {external_hostname}"
                )

            except Exception as svc_error:
                logger.warning(f"Failed to create Service for ModalFunction {name}: {svc_error}")
                # Don't fail the whole operation if service creation fails

        status = {
            "phase": "Deployed" if result["status"] == "deployed" else "Failed",
            "modal_app_id": result.get("app_id"),
            "function_url": result.get("function_url"),
            "message": result.get("error", "Function deployed successfully"),
        }

        return status

    except Exception as e:
        logger.error(f"Failed to create Modal function {name}: {e}")
        return {"phase": "Failed", "message": str(e)}


@kopf.on.delete("modal-operator.io", "v1alpha1", "modalfunctions")
async def delete_modal_function(spec, name, namespace, **kwargs):
    """Handle ModalFunction deletion."""

    logger.info(f"Deleting Modal function {name} in namespace {namespace}")

    # Delete associated Kubernetes Service
    try:
        k8s_core = client.CoreV1Api()
        k8s_core.delete_namespaced_service(name=name, namespace=namespace)
        logger.info(f"Deleted Kubernetes Service {name} in namespace {namespace}")
    except client.exceptions.ApiException as e:
        if e.status != 404:
            logger.warning(f"Failed to delete Service for ModalFunction {name}: {e}")
        # Service doesn't exist, which is fine
    except Exception as e:
        logger.warning(f"Error deleting Service for ModalFunction {name}: {e}")

    return {"message": "Function deleted"}


@kopf.on.create("modal-operator.io", "v1alpha1", "modalendpoints")
async def create_modal_endpoint(spec, name, namespace, logger, **kwargs):
    """Handle ModalEndpoint creation."""
    logger.info(f"Creating ModalEndpoint {name} in namespace {namespace}")

    try:
        # Create Modal endpoint
        endpoint_result = await modal_controller.create_endpoint(
            name=name,
            image=spec["image"],
            handler=spec["handler"],
            cpu=spec.get("cpu", "1.0"),
            memory=spec.get("memory", "512Mi"),
            gpu=spec.get("gpu"),
            env=spec.get("env", {}),
            command=spec.get("command"),
            args=spec.get("args"),
        )

        # Update status using direct patching (same as ModalJob)
        try:
            custom_api = client.CustomObjectsApi()

            status_patch = {
                "status": {
                    "phase": "Ready",
                    "modal_app_id": endpoint_result["app_id"],
                    "endpoint_url": endpoint_result["endpoint_url"],
                    "ready_replicas": 1,
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "True",
                            "lastTransitionTime": datetime.utcnow().isoformat(),
                            "reason": "EndpointReady",
                            "message": f"Modal endpoint is ready at {endpoint_result['endpoint_url']}",
                        }
                    ],
                }
            }

            custom_api.patch_namespaced_custom_object_status(
                group="modal-operator.io",
                version="v1alpha1",
                namespace=namespace,
                plural="modalendpoints",
                name=name,
                body=status_patch,
            )
            logger.info(f"Successfully updated status for ModalEndpoint {name} to Ready. URL: {endpoint_result['endpoint_url']}")

        except Exception as status_error:
            logger.error(f"Failed to update status for ModalEndpoint {name}: {status_error}")
            # Don't fail the whole operation if status update fails
            metrics.record_error(error_type="status_update_failed", component="kubernetes_api")

        return None

    except Exception as e:
        logger.error(f"Failed to create ModalEndpoint {name}: {e}", exc_info=True)

        # Record error metrics
        error_type = type(e).__name__
        metrics.record_error(error_type=f"endpoint_creation_failed_{error_type.lower()}", component="modal_client")

        # Update status to Failed with detailed error info
        try:
            custom_api = client.CustomObjectsApi()
            status_patch = {
                "status": {
                    "phase": "Failed",
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "False",
                            "lastTransitionTime": datetime.utcnow().isoformat(),
                            "reason": f"CreationFailed_{error_type}",
                            "message": f"{error_type}: {str(e)[:200]}",
                        }
                    ],
                }
            }

            custom_api.patch_namespaced_custom_object_status(
                group="modal-operator.io",
                version="v1alpha1",
                namespace=namespace,
                plural="modalendpoints",
                name=name,
                body=status_patch,
            )
            logger.info(f"Updated ModalEndpoint {name} status to Failed")

        except Exception as status_error:
            logger.error(f"Failed to update error status for ModalEndpoint {name}: {status_error}")

        return None


@kopf.on.delete("modal-operator.io", "v1alpha1", "modalendpoints")
async def delete_modal_endpoint(spec, name, namespace, status, logger, **kwargs):
    """Handle ModalEndpoint deletion - stop the deployed Modal app."""
    logger.info(f"Deleting ModalEndpoint {name} in namespace {namespace}")

    try:
        # Stop Modal app if it exists
        if status and status.get("modal_app_id"):
            app_id = status["modal_app_id"]
            logger.info(f"Stopping Modal app {app_id} for endpoint {name}")
            await modal_controller.delete_app(app_id)
            logger.info(f"Successfully stopped Modal app {app_id}")

        logger.info(f"Successfully deleted ModalEndpoint {name}")

    except Exception as e:
        logger.error(f"Failed to delete ModalEndpoint {name}: {e}")


# Pod interception (existing functionality)
@kopf.on.cleanup()
async def cleanup_handler(logger, **kwargs):
    """Handle operator shutdown gracefully."""
    logger.info("Modal operator shutting down...")

    try:
        # Record shutdown metrics
        metrics.record_operator_shutdown()
        logger.info("Shutdown metrics recorded")
    except Exception as e:
        logger.error(f"Failed to record shutdown metrics: {e}")

    logger.info("Modal operator shutdown complete")


@kopf.on.startup()
async def startup_handler(logger, **kwargs):
    """Startup handler to verify operator is loading correctly."""
    global webhook_task

    logger.info("Modal vGPU Operator handlers registered")

    # Start webhook server in background
    webhook_enabled = os.getenv("ENABLE_WEBHOOK", "true").lower() == "true"
    logger.info(f"Webhook enabled: {webhook_enabled}")
    if webhook_enabled:
        logger.info("Starting webhook server...")
        webhook_task = asyncio.create_task(start_webhook_server_async())


async def start_webhook_server_async():
    """Start the mutating admission webhook server asynchronously."""
    import ssl

    from aiohttp import web

    async def webhook_handler(request):
        """Handle mutating admission webhook requests."""
        try:
            body = await request.json()
            response = mutating_webhook.mutate_pod(body["request"])
            return web.json_response(response)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return web.json_response(
                {
                    "apiVersion": "admission.k8s.io/v1",
                    "kind": "AdmissionReview",
                    "response": {
                        "uid": body.get("request", {}).get("uid", ""),
                        "allowed": False,
                        "status": {"message": f"Webhook error: {e}"},
                    },
                },
                status=500,
            )

    try:
        logger.info("Creating webhook app...")
        app = web.Application()
        app.router.add_post("/mutate", webhook_handler)

        logger.info("Loading TLS certificates...")
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain("/etc/certs/tls.crt", "/etc/certs/tls.key")

        logger.info("Starting webhook server...")
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8443, ssl_context=ssl_context)
        await site.start()
        logger.info("Webhook server started on port 8443 with TLS")

        # Keep server running
        while True:
            await asyncio.sleep(60)

    except Exception as e:
        logger.error(f"Failed to start webhook server: {e}")
        import traceback

        logger.error(traceback.format_exc())


@kopf.on.create("", "v1", "pods")
async def pod_created(body, name, namespace, logger, **kwargs):
    """Handle pod creation - check for GPU requests and Modal annotations."""
    try:
        # Check if pod should be offloaded to Modal
        annotations = body.get("metadata", {}).get("annotations", {})
        containers = body.get("spec", {}).get("containers", [])

        # Skip pods that were already mutated by the webhook
        if annotations.get("modal-operator.io/mutated") == "true":
            return

        should_offload = (
            annotations.get("modal-operator.io/offload") == "true"
            or annotations.get("modal-operator.io/use-modal") == "true"
            or any(_has_gpu_request(container) for container in containers)
        )

        if not should_offload:
            return

        logger.info(f"Creating ModalJob for pod {name}")

        # Convert pod to ModalJob
        modal_job_spec = _pod_to_modal_job_spec(body, annotations)

        # Create ModalJob CRD
        custom_api = client.CustomObjectsApi()
        modal_job = {
            "apiVersion": "modal-operator.io/v1alpha1",
            "kind": "ModalJob",
            "metadata": {
                "name": f"{name}-modal",
                "namespace": namespace,
                "labels": {"modal-operator.io/original-pod": name},
            },
            "spec": modal_job_spec,
        }

        custom_api.create_namespaced_custom_object(
            group="modal-operator.io", version="v1alpha1", namespace=namespace, plural="modaljobs", body=modal_job
        )

        logger.info(f"Created ModalJob {name}-modal for pod {name}")

    except Exception as e:
        logger.error(f"Error processing pod {name}: {e}")


@kopf.on.create("", "v1", "pods", annotations={"modal-operator.io/mutated": "true"})
async def mutated_pod_created(body, name, namespace, logger, **kwargs):
    """Handle webhook-mutated pods - create corresponding ModalJob or ModalFunction."""
    try:
        annotations = body.get("metadata", {}).get("annotations", {})
        labels = body.get("metadata", {}).get("labels", {})

        # Determine workload type from label
        workload_type = labels.get("modal-operator.io/workload-type", "job")

        # Check if resource already exists
        custom_api = client.CustomObjectsApi()
        resource_name = f"{name}-modal"

        # Use ModalEndpoint for HTTP services, ModalJob for batch jobs
        if workload_type == "function":
            resource_kind = "ModalEndpoint"
            resource_plural = "modalendpoints"
        else:
            resource_kind = "ModalJob"
            resource_plural = "modaljobs"

        try:
            custom_api.get_namespaced_custom_object(
                group="modal-operator.io",
                version="v1alpha1",
                namespace=namespace,
                plural=resource_plural,
                name=resource_name
            )
            logger.info(f"{resource_kind} {resource_name} already exists, skipping creation")
            return
        except client.exceptions.ApiException as e:
            if e.status != 404:
                raise

        logger.info(f"Creating {resource_kind} for webhook-mutated pod {name}")

        # Convert pod to ModalJob using original container specs from environment variables
        original_images = json.loads(body.get("spec", {}).get("containers", [{}])[0].get("env", [{}])[2].get("value", "[]"))
        original_names = json.loads(body.get("spec", {}).get("containers", [{}])[0].get("env", [{}])[3].get("value", "[]"))
        original_commands = json.loads(body.get("spec", {}).get("containers", [{}])[0].get("env", [{}])[4].get("value", "[]"))
        original_args = json.loads(body.get("spec", {}).get("containers", [{}])[0].get("env", [{}])[5].get("value", "[]"))
        original_env = json.loads(body.get("spec", {}).get("containers", [{}])[0].get("env", [{}])[6].get("value", "{}"))

        # Build spec from original container specs
        spec = {
            "image": original_images[0] if original_images else "python:3.11-slim",
            "env": original_env,
            "cpu": annotations.get("modal-operator.io/cpu", "1.0"),
            "memory": annotations.get("modal-operator.io/memory", "1Gi"),
            "gpu": annotations.get("modal-operator.io/gpu"),
        }

        # Add workload-specific fields
        if workload_type == "function":
            # ModalEndpoint for HTTP services - wraps command in web endpoint
            spec["handler"] = "serve"
            # Store original command/args for execution
            if original_commands and original_commands[0]:
                spec["command"] = original_commands[0]
            if original_args and original_args[0]:
                spec["args"] = original_args[0]
        else:
            # ModalJob for batch processing
            spec["timeout"] = int(annotations.get("modal-operator.io/timeout", "600"))
            if original_commands and original_commands[0]:
                spec["command"] = original_commands[0]
            if original_args and original_args[0]:
                spec["args"] = original_args[0]

        # Remove None values
        spec = {k: v for k, v in spec.items() if v is not None}

        # Create resource CRD
        resource = {
            "apiVersion": "modal-operator.io/v1alpha1",
            "kind": resource_kind,
            "metadata": {
                "name": resource_name,
                "namespace": namespace,
                "labels": {"modal-operator.io/original-pod": name},
            },
            "spec": spec,
        }

        custom_api.create_namespaced_custom_object(
            group="modal-operator.io", version="v1alpha1", namespace=namespace, plural=resource_plural, body=resource
        )

        logger.info(f"Created {resource_kind} {resource_name} for webhook-mutated pod {name}")

    except Exception as e:
        logger.error(f"Error creating ModalJob for mutated pod {name}: {e}")
        logger.error(traceback.format_exc())
        raise


def _has_gpu_request(container: Dict[str, Any]) -> bool:
    """Check if container requests GPU resources."""
    resources = container.get("resources", {})
    requests = resources.get("requests", {})
    return "nvidia.com/gpu" in requests


def _pod_to_modal_job_spec(pod_spec: Dict[str, Any], annotations: Dict[str, str]) -> Dict[str, Any]:
    """Convert pod spec to ModalJob spec."""
    containers = pod_spec.get("spec", {}).get("containers", [])
    if not containers:
        raise ValueError("Pod has no containers")

    container = containers[0]  # Use first container

    # Extract configuration
    modal_spec = {
        "image": annotations.get("modal-operator.io/image", container.get("image", "python:3.11-slim")),
        "command": annotations.get("modal-operator.io/command", "").split() or container.get("command", []),
        "args": container.get("args", []),
        "cpu": annotations.get("modal-operator.io/cpu", "1.0"),
        "memory": annotations.get("modal-operator.io/memory", "512Mi"),
        "timeout": int(annotations.get("modal-operator.io/timeout", "300")),
        "retries": int(annotations.get("modal-operator.io/retries", "0")),
        "tunnel_enabled": annotations.get("modal-operator.io/tunnel", "false").lower() == "true",
        "tunnel_port": int(annotations.get("modal-operator.io/tunnel-port", "8000")),
        # Networking parameters
        "replicas": int(annotations.get("modal-operator.io/replicas", "1")),
        "enable_i6pn": annotations.get("modal-operator.io/enable-i6pn", "false").lower() == "true",
    }

    # Extract GPU configuration
    gpu = annotations.get("modal-operator.io/gpu")
    if not gpu:
        # Check container resources for GPU request
        resources = container.get("resources", {})
        requests = resources.get("requests", {})
        if "nvidia.com/gpu" in requests:
            gpu_count = requests["nvidia.com/gpu"]
            gpu_type = annotations.get("modal-operator.io/gpu-type", "T4")
            gpu = f"{gpu_type}:{gpu_count}"

    if gpu:
        modal_spec["gpu"] = gpu

    # Extract environment variables
    env = {}
    for key, value in annotations.items():
        if key.startswith("modal-operator.io/env-"):
            env_name = key[len("modal-operator.io/env-") :]
            env[env_name] = value

    # Add container env vars
    for env_var in container.get("env", []):
        env[env_var["name"]] = env_var.get("value", "")

    if env:
        modal_spec["env"] = env

    return modal_spec


@kopf.timer("", "v1", "pods", interval=30.0, annotations={"modal-operator.io/mutated": "true"})
async def sync_pod_status(name: str, namespace: str, annotations: Dict[str, str], **kwargs):
    """Periodically sync Modal job status to mutated pod status."""
    if not status_sync_controller:
        return

    try:
        # For webhook-mutated pods, sync Modal job status directly to the pod
        success = status_sync_controller.sync_mutated_pod_status(pod_name=name, namespace=namespace)

        if success:
            logger.debug(f"Status synced for mutated pod {name}")

    except Exception as e:
        logger.error(f"Failed to sync status for mutated pod {name}: {e}")


@kopf.on.update("", "v1", "pods", annotations={"modal-operator.io/mutated": "true"})
async def pod_updated(name: str, namespace: str, **kwargs):
    """Handle mutated pod updates and trigger immediate status sync."""
    if not status_sync_controller:
        return

    # Immediate status sync on pod updates
    try:
        status_sync_controller.sync_mutated_pod_status(pod_name=name, namespace=namespace)
        logger.debug(f"Immediate status sync completed for mutated pod {name}")
    except Exception as e:
        logger.debug(f"Status sync failed during pod update: {e}")


@kopf.on.probe(id="status")
def health_status(**kwargs):
    """Health probe handler for Kubernetes liveness checks."""
    try:
        # Check if critical components are initialized
        if not modal_controller:
            return {"status": "unhealthy", "reason": "modal_controller not initialized"}
        if not mutating_webhook:
            return {"status": "unhealthy", "reason": "webhook not initialized"}

        # Check Modal API connectivity (if not in mock mode)
        mock_mode = os.getenv("MODAL_MOCK", "false").lower() == "true"
        if not mock_mode:
            try:
                # Simple connectivity check - this will be fast
                import modal

                modal.is_local()  # Quick local check
            except Exception as e:
                return {"status": "degraded", "reason": f"modal_api_issue: {str(e)[:100]}"}

        return {
            "status": "healthy",
            "mock_mode": mock_mode,
            "components": {
                "modal_controller": "ready",
                "webhook": "ready",
                "status_sync": "ready" if status_sync_controller else "not_initialized",
            },
        }
    except Exception as e:
        return {"status": "unhealthy", "reason": f"health_check_failed: {str(e)[:100]}"}


async def main():
    """Main entry point for the operator."""
    # Run the operator with built-in health endpoints
    await kopf.operator(clusterwide=True, liveness_endpoint="http://0.0.0.0:8080/healthz")


if __name__ == "__main__":
    asyncio.run(main())
