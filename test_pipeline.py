import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid

# Grab your actual secret from your config
try:
    from backend.config import settings

    SECRET = settings.GITHUB_WEBHOOK_SECRET
except ImportError:
    print(
        "❌ Error: Could not import backend.config.settings. Run this script from the root folder."
    )
    sys.exit(1)

print("🚀 Starting the All-In-One Test Pipeline...")

# 1. Write a temporary script to run the worker safely in Python 3.14
worker_script_content = """
import asyncio
from arq.worker import run_worker
from backend.job_queue.worker import WorkerSettings

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    run_worker(WorkerSettings)
"""
with open("temp_worker_runner.py", "w") as f:
    f.write(worker_script_content.strip())

# 2. Start the FastAPI server and the Worker in the background
env = os.environ.copy()
env["PYTHONPATH"] = "."

print("📦 Booting FastAPI Ingress...")
api_process = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.api.webhooks:app", "--port", "8000"],
    env=env,
)

print("📦 Booting ARQ Worker...")
worker_process = subprocess.Popen([sys.executable, "temp_worker_runner.py"], env=env)

try:
    print("⏳ Giving services 4 seconds to wake up...")
    time.sleep(4)

    print("\n📤 Sending simulated GitHub Webhook...")
    payload = {
        "action": "opened",
        "repository": {"full_name": "aman/test-repo"},
        "pull_request": {"number": 99, "head": {"sha": "abc1234"}},
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    # Sign the payload securely
    signature = hmac.new(
        SECRET.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256
    ).hexdigest()

    req = urllib.request.Request(
        "http://localhost:8000/webhook/github", data=payload_bytes
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("X-GitHub-Event", "pull_request")
    req.add_header("X-GitHub-Delivery", str(uuid.uuid4()))
    req.add_header("X-Hub-Signature-256", f"sha256={signature}")

    try:
        response = urllib.request.urlopen(req)
        print(f"\n✅ Webhook Response from API: {response.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"\n❌ Webhook Failed ({e.code}): {e.read().decode()}")

    print("\n⏳ Waiting 3 seconds to let the worker process the job...")
    time.sleep(3)

finally:
    print("\n🛑 Shutting down all services...")
    api_process.terminate()
    worker_process.terminate()
    if os.path.exists("temp_worker_runner.py"):
        os.remove("temp_worker_runner.py")
    print("🏁 Test pipeline finished.")
