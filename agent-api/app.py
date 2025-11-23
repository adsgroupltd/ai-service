import os, json, openai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------
# Configuration (read from .env)
# -------------------------------------------------
OPENAI_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")
LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "host.docker.internal")
LMSTUDIO_PORT = int(os.getenv("LMSTUDIO_PORT", "12345"))
REDIS_URL = f"redis://{os.getenv('REDIS_HOST','redis')}:{os.getenv('REDIS_PORT','6379')}"
MAX_LOOKUP_HISTORY = int(os.getenv("AGENT_MAX_LOOKUP_HISTORY","500"))

# -------------------------------------------------
# OpenAI client that talks to LM Studio (host endpoint)
# -------------------------------------------------
openai.base_url = f"http://{LMSTUDIO_HOST}:{LMSTUDIO_PORT}/v1"
openai.api_key = os.getenv("AGENT_OPENAI_API_KEY", "dummy")   # any non‑empty string works

# -------------------------------------------------
# Redis connection
# -------------------------------------------------
rdb = aioredis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI()


# -----------------------------------------------------------------
# Pydantic models for the API payload
# -----------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str   # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the end‑user")
    messages: list[ChatMessage] = Field(
        ..., description="Full conversation history (including latest user message)"
    )
    session_id: str | None = None   # optional – not used in this demo


# -----------------------------------------------------------------
# Helper utilities
# -----------------------------------------------------------------
async def store_lookup(user_id: str, lookup: dict) -> None:
    """Append a lookup record to the per‑user list and trim it."""
    key = f"USER:{user_id}:LOOKUPS"
    await rdb.lpush(key, json.dumps(lookup))
    await rdb.ltrim(key, 0, MAX_LOOKUP_HISTORY - 1)


async def fetch_knowledge(user_id: str, query: str = "", limit: int = 20) -> list[dict]:
    """
    Return everything the agent has ever “learned” for this user.
    If `query` is non‑empty we do a simple substring filter.
    """
    raw = await rdb.lrange(f"USER:{user_id}:LOOKUPS", 0, -1)
    items = [json.loads(x) for x in raw]

    if query:
        q = query.lower()
        items = [i for i in items if q in i.get("query", "").lower()]

    return items[:limit]


# -----------------------------------------------------------------
# Main endpoint – forces a tool call, logs the lookup, then answers
# -----------------------------------------------------------------
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    # The last message must be from the user
    if req.messages[-1].role != "user":
        raise HTTPException(400, detail="Last message must be a user message")

    system_prompt = {
        "role": "system",
        "content": (
            "You are an AI assistant that never answers directly. "
            "Before you can respond, you **must** call the tool `get_knowledge` to retrieve everything you have ever learned for this user. "
            "If you think no external data is needed, still call the tool with an empty query – it will return all prior lookups."
        ),
    }

    # Build OpenAI‑compatible message list
    openai_messages = [system_prompt] + [
        {"role": m.role, "content": m.content} for m in req.messages
    ]

    # -----------------------------------------------------------------
    # 1️⃣ First LLM call – we expect a function (tool) request
    # -----------------------------------------------------------------
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_knowledge",
                "description": "Retrieve all knowledge the model has accessed for this user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search term (optional). Empty string returns everything."
                        },
                        "limit": {
                            "type": "integer",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100
                        }
                    },
                    "required": []
                },
            },
        }
    ]

    first_resp = await openai.ChatCompletion.acreate(
        model=OPENAI_MODEL,
        messages=openai_messages,
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "get_knowledge"}},
        temperature=0.0,  # deterministic for the tool request
    )
    first_msg = first_resp["choices"][0]["message"]

    if not first_msg.get("tool_calls"):
        return {
            "error": "Model did not request a knowledge lookup",
            "model_output": first_msg.get("content", ""),
        }

    tool_call = first_msg["tool_calls"][0]
    args = json.loads(tool_call["function"]["arguments"])
    query = args.get("query", "")
    limit = int(args.get("limit", 20))

    # -----------------------------------------------------------------
    # 2️⃣ Perform the Redis lookup
    # -----------------------------------------------------------------
    knowledge_items = await fetch_knowledge(req.user_id, query=query, limit=limit)

    # Record this lookup for future “everything” queries
    await store_lookup(
        req.user_id,
        {
            "timestamp": int(openai.utils.now()),
            "query": query,
            "limit": limit,
            "result_count": len(knowledge_items),
        },
    )

    tool_response = {
        "role": "tool",
        "name": tool_call["function"]["name"],
        "content": json.dumps({"items": knowledge_items}),
    }

    # -----------------------------------------------------------------
    # 3️⃣ Second LLM call – now with the tool result in context
    # -----------------------------------------------------------------
    second_resp = await openai.ChatCompletion.acreate(
        model=OPENAI_MODEL,
        messages=openai_messages + [first_msg, tool_response],
        temperature=0.7,
    )
    final_msg = second_resp["choices"][0]["message"]

    return {
        "assistant": final_msg["content"],
        "usage": second_resp.get("usage", {}),
        "lookup_meta": {
            "query": query,
            "limit": limit,
            "returned_items": len(knowledge_items),
        },
    }
