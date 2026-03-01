#!/usr/bin/env python3
"""
Development startup script for EyeReadDemo v7 Backend
"""
import sys
import os
import subprocess

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == "__main__":
    print("🚀 Starting EyeReadDemo v7 Backend...")
    print("📍 Backend will be available at: http://localhost:8080")
    print("🔌 WebSocket endpoint: ws://localhost:8080/ws/{client_id}")
    print("📚 API docs: http://localhost:8080/docs")
    print("❤️  Health check: http://localhost:8080/health")
    print("\n" + "="*50)
    
    try:
        # Change to src directory and run uvicorn
        os.chdir(os.path.join(os.path.dirname(__file__), 'src'))
        subprocess.run([
            sys.executable, '-m', 'uvicorn', 
            'main:app', 
            '--host', '0.0.0.0', 
            '--port', '8080', 
            '--reload',
            '--log-level', 'info'
        ])
    except KeyboardInterrupt:
        print("\n🛑 Backend stopped by user")
    except Exception as e:
        print(f"❌ Error starting backend: {e}")
        sys.exit(1)
