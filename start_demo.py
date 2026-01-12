import subprocess
import sys
import webbrowser
import time
import threading
import os

def start_server():
    """Start the Flask server in a separate process"""
    try:
        subprocess.Popen([sys.executable, "app.py"])
        print("🚀 Flask server started successfully")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

def open_browser():
    """Open the demo pages in browser after server starts"""
    time.sleep(4)  # Wait for server to initialize

    try:
        print("🌐 Opening main demo...")
        webbrowser.open("http://localhost:5000")

        time.sleep(2)

        print("📊 Opening admin dashboard...")
        webbrowser.open("http://localhost:5000/admin")

    except Exception as e:
        print(f"❌ Error opening browser: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("🏥 ProtoMinds Health Chatbot Demo Launcher")
    print("=" * 50)

    # Check if required files exist
    required_files = ["app.py", "templates/index.html", "templates/admin.html"]
    missing_files = [f for f in required_files if not os.path.exists(f)]

    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        print("Please ensure all files are in place.")
        sys.exit(1)

    print("✅ All required files found")
    print("🚀 Starting server and opening browser...")

    # Start server in background thread
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()

    # Open browser
    open_browser()

    print("=" * 50)
    print("📊 Vedura Demo Ready!")
    print("Main Demo: http://localhost:5000")
    print("Admin Dashboard: http://localhost:5000/admin")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)

    try:
        # Keep the script running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Demo stopped. Thank you!")