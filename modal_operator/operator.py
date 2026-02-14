import base64
import time
from datetime import datetime, timezone
from typing import Optional

import kopf
import structlog
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from modal_operator.config import OperatorConfig
from modal_operator.crds import ModalAppSpec
from modal_operator.deployer import DeployResult, ModalDeployer
from modal_operator.health import mark_ready, start_health_server
from modal_operator.metrics import apps_active, apps_deployed, apps_failed, deploy_duration, start_metrics_server
from modal_operator.resources import ResourceManager

logger = structlog.get_logger(__name__)

operator_config: Optional[OperatorConfig] = None
deployer: Optional[ModalDeployer] = None
resource_manager: Optional[ResourceManager] = None


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    global operator_config, deployer, resource_manager

    settings.peering.standalone = True
    settings.posting.level = 20
    settings.watching.connect_timeout = 60
    settings.watching.server_timeout = 600

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    operator_config = OperatorConfig.from_env()
    deployer = ModalDeployer(operator_config.modal_token_id, operator_config.modal_token_secret)
    resource_manager = ResourceManager()

    start_health_server()
    start_metrics_server()
    mark_ready()
    logger.info("modal operator started")


@kopf.on.create("modal.internal.io", "v1alpha1", "modalapps")
async def create_modal_app(spec, name, namespace, meta, **kwargs):
    app_spec = ModalAppSpec(**spec)
    app_name = app_spec.appName or name
    log = logger.bind(app=app_name, namespace=namespace)

    env_vars = app_spec.env.copy()
    if app_spec.envFrom:
        env_vars.update(_read_env_from(app_spec.envFrom, namespace))

    start = time.monotonic()
    result: DeployResult = await deployer.deploy_app(app_name, app_spec.source, env_vars)
    deploy_duration.observe(time.monotonic() - start)

    if not result.success:
        apps_failed.labels(namespace=namespace).inc()
        _patch_status(name, namespace, {"phase": "Failed", "message": result.error})
        log.error("deploy failed", error=result.error)
        raise kopf.TemporaryError(f"Deploy failed: {result.error}", delay=30)

    apps_deployed.labels(namespace=namespace).inc()
    apps_active.inc()

    if result.url:
        owner_ref = _owner_ref(meta)
        try:
            resource_manager.create_external_service(
                name=name,
                namespace=namespace,
                modal_url=result.url,
                service_port=app_spec.servicePort,
                owner_ref=owner_ref,
            )
        except ApiException as e:
            if e.status == 409:
                resource_manager.update_external_service(name, namespace, result.url, app_spec.servicePort)
            else:
                raise

    status = {
        "phase": "Running",
        "url": result.url,
        "appId": result.app_id,
        "lastDeployed": datetime.now(timezone.utc).isoformat(),
        "message": f"Deployed. Access at {name}.{namespace}.svc.cluster.local",
    }
    _patch_status(name, namespace, status)
    log.info("deployed", url=result.url)
    return status


@kopf.on.resume("modal.internal.io", "v1alpha1", "modalapps")
async def resume_modal_app(spec, name, namespace, meta, **kwargs):
    app_spec = ModalAppSpec(**spec)
    app_name = app_spec.appName or name
    log = logger.bind(app=app_name, namespace=namespace)

    env_vars = app_spec.env.copy()
    if app_spec.envFrom:
        env_vars.update(_read_env_from(app_spec.envFrom, namespace))

    start = time.monotonic()
    result: DeployResult = await deployer.deploy_app(app_name, app_spec.source, env_vars)
    deploy_duration.observe(time.monotonic() - start)

    if not result.success:
        apps_failed.labels(namespace=namespace).inc()
        _patch_status(name, namespace, {"phase": "Failed", "message": result.error})
        log.error("resume deploy failed", error=result.error)
        raise kopf.TemporaryError(f"Deploy failed: {result.error}", delay=30)

    apps_deployed.labels(namespace=namespace).inc()
    apps_active.inc()

    if result.url:
        owner_ref = _owner_ref(meta)
        try:
            resource_manager.create_external_service(
                name=name,
                namespace=namespace,
                modal_url=result.url,
                service_port=app_spec.servicePort,
                owner_ref=owner_ref,
            )
        except ApiException as e:
            if e.status == 409:
                resource_manager.update_external_service(name, namespace, result.url, app_spec.servicePort)
            else:
                raise

    status = {
        "phase": "Running",
        "url": result.url,
        "appId": result.app_id,
        "lastDeployed": datetime.now(timezone.utc).isoformat(),
        "message": f"Resumed. Access at {name}.{namespace}.svc.cluster.local",
    }
    _patch_status(name, namespace, status)
    log.info("resumed", url=result.url)
    return status


@kopf.on.update("modal.internal.io", "v1alpha1", "modalapps")
async def update_modal_app(spec, name, namespace, meta, **kwargs):
    app_spec = ModalAppSpec(**spec)
    app_name = app_spec.appName or name
    log = logger.bind(app=app_name, namespace=namespace)

    env_vars = app_spec.env.copy()
    if app_spec.envFrom:
        env_vars.update(_read_env_from(app_spec.envFrom, namespace))

    start = time.monotonic()
    result: DeployResult = await deployer.deploy_app(app_name, app_spec.source, env_vars)
    deploy_duration.observe(time.monotonic() - start)

    if not result.success:
        apps_failed.labels(namespace=namespace).inc()
        _patch_status(name, namespace, {"phase": "Failed", "message": result.error})
        log.error("update deploy failed", error=result.error)
        raise kopf.TemporaryError(f"Deploy failed: {result.error}", delay=30)

    if result.url:
        resource_manager.update_external_service(name, namespace, result.url, app_spec.servicePort)

    status = {
        "phase": "Running",
        "url": result.url,
        "appId": result.app_id,
        "lastDeployed": datetime.now(timezone.utc).isoformat(),
        "message": f"Updated. Access at {name}.{namespace}.svc.cluster.local",
    }
    _patch_status(name, namespace, status)
    log.info("updated", url=result.url)
    return status


@kopf.on.delete("modal.internal.io", "v1alpha1", "modalapps")
async def delete_modal_app(spec, name, namespace, **kwargs):
    app_name = spec.get("appName", name)
    log = logger.bind(app=app_name, namespace=namespace)

    await deployer.stop_app(app_name)
    resource_manager.delete_service(name, namespace)
    apps_active.dec()

    log.info("deleted")


def _read_env_from(env_from_list, namespace):
    core_api = client.CoreV1Api()
    env_vars = {}

    for env_from in env_from_list:
        if env_from.secretRef:
            secret_name = env_from.secretRef["name"]
            secret = core_api.read_namespaced_secret(secret_name, namespace)
            if secret.data:
                for key, value in secret.data.items():
                    env_vars[key] = base64.b64decode(value).decode()

        if env_from.configMapRef:
            cm_name = env_from.configMapRef["name"]
            cm = core_api.read_namespaced_config_map(cm_name, namespace)
            if cm.data:
                env_vars.update(cm.data)

    return env_vars


def _owner_ref(meta):
    return client.V1OwnerReference(
        api_version="modal.internal.io/v1alpha1",
        kind="ModalApp",
        name=meta["name"],
        uid=meta["uid"],
        controller=True,
        block_owner_deletion=True,
    )


def _patch_status(name, namespace, status_body):
    api = client.CustomObjectsApi()
    api.patch_namespaced_custom_object_status(
        group="modal.internal.io",
        version="v1alpha1",
        namespace=namespace,
        plural="modalapps",
        name=name,
        body={"status": status_body},
    )
