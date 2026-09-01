from http.server import HTTPServer, SimpleHTTPRequestHandler
import sys, os

os.chdir("D:\\program\\AIscience\\dashboard")

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

try:
    s = HTTPServer(('0.0.0.0', 8770), Handler)
    print("Server started on port 8770", flush=True)
    s.serve_forever()
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    sys.exit(1)
