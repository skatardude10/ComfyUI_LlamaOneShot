import http.server
import socketserver
import json
import subprocess
import shlex
import os

# CONFIGURATION
PORT = 5050
HOST = "127.0.0.1"

class LlamaRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.client_address[0] != "127.0.0.1":
            self.send_error(403, "Access Denied: Localhost only.")
            return

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            binary_path = data.get('binary_path', '')
            flags_str = data.get('flags', '')
            prompt = data.get('prompt', '')

            if not binary_path:
                raise ValueError("Binary path is missing.")

            allowed_bins = ["llama-cli", "llama-completion", "llama-server", "main", "server"]
            if os.path.basename(binary_path) not in allowed_bins:
                 raise ValueError(f"Security Alert: '{os.path.basename(binary_path)}' is not an allowed executable.")

            # 1. Parse flags
            args = shlex.split(flags_str)
            
            # 2. Build Command (Binary + Flags + Prompt)
            command = [binary_path] + args + ["-p", prompt]

            # Debug: Print exact command to terminal
            print(f"\nEXECUTING:\n{shlex.join(command)}\n")

            # 3. Run
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            response_data = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))

        except Exception as e:
            print(f"ERROR: {e}")
            error_response = {"error": str(e)}
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode('utf-8'))
    
#    def log_message(self, format, *args):
#       return

if __name__ == "__main__":
    with socketserver.ThreadingTCPServer((HOST, PORT), LlamaRequestHandler) as httpd:
        print(f"--- Llama Bridge v4 (Raw Pipe) ---")
        print(f"Listening on: http://{HOST}:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()