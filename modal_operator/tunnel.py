"""Modal tunnel integration for cluster connectivity."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class TunnelManager:
    """Manages Modal tunnels for cluster connectivity."""

    def __init__(self, mock: bool = False):
        self.mock = mock
        self._active_tunnels: Dict[str, Dict[str, Any]] = {}

    def create_tunnel_config(self, job_name: str, port: int = 8000) -> Dict[str, Any]:
        """Create tunnel configuration for Modal job."""

        if self.mock:
            tunnel_url = f"https://mock-{job_name}-tunnel.modal.run"
            return {
                "enabled": True,
                "port": port,
                "url": tunnel_url,
                "tls_socket": (f"mock-{job_name}-tunnel.modal.run", 443),
            }

        # Real tunnel configuration
        return {
            "enabled": True,
            "port": port,
            "url": None,  # Will be set when tunnel is created
            "tls_socket": None,
        }

    def get_tunnel_code(self, port: int = 8000) -> str:
        """Generate Modal tunnel code for injection into jobs."""

        return f"""
import modal

# Create tunnel for cluster connectivity
with modal.forward({port}) as tunnel:
    print(f"🔗 Tunnel URL: {{tunnel.url}}")
    print(f"🔗 TLS Socket: {{tunnel.tls_socket}}")

    # Store tunnel info for Mirror Pod access
    tunnel_info = {{
        "url": tunnel.url,
        "tls_socket": tunnel.tls_socket,
        "port": {port}
    }}

    # Your job code here - tunnel stays active during execution
"""

    def create_cluster_access_config(self) -> Dict[str, Any]:
        """Create configuration for accessing cluster services from Modal."""

        return {
            "minio": {
                "description": "Access MinIO object storage in cluster",
                "example_url": "http://minio.default.svc.cluster.local:9000",
            },
            "postgres": {
                "description": "Access PostgreSQL database in cluster",
                "example_url": "postgresql://postgres.default.svc.cluster.local:5432",
            },
            "redis": {
                "description": "Access Redis cache in cluster",
                "example_url": "redis://redis.default.svc.cluster.local:6379",
            },
            "kubeflow": {
                "description": "Access Kubeflow services",
                "example_url": "http://kubeflow.kubeflow.svc.cluster.local",
            },
        }

    def generate_tunnel_service_yaml(self, job_name: str, tunnel_url: str, port: int = 8000) -> str:
        """Generate Kubernetes Service YAML for tunnel access."""

        return f"""
apiVersion: v1
kind: Service
metadata:
  name: {job_name}-tunnel
  labels:
    modal-operator.io/type: tunnel-service
    modal-operator.io/job: {job_name}
spec:
  type: ExternalName
  externalName: {tunnel_url.replace("https://", "").replace("http://", "")}
  ports:
  - port: {port}
    targetPort: 443
    protocol: TCP
---
apiVersion: v1
kind: Endpoints
metadata:
  name: {job_name}-tunnel
subsets:
- addresses:
  - ip: {tunnel_url.replace("https://", "").replace("http://", "")}
  ports:
  - port: 443
    protocol: TCP
"""
