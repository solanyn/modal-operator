import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeployResult:
    success: bool
    url: Optional[str] = None
    app_id: Optional[str] = None
    error: Optional[str] = None


class ModalDeployer:
    def __init__(self, modal_token_id: str, modal_token_secret: str):
        self.modal_token_id = modal_token_id
        self.modal_token_secret = modal_token_secret

    async def deploy_app(
        self,
        name: str,
        source: str,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> DeployResult:
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", prefix=f"modal-{name}-", delete=False) as f:
                f.write(source)
                temp_file = f.name

            env = os.environ.copy()
            env["MODAL_TOKEN_ID"] = self.modal_token_id
            env["MODAL_TOKEN_SECRET"] = self.modal_token_secret
            if env_vars:
                env.update(env_vars)

            logger.info(f"Deploying Modal app {name}")
            result = subprocess.run(
                ["modal", "deploy", temp_file],
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                logger.error(f"modal deploy failed for {name}: {result.stderr}")
                return DeployResult(success=False, error=result.stderr)

            url, app_id = await self._query_deployment(name, env)

            logger.info(f"Deployed {name}: url={url} app_id={app_id}")
            return DeployResult(success=True, url=url, app_id=app_id)

        except subprocess.TimeoutExpired:
            return DeployResult(success=False, error="modal deploy timed out after 300s")
        except Exception as e:
            logger.error(f"Failed to deploy {name}: {e}")
            return DeployResult(success=False, error=str(e))
        finally:
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)

    async def _query_deployment(self, name: str, env: dict) -> tuple[Optional[str], Optional[str]]:
        url = None
        app_id = None
        try:
            from modal.experimental import list_deployed_apps

            deployed = await list_deployed_apps.aio()
            for app_info in deployed:
                if app_info.name == name:
                    url = getattr(app_info, "web_url", None)
                    app_id = getattr(app_info, "app_id", None)
                    break
        except Exception as e:
            logger.warning(f"Failed to query deployment info for {name}: {e}")

        if not url:
            workspace = env.get("MODAL_WORKSPACE") or self._get_workspace(env)
            if workspace:
                url = f"https://{workspace}--{name}-serve.modal.run"

        return url, app_id

    def _get_workspace(self, env: dict) -> Optional[str]:
        try:
            result = subprocess.run(
                ["modal", "profile", "current"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Failed to get workspace: {e}")
        return None

    async def stop_app(self, app_name: str) -> bool:
        try:
            env = os.environ.copy()
            env["MODAL_TOKEN_ID"] = self.modal_token_id
            env["MODAL_TOKEN_SECRET"] = self.modal_token_secret

            result = subprocess.run(
                ["modal", "app", "stop", app_name],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.info(f"Stopped Modal app {app_name}")
                return True

            logger.error(f"Failed to stop {app_name}: {result.stderr}")
            return False

        except Exception as e:
            logger.error(f"Failed to stop app {app_name}: {e}")
            return False
