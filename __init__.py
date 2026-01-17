from .llama_oneshot import LlamaOneShotNode

NODE_CLASS_MAPPINGS = {
    "LlamaOneShotNode": LlamaOneShotNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LlamaOneShotNode": "Llama.cpp One-Shot CLI"
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

print("LOADED: LlamaOneShotNode mappings registered.")