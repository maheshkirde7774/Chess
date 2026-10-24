"""
Convenience entry point to run Neon Four Chess backend.
"""
import os
import sys
import uvicorn

# Ensure backend directory is in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "True").lower() == "true"
    print("\n=======================================================")
    print("  NEON FOUR CHESS SERVER READY!")
    print(f"  Open in your web browser: http://localhost:{port}")
    print(f"  Or LAN / Mobile URL:      http://127.0.0.1:{port}")
    print("=======================================================\n")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
