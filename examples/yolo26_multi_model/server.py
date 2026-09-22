# Copyright 2026 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Multi-model YOLO serving with dynamic model loading.

This example shows how to serve multiple YOLO model variants (e.g.
different fine-tunes for different object classes) from a single endpoint.
Models are loaded on demand and cached with SIEVE eviction.

Usage:
    # Start the server
    python server.py

    # Send a request (curl)
    curl -X POST http://127.0.0.1:8000/inference \\
         -H 'Content-Type: application/json' \\
         -d '{"model_id": "yolo26n", "image_url": "https://example.com/img.jpg"}'

    # Multiple model_ids in one batch are automatically sub-batched.
"""

from typing import Any, Dict, List

from mosec import MultiModelWorker, Server


class YOLOMultiModel(MultiModelWorker):
    """Serve multiple YOLO variants from a single worker with LRU caching."""

    # Keep up to 3 YOLO model variants in GPU memory at once.
    max_cache_size = 3

    def load_model(self, model_id: str) -> Any:
        """Load a YOLO model by its identifier.

        In production, model_id might map to a path like:
            models/yolo11n.pt, models/yolo11s-custom.pt, etc.
        """
        # Lazy import so the server module itself stays lightweight.
        from ultralytics import YOLO  # type: ignore[import-untyped]

        print(f"[YOLOMultiModel] Loading model: {model_id}")
        return YOLO(f"models/{model_id}.pt")

    def unload_model(self, model_id: str, model: Any) -> None:
        """Free GPU memory when a model is evicted."""
        print(f"[YOLOMultiModel] Evicting model: {model_id}")
        del model

    def forward_model(
        self, model_id: str, model: Any, data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Run detection on a sub-batch of images for one model variant."""
        image_urls = [item["image_url"] for item in data]
        results = model(image_urls)
        return [
            {
                "model_id": model_id,
                "detections": r.boxes.data.tolist() if r.boxes else [],
            }
            for r in results
        ]


if __name__ == "__main__":
    server = Server()
    server.append_worker(YOLOMultiModel, max_batch_size=16)
    server.run()
