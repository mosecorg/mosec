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

"""Multi-LoRA serving with dynamic adapter loading.

This example shows how to serve a base model with multiple LoRA adapters
swapped in and out on demand. The base model stays in memory permanently;
only the adapter weights are cached and evicted.

Usage:
    # Start the server
    python server.py

    # Send a request (curl)
    curl -X POST http://127.0.0.1:8000/inference \\
         -H 'Content-Type: application/json' \\
         -d '{"model_id": "lora-chat-v2", "prompt": "Hello, how are you?"}'
"""

from typing import Any, Dict, List

from mosec import MultiModelWorker, Server, get_logger

logger = get_logger()


class LoRAWorker(MultiModelWorker):
    """Serve a base model with swappable LoRA adapters."""

    max_cache_size = 4  # keep up to 4 adapters loaded

    def __init__(self):
        super().__init__()
        # The base model is loaded once and never evicted.
        # Only adapters go through the SIEVE cache.
        self.base_model = None

    def load_model(self, model_id: str) -> Any:
        """Load a LoRA adapter on top of the shared base model.

        In production this would call something like:
            self.base_model.load_adapter(f"adapters/{model_id}", adapter_name=model_id)
        """
        # Lazy-load the base model on first call.
        if self.base_model is None:
            self._load_base_model()

        logger.info("Loading adapter: %s", model_id)
        # The adapter weights live in the shared PEFT model, so the cached
        # "model" object only needs to identify the adapter.
        return {"base": self.base_model, "adapter_id": model_id}

    def _load_base_model(self):
        """Load the base model once (not cached, never evicted)."""
        logger.info("Loading base model (one-time)")
        # e.g. base = AutoModelForCausalLM.from_pretrained("meta-llama/...")
        #      self.base_model = PeftModel(base, LoraConfig(...))
        # Use one PEFT model for all adapters: calling `PeftModel.from_pretrained`
        # per adapter would inject LoRA layers into the same base model repeatedly.
        self.base_model = "base_model_placeholder"

    def unload_model(self, model_id: str, model: Any) -> None:
        """Free the adapter weights."""
        logger.info("Evicting adapter: %s", model_id)
        # e.g. self.base_model.delete_adapter(model_id)
        # Don't move `model` to "meta" here: it shares the base model weights.

    def forward_model(
        self, model_id: str, model: Any, data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate text for a sub-batch using one adapter."""
        prompts = [item["prompt"] for item in data]
        # In production:
        #   self.base_model.set_adapter(model_id)  # safe: sub-batches run one at a time
        #   outputs = self.base_model.generate(**tokenizer(prompts, return_tensors="pt"))
        return [
            {
                "model_id": model_id,
                "generated": f"[{model_id}] response to: {p}",
            }
            for p in prompts
        ]


if __name__ == "__main__":
    server = Server()
    server.append_worker(LoRAWorker, max_batch_size=8)
    server.run()
