"""Modal Functions controller for serverless function management."""

import logging
from typing import Any, Dict
import json

import kopf
from kubernetes import client

logger = logging.getLogger(__name__)


@kopf.on.create("modal-operator.io", "v1alpha1", "modalfunctions")
async def create_modal_function(spec: Dict[str, Any], name: str, namespace: str, **kwargs):
    """Handle ModalFunction creation."""
    
    logger.info(f"Creating Modal function {name} in namespace {namespace}")
    
    try:
        # Create Modal function via modal_client (mock for now)
        result = {
            "status": "deployed",
            "app_id": f"func-{name}-{namespace}",
            "function_url": f"https://func-{name}-{namespace}.modal.run",
        }
        
        status = {
            "phase": "Deployed",
            "modal_app_id": result["app_id"],
            "function_url": result["function_url"],
            "message": "Function deployed successfully",
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Failed to create Modal function {name}: {e}")
        return {
            "phase": "Failed",
            "message": str(e)
        }


@kopf.on.delete("modal-operator.io", "v1alpha1", "modalfunctions")
async def delete_modal_function(spec: Dict[str, Any], name: str, namespace: str, **kwargs):
    """Handle ModalFunction deletion."""
    
    logger.info(f"Deleting Modal function {name} in namespace {namespace}")
    return {"message": "Function deleted"}


# Function calling service with authentication
class ModalFunctionService:
    """Service for calling Modal functions from local services."""
    
    def __init__(self):
        self.k8s_client = client.ApiClient()
    
    async def call_function(
        self, 
        namespace: str, 
        function_name: str, 
        payload: Dict[str, Any],
        auth_token: str = None
    ) -> Dict[str, Any]:
        """Call a Modal function with authentication."""
        
        try:
            # Get ModalFunction resource
            custom_api = client.CustomObjectsApi(self.k8s_client)
            function_resource = custom_api.get_namespaced_custom_object(
                group="modal-operator.io",
                version="v1alpha1", 
                namespace=namespace,
                plural="modalfunctions",
                name=function_name
            )
            
            status = function_resource.get("status", {})
            function_url = status.get("function_url")
            
            if not function_url:
                return {"error": "Function not deployed"}
            
            # Call function via modal operator proxy for security
            proxy_url = f"http://modal-operator-proxy.{namespace}.svc.cluster.local:8080"
            
            # Route through proxy to Modal function
            import aiohttp
            async with aiohttp.ClientSession() as session:
                headers = {}
                if auth_token:
                    headers["Authorization"] = f"Bearer {auth_token}"
                
                # Proxy request to Modal function
                async with session.post(
                    f"{proxy_url}/modal-function/{function_name}",
                    json=payload,
                    headers=headers
                ) as response:
                    result = await response.json()
                    return result
            
        except Exception as e:
            logger.error(f"Failed to call function {function_name}: {e}")
            return {"error": str(e)}
