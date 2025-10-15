"""Example: Immich service calling Modal functions for face recognition."""

import asyncio
from typing import Any, Dict

import aiohttp


class ImmichModalIntegration:
    """Immich service integration with Modal functions."""

    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self.proxy_url = f"http://modal-operator-proxy.{namespace}.svc.cluster.local:8080"

    async def recognize_faces(self, image_data: bytes, person_id: str = None) -> Dict[str, Any]:
        """Call Modal function for face recognition."""

        payload = {
            "image_data": image_data.hex(),  # Convert bytes to hex string
            "person_id": person_id,
            "model": "face_recognition",
            "threshold": 0.6
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.proxy_url}/modal-function/immich-face-recognition",
                json=payload
            ) as response:
                result = await response.json()

                if result.get("status") == "success":
                    return {
                        "faces": result["result"]["faces"],
                        "embeddings": result["result"]["embeddings"],
                        "processing_time": result["result"]["processing_time"]
                    }
                else:
                    raise Exception(f"Face recognition failed: {result.get('error')}")

    async def process_photo_upload(self, photo_path: str, user_id: str):
        """Process new photo upload with Modal ML."""

        # Read photo
        with open(photo_path, "rb") as f:
            image_data = f.read()

        try:
            # Call Modal function for face recognition
            faces = await self.recognize_faces(image_data)

            # Store results in Immich database
            await self.store_face_data(photo_path, faces, user_id)

            print(f"✅ Processed {len(faces['faces'])} faces in {photo_path}")

        except Exception as e:
            print(f"❌ Failed to process {photo_path}: {e}")

    async def store_face_data(self, photo_path: str, faces: Dict[str, Any], user_id: str):
        """Store face recognition results in Immich database."""
        # This would integrate with Immich's actual database
        print(f"Storing face data for {photo_path}: {len(faces['faces'])} faces detected")


# Example usage
async def main():
    immich = ImmichModalIntegration(namespace="immich")

    # Simulate photo upload processing
    await immich.process_photo_upload("/photos/family_photo.jpg", "user123")


if __name__ == "__main__":
    asyncio.run(main())
