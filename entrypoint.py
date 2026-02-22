#!/usr/bin/env python3
"""
Entrypoint script for MacReplayXC
Alternative to start.sh (no bash required, no line ending issues)
"""

import os
import sys
import subprocess

def main():
    print("🚀 Starting MacReplayXC...")
    
    # Start MacReplayXC
    print("🎬 Starting MacReplayXC on port 8001...")
    os.chdir("/app")
    
    try:
        # Run MacReplayXC (this blocks until it exits)
        subprocess.run([sys.executable, "app.py"], check=True)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"❌ Error running MacReplayXC: {e}")
    finally:
        print("✅ Shutdown complete")

if __name__ == "__main__":
    main()

