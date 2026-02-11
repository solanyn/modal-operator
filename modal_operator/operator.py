import base64
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import kopf
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from modal_operator.config import OperatorConfig
from modal_operator.crds import ModalAppSpec
from modal_operator.deployer import DeployResult, ModalDeployer
from modal_operator.metrics import apps_active, apps_deployed, apps_failed, deploy_duration, start_metrics_server
from modal_operator.resources import ResourceManager

logger = logging.getLogger(__name__)

operator_config: Optional[OperatorConfig] = None
deployer: Optional[ModalDeployer] = None
resource_manager: Optional[ResourceManager] = None


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    global operator_config, deployer, resource_manager

    settings.posting.level = logging.INFO
    settings.watching.connect_timeout = 60
    settings.watching.server_timeout = 600

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    operator_config = OperatorConfig.from_env()
    deployer = ModalDeployer(operator_config.modal_token_id, operator_config.modal_token_secret)
    resource_manager = ResourceManager()

    start_metrics_server()
    logger.info("Modal operator started")


@kopf.on.create("modal.internal.io", "v1alpha1", "modalapps")
async def create_modal_app(spec, name, namespace, meta, logger, **kwargs):
    app_spec = ModalAppSpec(**spec)
    app_name = app_spec.appName or name

    env_vars = app_spec.env.copy()
    if app_spec.envFrom:
        env_vars.update(_read_env_from(app_spec.envFrom, namespace))

    start = time.monotonic()
    result: DeployResult = await deployer.deploy_app(app_name, app_spec.source, env_vars)
    deploy_duration.observe(time.monotonic() - start)

    if not result.success:
        apps_failed.labels(namespace=namespace).inc()
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

    return {
        "phase": "Running",
        "url": result.url,
        "appId": result.app_id,
        "lastDeployed": datetime.now(timezone.utc).isoformat(),
        "message": f"Deployed. Access at {name}.{namespace}.svc.cluster.local",
    }


@kopf.on.update("modal.internal.io", "v1alpha1", "modalapps")
async def update_modal_app(spec, name, namespace, meta, logger, **kwargs):
    app_spec = ModalAppSpec(**spec)
    app_name = app_spec.appName or name

    env_vars = app_spec.env.copy()
    if app_spec.envFrom:
        env_vars.update(_read_env_from(app_spec.envFrom, namespace))

    start = time.monotonic()
    result: DeployResult = await deployer.deploy_app(app_name, app_spec.source, env_vars)
    deploy_duration.observe(time.monotonic() - start)

    if not result.success:
        apps_failed.labels(namespace=namespace).inc()
        raise kopf.TemporaryError(f"Deploy failed: {result.error}", delay=30)

    if result.url:
        resource_manager.update_external_service(name, namespace, result.url, app_spec.servicePort)

    return {
        "phase": "Running",
        "url": result.url,
        "appId": result.app_id,
        "lastDeployed": datetime.now(timezone.utc).isoformat(),
        "message": f"Updated. Access at {name}.{namespace}.svc.cluster.local",
    }


@kopf.on.delete("modal.internal.io", "v1alpha1", "modalapps")
async def delete_modal_app(spec, name, namespace, logger, **kwargs):
    app_name = spec.get("appName", name)

    await deployer.stop_app(app_name)
    resource_manager.delete_service(name, namespace)
    apps_active.dec()

    logger.info(f"Deleted ModalApp {name}")


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
