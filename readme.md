# ComfyUI-Llama-OneShot

Run local `llama.cpp` binaries from ComfyUI. The node sends prompt + flags to a small local bridge, the bridge runs your binary once and returns the output.

This is not a model loader. It does not manage VRAM. Each run loads the model, generates, then exits and frees VRAM.

You need a working `llama.cpp` build (or `ik_llama.cpp`).

## Setup

1. Clone into `custom_nodes`, restart ComfyUI.
2. Run the bridge:
```bash
python llama_bridge.py
```
Listens on `http://127.0.0.1:5050`. Keep it running. Unix only (needs `pty`).

## Node fields

- **Prompt**: full prompt text (chat template applied by the binary with `--jinja`).
- **Binary Path**: absolute path, e.g. `/path/to/llama.cpp/build/bin/llama-completion`
- **Flags**: CLI args for the binary. Must include `-m /path/to/model.gguf`.
- **Bridge URL**: keep `http://127.0.0.1:5050`. Local only — remote URLs are rejected.
- **Timeout**: seconds, default 1200. Kills hung runs.

Returns: Final Text, Thinking, Raw Log. Raw is the full stdout for debug.

## Sane starting flags

Keep it minimal. Let `llama.cpp` pick context and offload unless you need to override:

```text
-m /path/to/model.gguf --jinja --no-display-prompt -no-cnv -st
```

Why these:

- `--jinja`: use the model's own chat template. Works across ChatML, Gemma, Llama without hard-coding.
- `--no-display-prompt`: don't echo the prompt into stdout. Keeps parsing clean.
- `-no-cnv`: no conversation loop. Run once and exit. Without this the binary stays interactive and holds VRAM.
- `-st`: single turn, then exit. Same reason — free VRAM for the next run.

Add your own on top:

```text
-m /path/to/model.gguf --jinja --no-display-prompt -no-cnv -st -c 32768 -ngl 99 --temp 0.8 --top-p 0.95 -n 2000 -s 1234 -r "<end_of_turn>,<turn|>"
```

Notes:

- `-c`, `-ngl`, `-ctk/-ctv`, `--n-cpu-moe`, `--split-mode` depend on your GPU and model. Omit them to use auto.
- `-r` takes one comma-separated value: `-r "<end_of_turn>,<turn|>"`. Multiple `-r` flags only keep the last.
- `-s` is seed. `-s -1` = random.
- MoE example: add `--n-cpu-moe 0 -ctk q8_0 -ctv q8_0 --split-mode none --main-gpu 0`.
- Dense example: `-c 32768 -ngl 99` is a common starting point if you have the VRAM.

## Security

The bridge runs binaries. It:

- only listens on `127.0.0.1`, checks `Host` and requires `Content-Type: application/json`,
- only allows filenames `llama-cli`, `llama-completion`, `llama-server`, `main`, `server`, and the file must exist and be executable,
- rejects `-p/--prompt/-f/--file` in flags (prompt is appended by the bridge),
- `llama-server` prints a warning — it stays resident and holds VRAM, prefer `llama-completion` for one-shot.

Run only on a machine you control. Don't point the node at a remote bridge URL.
