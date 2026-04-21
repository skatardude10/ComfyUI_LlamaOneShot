import http.server
import socketserver
import json
import subprocess
import shlex
import os
import pty
import select

# CONFIGURATION
PORT = 5050
HOST = "127.0.0.1"

class LlamaRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        # --- SECURITY CHECK 1: LOCALHOST ONLY ---
        if self.client_address[0] != "127.0.0.1":
            self.send_error(403, "Access Denied: Localhost only.")
            return

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            binary_path = data.get('binary_path', '')
            
            # --- SECURITY CHECK 2: BINARY ALLOWLIST ---
            if not binary_path:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Bad Request: Binary path is missing."}).encode('utf-8'))
                return

            # Extract just the filename from the path
            base_name = os.path.basename(binary_path).lower()
            # Strip .exe for Windows compatibility
            if base_name.endswith('.exe'):
                base_name = base_name[:-4]

            # Allowed executables list
            allowed_bins = ["llama-cli", "llama-completion", "llama-server", "main", "server"]
            if base_name not in allowed_bins:
                error_msg = f"Security Alert: '{os.path.basename(binary_path)}' is not an allowed executable."
                print(f"BLOCKED: {error_msg}")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": error_msg}).encode('utf-8'))
                return
            # ------------------------------------------

            flags_str = data.get('flags', '')
            prompt = data.get('prompt', '')
            
            # Fetch multiple image paths (new node behavior)
            image_paths = data.get('image_paths', [])
            
            # Fallback for backwards compatibility with older versions of the node
            if not image_paths and data.get('image_path'):
                image_paths = [data.get('image_path')]

            # 1. Build Command
            args = shlex.split(flags_str)
            command = [binary_path] + args
            
            # Append each valid image path as a separate --image flag
            for path in image_paths:
                if path and path.strip() and os.path.exists(path):
                    command.extend(["--image", path])

            command.extend(["-p", prompt])

            print(f"\nEXECUTING (PTY Mode):\n{shlex.join(command)}\n")

            # 2. CREATE FAKE TERMINAL
            # master_fd is what WE read. slave_fd is what llama-cli writes to.
            master_fd, slave_fd = pty.openpty()

            # 3. RUN
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL, # No input allowed
                stdout=slave_fd,          # Output to fake terminal
                stderr=slave_fd,          # Merge logs to fake terminal
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # Close slave in parent so we get EOF when process dies
            os.close(slave_fd)

            # 4. READ LOOP
            captured_output = []
            while True:
                try:
                    # Wait 0.1s for data
                    r, _, _ = select.select([master_fd], [], [], 0.1)
                    if master_fd in r:
                        # Read raw bytes from the fake terminal
                        chunk = os.read(master_fd, 10240).decode('utf-8', errors='replace')
                        if not chunk:
                            break
                        captured_output.append(chunk)
                    elif process.poll() is not None:
                        # Process died and no data left
                        break
                except OSError:
                    break

            full_text = "".join(captured_output)
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
        print(f"--- Llama Bridge v16 (PTY Mode + Security) ---")
        print(f"Listening on: http://{HOST}:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()