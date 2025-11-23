# agent-api/populate_kb.py   (run once with `docker compose run --rm agent-api python populate_kb.py`)
import asyncio, json, redis.asyncio as aioredis

async def main():
    r = await aioredis.from_url("redis://redis:6379", decode_responses=True)

    # Example static entries
    facts = [
        {"id": "wiki:python", "content": "Python is a high‑level programming language.", "source": "Wikipedia"},
        {"id": "product:1234", "content": "Acme SuperWidget 3000 – weight 5 kg, colour blue.", "source": "Catalog"}
    ]

    for f in facts:
        await r.hset(f"KB:{f['id']}", mapping=f)

    print("Static KB populated")
    await r.close()

if __name__ == "__main__":
    asyncio.run(main())
