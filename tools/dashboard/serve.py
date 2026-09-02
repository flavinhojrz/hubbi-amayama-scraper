import http.server
import socketserver
import webbrowser
import os
import sys

PORT = 8080
# The script is in tools/dashboard/
current_dir = os.path.dirname(os.path.abspath(__file__))
# The project root should be two levels up from tools/dashboard/
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))

os.chdir(project_root)

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    # Disable cache to always get the latest json/html
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

Handler = CustomHandler

print(f"Starting server at {project_root}", flush=True)
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    url = f"http://localhost:{PORT}/tools/dashboard/index.html"
    print(f"Serving on port {PORT}", flush=True)
    print(f"Dashboard available at: {url}", flush=True)
    print("Opening browser...", flush=True)
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.", flush=True)
        sys.exit(0)
