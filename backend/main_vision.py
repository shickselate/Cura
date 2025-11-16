from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import uuid
from pathlib import Path
import logging
import time
from concurrent.futures import ThreadPoolExecutor

DEFAULT_AVATAR_STATE = "welcoming"

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"

app = FastAPI()
http_session = requests.Session()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Avatar loading
AVATAR_FOLDER = Path(__file__).parent.parent / "frontend" / "public" / "avatars"
if AVATAR_FOLDER.exists():
    # Only include common image file types to avoid picking non-image files
    IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
    AVATAR_EXPRESSIONS = [
        f.stem.lower()
        for f in AVATAR_FOLDER.iterdir()
        if f.is_file() and f.suffix.lower() in IMG_EXTS
    ]
else:
    AVATAR_EXPRESSIONS = []
    print("WARNING: Avatar folder not found:", AVATAR_FOLDER)

conversations: dict[str, dict] = {}


# ---------------------------------------------------------
# Models
# ---------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str | None = None
    user_message: str
    mode: str = "llama"       
    image_b64: str | None = None
    affect: str | None = None
    avatar_state: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    avatar_state: str
    debug: dict


# ---------------------------------------------------------
# Helper to parse Ollama responses
# ---------------------------------------------------------

def parse_ollama_response(data: dict) -> str | None:
    if "message" in data and isinstance(data["message"], dict):
        return data["message"].get("content")
    if "response" in data:
        return data["response"]
    return None


# ---------------------------------------------------------
# Affect estimation
# ---------------------------------------------------------

def update_affect_state(prev_state, last_msg):
    prompt = (
        f"Previous state: {prev_state}\n"
        f"Message: \"{last_msg}\"\n"
        "Update the emotional state using 3–6 emotional keywords. "
        "Output only the keywords, comma-separated."
    )

    start = time.time()
    try:
        r = http_session.post(
            OLLAMA_URL,
            json={"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}], "stream": False}
        )
        data = r.json()
        affect_ms = int((time.time() - start) * 1000)
        content = parse_ollama_response(data)
        return (content or prev_state).strip(), affect_ms
    except:
        return prev_state, int((time.time() - start) * 1000)


# ---------------------------------------------------------
# Avatar selection
# ---------------------------------------------------------

def select_avatar_expression(affect_state, reply_text):
    avatar_list_str = ", ".join(AVATAR_EXPRESSIONS)
    prompt = (
        "You are selecting the best clinician facial expression.\n\n"
        f"User emotional state: \"{affect_state}\"\n"
        f"Clinician reply: \"{reply_text}\"\n\n"
        f"Available expressions: {avatar_list_str}\n"
        "Choose EXACTLY ONE expression from this list. "
        "Do NOT invent new expressions. "
        "Respond with ONLY the expression name."
    )

    start = time.time()
    try:
        r = http_session.post(
            OLLAMA_URL,
            json={"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}], "stream": False}
        )
        data = r.json()
        avatar_ms = int((time.time() - start) * 1000)
        content = parse_ollama_response(data)
        if content:
            expr = content.strip().lower()
            if expr in AVATAR_EXPRESSIONS:
                return expr, avatar_ms
        return DEFAULT_AVATAR_STATE, avatar_ms
    except:
        return DEFAULT_AVATAR_STATE, int((time.time() - start) * 1000)


# ---------------------------------------------------------
# System prompt
# ---------------------------------------------------------

def build_system_prompt(affect_state):
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
# Main reply model (LLaMA)
# ---------------------------------------------------------

def call_ollama_for_reply(messages):
    start = time.time()
    try:
        r = http_session.post(
            OLLAMA_URL,
            json={"model": MODEL_NAME, "messages": messages, "stream": False}
        )
        data = r.json()
        reply_ms = int((time.time() - start) * 1000)
        content = parse_ollama_response(data)
        return (content or "(Error: no reply)").strip(), reply_ms
    except Exception as e:
        return f"(Error talking to model: {e})", int((time.time() - start) * 1000)


# ---------------------------------------------------------
# Vision (LLaVA)
# ---------------------------------------------------------

def call_llava_image(image_b64):
    start = time.time()
    try:
        if image_b64.startswith("data:"):
            _, b64data = image_b64.split(",", 1)
        else:
            b64data = image_b64

        prompt = (
            "You are a clinician character observing a single webcam frame.\n"
            "Briefly describe anything clinically or emotionally relevant.\n"
            "Use ONE or TWO short sentences."
        )

        r = http_session.post(
            OLLAMA_GENERATE_URL,
            json={"model": "llava", "prompt": prompt, "images": [b64data], "stream": False}
        )
        data = r.json()
        ms = int((time.time() - start) * 1000)
        return (data.get("response", "") or "").strip(), ms

    except Exception as e:
        return f"(Vision error: {e})", int((time.time() - start) * 1000)


# ---------------------------------------------------------
# Cleanup
# ---------------------------------------------------------

def cleanup_old_sessions(max_age=3600):
    now = time.time()
    dead = [sid for sid, sess in conversations.items() if now - sess["created_at"] > max_age]
    for sid in dead:
        del conversations[sid]


# ---------------------------------------------------------
# CHAT ENDPOINT (FULLY FIXED)
# ---------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):

    # Create or continue session
    if req.session_id and req.session_id in conversations:
        session_id = req.session_id
    else:
        session_id = str(uuid.uuid4())
        conversations[session_id] = {
            "messages": [],
            "affect_state": "emotionally neutral",
            "avatar_state": DEFAULT_AVATAR_STATE,
            "created_at": time.time(),
        }

    session = conversations[session_id]
    history = session["messages"]
    current_affect = session["affect_state"]

    # ----- Phase 1: Vision -----
    vision_text = ""
    vision_ms = 0
    use_vision = bool(req.image_b64)

    if use_vision:
        vision_text, vision_ms = call_llava_image(req.image_b64)

    # Build system prompt WITH structured vision block
    system_prompt = build_system_prompt(current_affect)

    if use_vision and vision_text:
        system_prompt += (
            "\n\nHere is the clinician's visual observation of the patient's current appearance:\n"
            f"[VISION]: {vision_text}\n"
            "Use this information to guide your reply, but do not repeat it verbatim."
        )

    # Build messages (history = text only)
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": req.user_message}
    ]

    # Debug real prompt
    print("\n==== LLaMA FULL PROMPT SENT ====")
    for m in messages:
        print(f"[{m['role']}]: {m['content']}")
    print("================================\n")

    # ----- Phase 2: Parallel affect + reply -----
    start_total = time.time()

    with ThreadPoolExecutor(max_workers=2) as ex:
        affect_f = ex.submit(update_affect_state, current_affect, req.user_message)
        reply_f = ex.submit(call_ollama_for_reply, messages)

        new_affect, affect_ms = affect_f.result()
        reply_text, reply_ms = reply_f.result()

    # Append vision visibly
    if use_vision and vision_text:
        reply_text += f"\n\n(Vision) {vision_text}"

    # ----- Phase 3: Avatar -----
    avatar_expr, avatar_ms = select_avatar_expression(new_affect, reply_text)
    session["avatar_state"] = avatar_expr

    # Update session (store ONLY text reply, not "(Vision)")
    session["affect_state"] = new_affect
    session["messages"] = history + [
        {"role": "user", "content": req.user_message},
        {"role": "assistant", "content": reply_text},
    ]

    total_ms = int((time.time() - start_total) * 1000)

    debug = {
        "session_id": session_id,
        "use_vision": use_vision,
        "vision_ms": vision_ms,
        "vision_text": vision_text,
        "affect_state": new_affect,
        "avatar_state": avatar_expr,
        "affect_call_ms": affect_ms,
        "reply_call_ms": reply_ms,
        "avatar_call_ms": avatar_ms,
        "total_ms": total_ms,
    }

    cleanup_old_sessions()

    return ChatResponse(
        session_id=session_id,
        reply=reply_text,
        avatar_state=avatar_expr,
        debug=debug,
    )


# ---------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")

print("FASTAPI IS SERVING FROM:", frontend_dist)
