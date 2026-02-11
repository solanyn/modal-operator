from modal_operator.config import OperatorConfig
from modal_operator.crds import ModalAppSpec
from modal_operator.deployer import DeployResult


def test_operator_config_from_env(monkeypatch):
    monkeypatch.setenv("MODAL_TOKEN_ID", "test-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "test-secret")
    monkeypatch.setenv("WATCH_NAMESPACES", "ns1,ns2")

    config = OperatorConfig.from_env()
    assert config.modal_token_id == "test-id"
    assert config.modal_token_secret == "test-secret"
    assert config.watch_namespaces == ["ns1", "ns2"]


def test_operator_config_defaults(monkeypatch):
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("WATCH_NAMESPACES", raising=False)

    config = OperatorConfig.from_env()
    assert config.modal_token_id == ""
    assert config.watch_namespaces == []


def test_modal_app_spec_defaults():
    spec = ModalAppSpec(source="import modal")
    assert spec.appName is None
    assert spec.servicePort == 80
    assert spec.env == {}
    assert spec.envFrom == []


def test_modal_app_spec_full():
    spec = ModalAppSpec(
        source="import modal",
        appName="my-app",
        servicePort=8080,
        env={"KEY": "val"},
    )
    assert spec.appName == "my-app"
    assert spec.servicePort == 8080
    assert spec.env == {"KEY": "val"}


def test_deploy_result_success():
    r = DeployResult(success=True, url="https://test.modal.run", app_id="ap-123")
    assert r.success
    assert r.url == "https://test.modal.run"
    assert r.app_id == "ap-123"
    assert r.error is None


def test_deploy_result_failure():
    r = DeployResult(success=False, error="deploy failed")
    assert not r.success
    assert r.error == "deploy failed"
    assert r.url is None
