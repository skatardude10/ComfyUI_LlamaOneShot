import urllib.request
import urllib.error
import json
import tempfile
import numpy as np
import re
import os
from PIL import Image

print("LOADING: LlamaOneShotNode v15 (Prompt Echo Stripper + Universal Log Cleanup)...")

class LlamaOneShotNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "binary_path": ("STRING", {"default": "/path/to/llama-cli"}),
                "flags": ("STRING", {"default": "-m /path/to/model.gguf -c 32768 -ngl 99 -st --simple-io", "multiline": True}),
                "bridge_url": ("STRING", {"default": "http://127.0.0.1:5050"}),
            },
            "optional": {
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
                "image_3": ("IMAGE",),
                "image_4": ("IMAGE",),
                "image_5": ("IMAGE",),
                "image_6": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("Final Text", "Thinking", "Raw Log")
    FUNCTION = "generate"
    CATEGORY = "LlamaOneShot"

    def generate(self, prompt, binary_path, flags, bridge_url, **kwargs):
        image_paths =[]
        
        for i in range(1, 7):
            img_key = f"image_{i}"
            if img_key in kwargs and kwargs[img_key] is not None:
                img_batch = kwargs[img_key]
                for i_batch in range(img_batch.shape[0]):
                    img_tensor = 255. * img_batch[i_batch].cpu().numpy()
                    img = Image.fromarray(np.clip(img_tensor, 0, 255).astype(np.uint8))
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png", mode='wb') as f:
                        img.save(f)
                        image_paths.append(f.name)
        
        payload = {
            "binary_path": binary_path,
            "flags": flags,
            "prompt": prompt,
            "image_paths": image_paths, 
            "image_path": image_paths[0] if len(image_paths) > 0 else "" 
        }

        data_json = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(bridge_url, data=data_json, headers={'Content-Type': 'application/json'})

        try:
            with urllib.request.urlopen(req) as response:
                response_body = response.read().decode('utf-8')
                data = json.loads(response_body)
            
            if "error" in data:
                return (f"BRIDGE ERROR: {data['error']}", "", str(data))

            raw_output = data.get("stdout", "")
            final_text, thinking_text = self.parse_v15(raw_output)

            return (final_text, thinking_text, raw_output)

        except Exception as e:
            return (f"NODE ERROR: {e}", "", str(e))

    def parse_v15(self, raw_text):
        # 1. Clean ANSI and ASCII Blobs
        text = re.sub(r'\x1b\[[0-9;]*m', '', raw_text)
        text = re.sub(r'[\u2580-\u259F]', '', text)

        # 2. Filter Engine Logs (Line by Line)
        lines = text.split('\n')
        cleaned_lines = []
        
        log_patterns =[
            r'^ggml_', r'^llama_', r'^Device \d', r'^Loading model', 
            r'^build\s+:', r'^model\s+:', r'^modalities\s+:', 
            r'^available commands:', r'^\s*/\w+',  # Catches all CLI interactive help commands (/glob, /help, etc)
            r'^Loaded media', r'^Exiting', 
            r'^common_perf', r'^sampler', r'^system_info', r'^main:',
            r'^generate: n_ctx', r'^print_info:', r'^load:', r'^sched_reserve:',
            r'^load_tensors:', r'^common_init', r'^llama_memory', 
            r'^common_memory_breakdown_print:',
            r'^\.+', r'^\s*(repeat_last_n|dry_multiplier|top_k|mirostat)'
        ]
        
        for line in lines:
            stripped = line.strip()
            if any(re.match(p, line) or re.match(p, stripped) for p in log_patterns):
                continue
            if stripped.startswith("> "):
                continue
            if re.match(r'\[ Prompt: .* \| Generation: .* \]', stripped):
                continue
            cleaned_lines.append(line)

        text = "\n".join(cleaned_lines)

        # 3. PROMPT ECHO STRIPPER (Isolates Generation from CLI Echo)
        # If llama-cli truncated the prompt display, split there and take everything after.
        if "... (truncated)" in text:
            text = text.split("... (truncated)")[-1]
        else:
            # If it wasn't truncated, find the AI's role tag and slice everything before it off.
            role_markers =[
                r"<start_of_turn>model",   # Gemma
                r"<\|im_start\|>assistant" # ChatML / Qwen
            ]
            for rm in role_markers:
                matches = list(re.finditer(rm, text, re.IGNORECASE))
                if matches:
                    last_match = matches[-1]
                    text = text[last_match.end():]
                    break

        # 4. Split Thinking vs Response
        thinking = ""
        response = text

        split_markers =[
            (r'<channel\|>', r'<\|channel>(?:thought)?'), # Gemma 4
            (r'</think>', r'<think>'),                     # DeepSeek / Standard
            (r'\[End thinking\]', r'\[Start thinking\]'),  # Legacy 1
            (r'\[/Thinking\]', r'\[Thinking\]')            # Legacy 2
        ]

        for end_marker, start_marker in split_markers:
            end_matches = list(re.finditer(end_marker, text, re.IGNORECASE | re.DOTALL))
            if end_matches:
                last_end = end_matches[-1]
                response = text[last_end.end():].strip()
                
                pre_text = text[:last_end.start()]
                start_matches = list(re.finditer(start_marker, pre_text, re.IGNORECASE | re.DOTALL))
                if start_matches:
                    thinking = pre_text[start_matches[0].end():].strip()
                else:
                    thinking = pre_text.strip()
                
                response = re.sub(end_marker, '', response, flags=re.IGNORECASE).strip()
                thinking = re.sub(start_marker, '', thinking, flags=re.IGNORECASE).strip()
                break

        # 5. Final Formatting & Structural Tag Scrubbing
        def scrub_final(t):
            t = re.sub(r"'/tmp/tmp\w+\.png'", '', t)
            t = re.sub(r"/tmp/tmp\w+\.png", '', t)
            t = re.sub(r'<(start_of_turn|end_of_turn|turn\|)>', '', t, flags=re.IGNORECASE)
            t = re.sub(r'<\|.*?\|>', '', t)
            t = re.sub(r'<.*?_of_box>', '', t)
            t = re.sub(r'\[end of text\]', '', t, flags=re.IGNORECASE)
            t = re.sub(r'\n{3,}', '\n\n', t)
            return t.strip()

        response = scrub_final(response)
        thinking = scrub_final(thinking)

        return response, thinking
