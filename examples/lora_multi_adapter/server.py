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

from mosec import MultiModelWorker, Server


class LoRAWorker(MultiModelWorker):
    """Serve a base model with swappable LoRA adapters."""

    max_cache_size = 4  # keep up to 4 adapters loaded

    def __init__(self):
        super().__init__()
        # The base model is loaded once and never evicted.
        # Only adapters go through the SIEVE cache.
        self.base_model = None

    def load_model(self, model_id: str) -> Any:
        """Load a LoRA adapter and merge it with the base model.

        In production this would call something like:
            from peft import PeftModel
            adapter = PeftModel.from_pretrained(self.base_model, f"adapters/{model_id}")
        """
        # Lazy-load the base model on first call.
        if self.base_model is None:
            self._load_base_model()

        print(f"[LoRAWorker] Loading adapter: {model_id}")
        # Placeholder: return (base_ref, adapter_id) as the "model" object.
        # In a real implementation this would be the merged PEFT model.
        return {"base": self.base_model, "adapter_id": model_id}

    def _load_base_model(self):
        """Load the base model once (not cached, never evicted)."""
        print("[LoRAWorker] Loading base model (one-time)")
        # e.g. AutoModelForCausalLM.from_pretrained("meta-llama/...")
        self.base_model = "base_model_placeholder"

    def unload_model(self, model_id: str, model: Any) -> None:
        """Free the adapter weights."""
        print(f"[LoRAWorker] Evicting adapter: {model_id}")
        # e.g. del model; torch.cuda.empty_cache()

    def forward_model(
        self, model_id: str, model: Any, data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate text for a sub-batch using one adapter."""
        prompts = [item["prompt"] for item in data]
        # In production: outputs = model.generate(tokenizer(prompts))
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
