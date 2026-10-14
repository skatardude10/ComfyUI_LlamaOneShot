import http.server
import socketserver
import json
import subprocess
import shlex
import os
import select
import time

try:
    import pty
except ImportError:
    pty = None

# CONFIGURATION
PORT = 5050
HOST = "127.0.0.1"
MAX_BODY = 10 * 1024 * 1024
BRIDGE_TIMEOUT = 1200

class LlamaRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        # --- LOCALHOST ONLY ---
        if self.client_address[0] != "127.0.0.1":
            self.send_error(403, "Access Denied: Localhost only.")
            return

        # --- HOST CHECK (blocks DNS rebinding) ---
        host = self.headers.get('Host', '')
        if host not in (f"{HOST}:{PORT}", f"localhost:{PORT}"):
            self.send_error(403, "Bad Host.")
            return

        # --- CONTENT-TYPE CHECK (forces browser preflight) ---
        ctype = self.headers.get('Content-Type', '').split(";")[0].strip().lower()
        if ctype != "application/json":
            self.send_error(403, "Content-Type must be application/json.")
            return

        if pty is None:
            self.send_error(500, "Bridge requires Unix pty (not available on Windows).")
            return

        try:
            raw_len = self.headers.get('Content-Length')
            if raw_len is None:
                self.send_error(400, "Missing Content-Length.")
                return
            content_length = int(raw_len)
            if content_length <= 0 or content_length > MAX_BODY:
                self.send_error(413, "Body too large.")
                return
            post_data = self.rfile.read(content_length)
        except Exception as e:
            self.send_error(400, f"Bad request: {e}")
            return

        try:
            data = json.loads(post_data.decode('utf-8'))
            binary_path = data.get('binary_path', '')

            # --- BINARY ALLOWLIST (filename + executable check) ---
            if not binary_path:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Bad Request: Binary path is missing."}).encode('utf-8'))
                return

            base_name = os.path.basename(binary_path).lower()
            if base_name.endswith('.exe'):
                base_name = base_name[:-4]

            allowed_bins = ["llama-cli", "llama-completion", "llama-server", "main", "server"]
            if base_name not in allowed_bins:
                error_msg = f"Security Alert: '{os.path.basename(binary_path)}' is not an allowed executable."
                print(f"BLOCKED: {error_msg}")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": error_msg}).encode('utf-8'))
                return

            real = os.path.realpath(binary_path)
            if not (os.path.isfile(real) and os.access(real, os.X_OK)):
                error_msg = f"Binary not found or not executable: '{binary_path}'."
                print(f"BLOCKED: {error_msg}")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": error_msg}).encode('utf-8'))
                return

            if base_name in ("llama-server", "server"):
                print("WARNING: llama-server holds VRAM and does not exit. Prefer llama-completion for one-shot use.")

            try:
                req_timeout = int(data.get('timeout', BRIDGE_TIMEOUT))
            except Exception:
                req_timeout = BRIDGE_TIMEOUT
            req_timeout = max(30, min(req_timeout, 7200))

            flags_str = data.get('flags', '')
            prompt = data.get('prompt', '')

            # Block flags that would conflict with bridge-appended prompt
            try:
                args = shlex.split(flags_str)
            except Exception as e:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Bad flags: {e}"}).encode('utf-8'))
                return
            blocked = {"-p", "--prompt", "-f", "--file", "--system-prompt-file"}
            if any(a in blocked for a in args):
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Flags must not contain -p/--prompt/-f/--file; prompt is appended by the bridge."}).encode('utf-8'))
                return
            
            # Fetch multiple image paths (new node behavior)
            image_paths = data.get('image_paths', [])
            
            # Fallback for backwards compatibility with older versions of the node
            if not image_paths and data.get('image_path'):
                image_paths = [data.get('image_path')]

            # 1. Build Command (args already split above)
            command = [real] + args

            # Append each valid image path as a separate --image flag
            for path in image_paths:
                if path and path.strip() and os.path.isfile(path) and os.path.exists(path):
                    command.extend(["--image", path])
                elif path and path.strip():
                    print(f"SKIP image (not a file): {path}")

            command.extend(["-p", prompt])

            print(f"\nEXECUTING (PTY Mode):\n{shlex.join(command)}\n")

            # 2. CREATE FAKE TERMINAL
            master_fd, slave_fd = pty.openpty()

            # 3. RUN
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=slave_fd,
                stderr=slave_fd,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            # Close slave in parent so we get EOF when process dies
            os.close(slave_fd)
            slave_fd = -1

            # 4. READ LOOP with deadline (uses node-supplied timeout, clamped)
            captured_output = []
            deadline = time.time() + req_timeout
            timed_out = False
            try:
                while True:
                    if time.time() > deadline:
                        timed_out = True
                        try:
                            process.kill()
                        except Exception:
                            pass
                        break
                    try:
                        r, _, _ = select.select([master_fd], [], [], 0.5)
                        if master_fd in r:
                            try:
                                chunk = os.read(master_fd, 10240).decode('utf-8', errors='replace')
                            except OSError:
                                break
                            if not chunk:
                                if process.poll() is not None:
                                    break
                                continue
                            captured_output.append(chunk)
                        elif process.poll() is not None:
                            # Drain any remaining output, then exit
                            try:
                                while True:
                                    rr, _, _ = select.select([master_fd], [], [], 0.2)
                                    if master_fd not in rr:
                                        break
                                    extra = os.read(master_fd, 10240).decode('utf-8', errors='replace')
                                    if not extra:
                                        break
                                    captured_output.append(extra)
                            except OSError:
                                pass
                            break
                    except OSError:
                        break
            finally:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
                try:
                    process.wait(timeout=5)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    try:
                        process.wait(timeout=5)
                    except Exception:
                        pass

            full_text = "".join(captured_output)
            if timed_out:
                print("--- CAPTURE TIMEOUT ---")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Timed out after {req_timeout}s.", "stdout": full_text}).encode('utf-8'))
                return

            print(f"--- CAPTURE SUCCESS ---")
            print(f"Captured: {len(full_text)} chars")

            # 5. Send Response
            response_data = {
                "stdout": full_text,
                "stderr": "",
                "returncode": process.returncode
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))

        except Exception as e:
            print(f"ERROR: {e}")
            self.send_error(500, str(e))

if __name__ == "__main__":
    with socketserver.ThreadingTCPServer((HOST, PORT), LlamaRequestHandler) as httpd:
        print(f"--- Llama Bridge v17 (PTY Mode + Security) ---")
        print(f"Listening on: http://{HOST}:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()