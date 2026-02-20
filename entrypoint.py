#!/usr/bin/env python3
"""
Entrypoint script for MacReplayXC + Vavoo
Alternative to start.sh (no bash required, no line ending issues)
"""

import os
import sys
import time
import subprocess
import signal

def main():
    print("🚀 Starting MacReplayXC + Vavoo...")
    
    # Extract public host from HOST environment variable
    host = os.getenv("HOST", "")
    if host:
        # Remove http:// or https://
        public_host_clean = host.replace("http://", "").replace("https://", "")
        # Extract hostname (without port)
        public_hostname = public_host_clean.split(":")[0]
        
        os.environ["VAVOO_PUBLIC_HOST"] = public_hostname
        os.environ["VAVOO_PORT"] = "4323"
        
        print(f"📡 Vavoo public host: {public_hostname}:4323")
    else:
        print("⚠️  No HOST environment variable set, using auto-detection")
    
    # Start Vavoo in background
    print("📡 Starting Vavoo on port 4323...")
    os.chdir("/app/vavoo")
    vavoo_process = subprocess.Popen(
        [sys.executable, "vavoo2.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print(f"✅ Vavoo started (PID: {vavoo_process.pid})")
    
    # Wait a moment for Vavoo to start
    time.sleep(2)
    
    # Start MacReplayXC in foreground
    print("🎬 Starting MacReplayXC on port 8001...")
    os.chdir("/app")
    
    # Handle signals to cleanup Vavoo process
    def signal_handler(signum, frame):
        print(f"\n⚠️  Received signal {signum}, shutting down...")
        vavoo_process.terminate()
        try:
            vavoo_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            vavoo_process.kill()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Run MacReplayXC (this blocks until it exits)
        subprocess.run([sys.executable, "app.py"], check=True)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"❌ Error running MacReplayXC: {e}")
    finally:
        # Cleanup: Kill Vavoo process
        print("🛑 Stopping Vavoo...")
        vavoo_process.terminate()
        try:
            vavoo_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            vavoo_process.kill()
        print("✅ Shutdown complete")

if __name__ == "__main__":
    main()
