
# Cura — LLM Clinician Avatar System (Backend + Frontend)

Cura is a prototype system for a virtual clinician that:
- Responds with short, supportive messages (LLM)
- Infers the user's emotional state (affect estimation)
- Selects an appropriate avatar expression (LLM-driven or rule-based)
- Displays a clinician portrait that changes dynamically
- Runs a React frontend served by a FastAPI backend

This README summarises the structure and behaviour of the `main.py` backend and overall app architecture.

---

## Overview

Cura consists of:

1. **React Frontend** (`frontend/`)
   - Shows the clinician avatar image
   - Provides a in-browser chat UI for user messages
   - Displays timing/debug info
   - Calls backend endpoints via `/api/chat`

2. **FastAPI Backend** (`backend/main.py`)
   - Handles session creation
   - Stores conversation history, affect state, and avatar state
   - Communicates with Ollama LLM for:
     - Affect estimation
     - Clinician reply generation
     - Avatar expression selection
   - Dynamically loads avatar images from `frontend/public/avatars/`
   - Serves the built React application

3. **Ollama Local Model**
   - Model: `llama3`
   - Used for all language tasks
   - Accessed via a persistent HTTP session for better performance on Windows

---

## Key Backend Features (`main.py`)

### 1. Session Management

Each chat session is tracked by:

- `messages` — conversation history
- `affect_state` — user affect updated every message
- `avatar_state` — current avatar expression (default `welcoming`)

Sessions persist in an in-memory dictionary (`conversations`).

---

### 2. Persistent HTTP Session

The backend uses a shared `requests.Session()`:

- Reuses TCP connections to Ollama
- Reduces per-call overhead on Windows
- Helps keep total latency under ~1 second

---

### 3. Affect Estimation

The function:

- `update_affect_state(prev_state, last_msg)`

Sends a short prompt to the LLM asking for:

- 3–6 emotional keywords
- A lightweight interpretation of the user's latest message
- A bias toward the previous affect state

It returns:

- The new affect string
- The call duration in milliseconds

---

### 4. Clinician Reply Generation

The main conversation LLM call builds a system prompt like:

- "You are a character in a story representing a clinician"
- "Use short, warm replies (1–3 sentences)"
- "Do not give real medical advice"
- "Patient appears: <affect_state>"

Then it appends recent chat history and the latest user message, and sends this to Ollama to generate a short clinician reply.

---

### 5. Avatar Expression Selection

The backend:

- Loads avatar filenames dynamically from `frontend/public/avatars/`
- Uses a separate LLM call to choose an avatar that fits:
  - The inferred user affect
  - The clinician reply text
  - (Optionally) the previous avatar state

The chosen avatar expression is returned in the API as `avatar_state`, and the frontend maps that to an image file, e.g.:

- `/avatars/welcoming.png`
- `/avatars/listening.png`
- `/avatars/head_down.png`

---

### 6. Parallel LLM Calls

Affect estimation and clinician reply run in parallel using `ThreadPoolExecutor`, so that:

- Affect estimation LLM call
- Clinician reply LLM call

happen at the same time. The total latency is then roughly:

- `max(affect_call_ms, reply_call_ms)` plus a small overhead

Avatar selection runs after the reply is available and is very fast.

---

### 7. Debug Panel Output

The backend returns a `debug` object that includes:

- `session_id`
- `num_messages`
- `affect_state`
- `avatar_state`
- `affect_call_ms`
- `reply_call_ms`
- `avatar_call_ms`
- `total_ms`

These are shown in a debug pane at the bottom of the UI during development.

---

## Frontend Overview

The React frontend:

- Displays the avatar image using the `avatarState` value from the backend
- Renders a scrollable chat window with user and clinician messages
- Uses a textarea + send button for user input
- Automatically scrolls to the bottom when a new message arrives
- Shows debug and timing information below the chat area

Frontend is built with Vite + React + a simple CSS layout that places:

- Avatar on the left
- Chat on the right
- Debug panel below

---

## Running the App

### Backend

From the `backend/` folder:

- Install dependencies (example):

  - `pip install fastapi uvicorn requests`

- Run the server:

  - `uvicorn main:app --reload`

Backend listens on `http://127.0.0.1:8000`.

Ollama must also be running locally with the `llama3` model pulled.

---

### Frontend (development)

From the `frontend/` folder:

- Install dependencies:

  - `npm install`

- Run in dev mode:

  - `npm run dev`

This will start the Vite dev server (typically on port 5173).

---

### Frontend (production via backend)

To build the frontend and serve it from FastAPI:

1. From `frontend/`:

   - `npm run build`

2. The build output goes into `frontend/dist/`.

3. The backend auto-mounts this folder:

   - If `frontend/dist` exists, `main.py` mounts it at `/` via `StaticFiles`.

You can then just run:

- `uvicorn main:app --reload`

and open the backend URL in the browser; FastAPI will serve the built React app directly.

---

## Folder Structure (Typical)

- `backend/`
  - `main.py` — FastAPI app, LLM calls, session and avatar logic

- `frontend/`
  - `src/` — React components and styles
  - `public/avatars/` — avatar images (PNG/JPG)
  - `dist/` — production build output (generated by Vite)

---

## Notes and Future Directions

- Avatars are loaded dynamically by reading filenames in `public/avatars/`.
- New avatars can be added by dropping new files into this folder and restarting the backend.
- Behaviour for avatar selection is currently driven by simple prompts and affect + reply context.
- Future work may:
  - Move avatar semantics to a metadata file
  - Add webcam-based affect estimation
  - Integrate a more explicit emotion / intent classifier
  - Support multiple clinician “personalities”

This codebase is intended as a prototype and playground for combining:
- Local LLMs (via Ollama)
- Affective computing
- Conversational UX
- Avatar-driven interaction in clinical-style scenarios.
