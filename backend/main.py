from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import uuid
from pathlib import Path
import logging
import time
from concurrent.futures import ThreadPoolExecutor

DEFAULT_AVATAR_STATE = "welcoming"

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3"

app = FastAPI()

# Persistent HTTP session (required for Windows performance)
http_session = requests.Session()

# Enable CORS during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------------------------------------
# Load avatar expressions dynamically from avatar folder
# ---------------------------------------------------------
AVATAR_FOLDER = Path(__file__).parent.parent / "frontend" / "public" / "avatars"

if AVATAR_FOLDER.exists():
    AVATAR_EXPRESSIONS = [
        f.stem.lower()
        for f in AVATAR_FOLDER.iterdir()
        if f.is_file()
    ]
else:
    AVATAR_EXPRESSIONS = []
    print("WARNING: Avatar folder not found:", AVATAR_FOLDER)

print("Loaded avatars:", AVATAR_EXPRESSIONS)


# In-memory conversation store
conversations: dict[str, dict] = {}

logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------
class ChatRequest(BaseModel):
    session_id: str | None = None
    user_message: str
    affect: str | None = None
    avatar_state: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    avatar_state: str
    debug: dict


# ---------------------------------------------------------
# Helper: Parse LLM Response
# ---------------------------------------------------------
def parse_ollama_response(data: dict) -> str | None:
    """Extract content from Ollama response, trying multiple response formats."""
    if isinstance(data, dict):
        # Try standard format first
        if "message" in data and isinstance(data["message"], dict):
            content = data["message"].get("content")
            if content:
                return content.strip()
        # Fallback to alternate format
        if "response" in data:
            content = data["response"]
            if content:
                return str(content).strip()
    return None


# ---------------------------------------------------------
# Affect Estimation LLM Call
# ---------------------------------------------------------
def update_affect_state(prev_state: str, last_msg: str) -> tuple[str, int]:
    prompt = (
        f"Previous state: {prev_state}\n"
        f"Message: \"{last_msg}\"\n"
        "Update the emotional state using 3–6 emotional keywords. "
        "Output only the keywords, comma-separated."
    )

    logging.debug("AFFECT PROMPT LENGTH: %d", len(prompt))

    start = time.time()

    try:
        r = http_session.post(
            OLLAMA_URL,
            json={"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}], "stream": False},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()

        content = None
        if "message" in data and isinstance(data["message"], dict):
            content = data["message"].get("content")
        if not content and "response" in data:
            content = data["response"]

        affect_ms = int((time.time() - start) * 1000)

        if content:
            return content.strip(), affect_ms

        logging.warning("Affect LLM returned no content: %s", data)
        return prev_state, affect_ms

    except Exception as e:
        affect_ms = int((time.time() - start) * 1000)
        logging.error("update_affect_state error: %s", e)
        return prev_state, affect_ms


# ---------------------------------------------------------
# Avatar Selection LLM Call
# ---------------------------------------------------------
def select_avatar_expression(affect_state: str, reply_text: str) -> tuple[str, int]:
    avatar_list_str = ", ".join(AVATAR_EXPRESSIONS)

    prompt = (
        "You are selecting the best clinician facial expression for a VR avatar.\n\n"
        f"User emotional state: \"{affect_state}\"\n"
        f"Clinician reply: \"{reply_text}\"\n\n"
        f"Available expressions: {avatar_list_str}\n\n"
        "Choose exactly one expression from the list.\n"
        "Respond with ONLY the expression name."
    )

    start = time.time()

    try:
        r = http_session.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            },
            timeout=20,
        )

        r.raise_for_status()
        data = r.json()

        content = parse_ollama_response(data)
        avatar_ms = int((time.time() - start) * 1000)

        if content:
            avatar_expr = content.strip().lower()
            # Validate that the returned expression is in the allowed list
            if avatar_expr in AVATAR_EXPRESSIONS:
                logging.debug("Selected avatar expression: %s", avatar_expr)
                return avatar_expr, avatar_ms
            else:
                logging.warning("LLM returned invalid avatar expression '%s' (not in %s), using default", avatar_expr, AVATAR_EXPRESSIONS)

        return DEFAULT_AVATAR_STATE, avatar_ms

    except Exception as e:
        avatar_ms = int((time.time() - start) * 1000)
        logging.error("avatar expression selection error: %s", e)
        return DEFAULT_AVATAR_STATE, avatar_ms


# ---------------------------------------------------------
# System Prompt
# ---------------------------------------------------------
def build_system_prompt(affect_state: str) -> str:
    affect_text = affect_state or "emotionally neutral"
    return (
        "You are a character in a story representing a clinician.\n"
        "You speak in very short, warm replies (1–3 sentences).\n"
        f"In the story, the patient appears: {affect_text}.\n"
        "You are warm, clear, and boundaried.\n"
        "You do not provide real medical advice.\n"
        "Use no more than 40–50 words.\n"
    )


# ---------------------------------------------------------
# Main Chat LLM Call
# ---------------------------------------------------------
def call_ollama_for_reply(messages: list[dict]) -> tuple[str, int]:
    start_reply = time.time()
    try:
        payload = {"model": MODEL_NAME, "messages": messages, "stream": False}
        r = http_session.post(OLLAMA_URL, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()

        reply_text = parse_ollama_response(data)

        if not reply_text:
            logging.warning("call_ollama_for_reply: unexpected response: %s", data)
            reply_text = "(Error: unexpected model response)"

        reply_ms = int((time.time() - start_reply) * 1000)
        return reply_text, reply_ms

    except Exception as e:
        reply_ms = int((time.time() - start_reply) * 1000)
        logging.error("call_ollama_for_reply error: %s", e)
        return f"(Error talking to model: {e})", reply_ms


# ---------------------------------------------------------
# API Endpoint
# ---------------------------------------------------------
def cleanup_old_sessions(max_age_seconds: int = 3600) -> None:
    """Remove sessions older than max_age_seconds (default 1 hour)."""
    current_time = time.time()
    expired_ids = [
        sid for sid, session in conversations.items()
        if current_time - session.get("created_at", current_time) > max_age_seconds
    ]
    for sid in expired_ids:
        del conversations[sid]
        logging.debug("Cleaned up expired session: %s", sid)


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):

    # Create new session if missing
    if req.session_id and req.session_id in conversations:
        session_id = req.session_id
    else:
        session_id = str(uuid.uuid4())
        conversations[session_id] = {
            "messages": [],
            "affect_state": "emotionally neutral",
            "avatar_state": DEFAULT_AVATAR_STATE,
            "created_at": time.time(),  # Track creation time for cleanup
        }

    session = conversations[session_id]
    history = session["messages"]

    current_affect = session["affect_state"]
    system_prompt = build_system_prompt(current_affect)

    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": req.user_message}
    ]

    start_total = time.time()

    # Phase 1: Parallel affect + reply calls
    with ThreadPoolExecutor(max_workers=2) as executor:
        affect_future = executor.submit(update_affect_state, current_affect, req.user_message)
        reply_future = executor.submit(call_ollama_for_reply, messages)

        new_affect, affect_ms = affect_future.result()
        reply_text, reply_ms = reply_future.result()

    # Phase 2: Avatar selection (depends on reply, so sequential)
    avatar_expr, avatar_ms = select_avatar_expression(new_affect, reply_text)
    session["avatar_state"] = avatar_expr

    total_ms = int((time.time() - start_total) * 1000)

    # Update session state
    session["affect_state"] = new_affect
    session["messages"] = history + [
        {"role": "user", "content": req.user_message},
        {"role": "assistant", "content": reply_text},
    ]

    avatar_state = avatar_expr

    debug_payload = {
        "session_id": session_id,
        "num_messages": len(session["messages"]),
        "affect_state": new_affect,
        "avatar_state": avatar_state,
        "affect_call_ms": affect_ms,
        "reply_call_ms": reply_ms,
        "avatar_call_ms": avatar_ms,
        "total_ms": total_ms,
    }

    # Cleanup old sessions (older than 1 hour)
    cleanup_old_sessions(max_age_seconds=3600)

    return ChatResponse(
        session_id=session_id,
        reply=reply_text,
        avatar_state=avatar_state,
        debug=debug_payload,
    )


# ---------------------------------------------------------
# Serve React frontend
# ---------------------------------------------------------
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
