#!/usr/bin/env python3
"""
Development server with hot-reloading for MCP Arduino Server
"""
import os
import sys
import time
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ReloadHandler(FileSystemEventHandler):
    def __init__(self):
        self.process = None
        self.start_server()

    def start_server(self):
        """Start the MCP Arduino server"""
        if self.process:
            print("🔄 Restarting server...")
            self.process.terminate()
            self.process.wait()
        else:
            print("🚀 Starting MCP Arduino Server in development mode...")

        env = os.environ.copy()
        env['LOG_LEVEL'] = 'DEBUG'

        self.process = subprocess.Popen(
            [sys.executable, "-m", "mcp_arduino_server.server"],
            env=env,
            cwd=Path(__file__).parent.parent
        )

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f"📝 Detected change in {event.src_path}")
            self.start_server()

def main():
    handler = ReloadHandler()
    observer = Observer()

    # Watch the source directory
    src_path = Path(__file__).parent.parent / "src"
    observer.schedule(handler, str(src_path), recursive=True)
    observer.start()

    print(f"👁️ Watching {src_path} for changes...")
    print("Press Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        if handler.process:
            handler.process.terminate()
    observer.join()

if __name__ == "__main__":
    main()