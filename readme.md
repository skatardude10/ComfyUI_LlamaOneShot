# ComfyUI-Llama-OneShot

A raw, flexible wrapper node for running local `llama.cpp` binaries directly within ComfyUI.

This is not a model loader. It does not load weights into ComfyUI's VRAM management. It a node that connects to the included bridge that executes your local `llama-cli` or `llama-completion` binary, passes the prompt and flags, and returns the stdout string.

Useful if you want full control over `llama.cpp` flags (layer offloading, context shifting, specific samplers) or if you are running experimental builds/models (like GLM-4.whatever) that aren't fully supported by standard or stupid ollama or one of the many llama nodes yet.

## Prerequisites

1.  **llama.cpp**: You must have a working, compiled version of [llama.cpp](https://github.com/ggerganov/llama.cpp) or something like ik_llama.cpp.
2.  **Python**: Standard ComfyUI environment.

## Installation

1.  Clone this repo into your `custom_nodes` folder:
    ```bash
    git clone https://github.com/skatardude10/ComfyUI-Llama-OneShot.git
    ```
2.  Restart ComfyUI.

## Usage (Step-by-Step)

This node requires a "Bridge" script to run in the background. This avoids ComfyUI blocking and handles the system calls to your binary.

### 1. Start the Bridge
Open a terminal inside this node's folder and run:
```bash
python llama_bridge.py
```
*   This starts a local server on port `5050`.
*   It listens **only** on `127.0.0.1` for security.
*   **Keep this terminal open** while using the node.

### 2. Configure the Node
Add the **Llama.cpp One-Shot CLI** node to your workflow.

*   **Prompt**: The text to send to the model.
*   **Binary Path**: The absolute path to your executable.
    *   *Example:* `/home/user/llama.cpp/build/bin/llama-cli`
    *   *Example:* `C:\AI\llama.cpp\build\bin\llama-completion.exe`
*   **Flags**: The exact command line arguments you would use in a terminal to the binary.
    *   **Must include** `-m /path/to/model.gguf`
*   **Bridge URL**: Leave as `http://127.0.0.1:5050` unless you changed the port in the python script.

## Examples

### Chat / Instruct (llama-cli)
**Binary:** `/path/to/llama-cli`

**Flags:**
```text
-m /models/Llama-3-8B-Instruct.gguf -c 8192 -ngl 99 --temp 0.7 --top-k 40 --top-p 0.9 --no-display-prompt -cnv -p "You are a helpful assistant."
```

### Raw Completion / GLM-4 (llama-completion)
**Binary:** `/path/to/llama-completion`

**Flags:**
```text
-m /models/GLM-4-9B.gguf -c 32768 -ngl 99 --temp 0.8 --min-p 0.05 --repeat-penalty 1.0 --no-display-prompt -no-cnv -mli -sp -r "<|user|>" -r "<|end_of_text|>"
```

### Advanced Split Offloading
You can use complex regex for CPU/GPU splitting just like in the CLI:
```text
-m /models/Heavy-Model-Q2_K.gguf -ngl 99 -ctv q8_0 -ctk q8_0 -ot .((1[8-9]|[2-9][0-9]).ffn_(down|up)_exps.weight)=CPU --xtc-threshold 0.1 --xtc-probability 0.4
```

## Security Note

The `llama_bridge.py` script executes shell commands.
1.  It includes a whitelist allowing only specific binaries (`llama-cli`, `llama-completion`, `main`, `server`).
2.  It restricts access to `localhost`.

However, as with any tool that executes binaries, run this only on a machine you control.