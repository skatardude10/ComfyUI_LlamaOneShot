import urllib.request
import urllib.error
import json

print("LOADING: LlamaOneShotNode v4 (Raw)...")

class LlamaOneShotNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        # Your specific flags setup
        default_flags = (
            "-m /path/to/your/model.gguf "
            "-fa -c 16384 -ngl 99 -b 2048 -ub 1024 --no-mmap --threads 12 --threads-batch 12 "
            "-ctv q8_0 -ctk q8_0 -ot .(([1-9][0-9]).ffn_(down|up)_exps.weight|([1-9][0-9]).ffn_gate_exps.weight)=CPU "
            "-n 3000 --temp 0.8 --top-k 40 --top-p 1.0 --min-p 0.05 "
            "--xtc-threshold 0.05 --xtc-probability 0.5 "
            "--repeat-penalty 1.0 --repeat-last-n 0"
        )

        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "binary_path": ("STRING", {
                    "default": "/path/to/llama.cpp/build/bin/llama-cli"
                }),
                "flags": ("STRING", {
                    "default": default_flags,
                    "multiline": True
                }),
                "bridge_url": ("STRING", {"default": "http://127.0.0.1:5050"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("Output Text", "Debug Log")
    FUNCTION = "generate"
    CATEGORY = "LlamaOneShot"

    def generate(self, prompt, binary_path, flags, bridge_url):
        payload = {
            "binary_path": binary_path,
            "flags": flags,
            "prompt": prompt
        }

        data_json = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            bridge_url, 
            data=data_json, 
            headers={'Content-Type': 'application/json'}
        )

        try:
            with urllib.request.urlopen(req) as response:
                response_body = response.read().decode('utf-8')
                data = json.loads(response_body)
            
            if "error" in data:
                return (f"BRIDGE ERROR: {data['error']}", str(data))

            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            final_output = stdout if stdout else "No output generated (Check Debug Log)"
            debug_info = f"--- STDERR ---\n{stderr}\n\n--- STDOUT ---\n{stdout}"

            return (final_output, debug_info)

        except urllib.error.URLError as e:
            return (f"CONNECTION ERROR: Is llama_bridge.py running?\n{e}", str(e))
        except Exception as e:
            return (f"UNKNOWN ERROR:\n{e}", str(e))