import asyncio

from arq.connections import RedisSettings


async def process_pull_request(ctx, pr_data: dict):
    job_id = ctx["job_id"]
    repo = pr_data.get("repo_full_name")
    pr_num = pr_data.get("pr_number")

    print(f"\n[Worker] Picked up job {job_id}")
    print(f"\n[Worker] Processing PR {pr_num} for Repo {repo}...")

    await asyncio.sleep(2)

    print(f"[Worker] SUCCESS! Finished processing PR #{pr_num}\n")
    return {"status": "success", "repo": repo, "pr": pr_num}


class WorkerSettings:
    functions = [process_pull_request]

    redis_settings = RedisSettings(host="localhost", port=6379)

    async def on_startup(ctx):
        print("ARQ Worker started, Listening for jobs...")
