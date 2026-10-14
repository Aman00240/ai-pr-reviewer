import hashlib
import hmac
import json
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import FastAPI, Header, HTTPException, Request

from backend.core.config import settings

GITHUB_WEBHOOK_SECRET = settings.GITHUB_WEBHOOK_SECRET
REDIS_SETTINGS = RedisSettings(host="localhost", port=6379)
redis_pool: ArqRedis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_pool
    redis_pool = await create_pool(REDIS_SETTINGS)

    yield

    await redis_pool.close()


app = FastAPI(title="AI PR Reviewer Ingress", lifespan=lifespan)


async def verify_github_signature(request: Request) -> bytes:

    signature_header = request.headers.get("X-Hub-Signature-256")

    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing signature header")

    raw_body = await request.body()

    hash_object = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256
    )

    expected_signature = "sha256=" + hash_object.hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")

    return raw_body


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None),
    x_github_delivery: str = Header(None),
):
    raw_body = await verify_github_signature(request)
    payload = json.loads(raw_body)

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"Not listening for {x_github_event}"}

    action = payload.get("action")
    if action not in ["opened", "synchronize", "reopened"]:
        return {"status": "ignored", "reason": f"PR action '{action}' not handled"}

    if not redis_pool:
        raise HTTPException(status_code=500, detail="Redis connection failed")

    is_new_delivery = await redis_pool.set(
        f"webhook_delivery:{x_github_delivery}", "1", ex=86400, nx=True
    )

    if not is_new_delivery:
        print(f"Duplicate delivery detected ({x_github_delivery}). Dropping.")
        return {"status": "ignored", "reason": "Duplicate webhook delivery"}

    pr_data = {
        "repo_full_name": payload["repository"]["full_name"],
        "pr_number": payload["pull_request"]["number"],
        "commit_sha": payload["pull_request"]["head"]["sha"],
        "delivery_id": x_github_delivery,
    }

    print(
        f"Enqueueing job for PR #{pr_data['pr_number']} in {pr_data['repo_full_name']}"
    )
    await redis_pool.enqueue_job("process_pull_request", pr_data)

    return {"status": "accepted", "queued": True}
