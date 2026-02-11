import logging

from prometheus_client import Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger(__name__)

apps_deployed = Counter("modal_apps_deployed_total", "Total Modal apps deployed", ["namespace"])
apps_failed = Counter("modal_apps_failed_total", "Total Modal app deploy failures", ["namespace"])
apps_active = Gauge("modal_apps_active", "Currently active Modal apps")
deploy_duration = Histogram("modal_deploy_duration_seconds", "Modal deploy duration", buckets=[5, 10, 30, 60, 120, 300])


def start_metrics_server(port: int = 8081):
    try:
        start_http_server(port)
        logger.info(f"Metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
