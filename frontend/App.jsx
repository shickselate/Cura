import React, { useState, useEffect, useRef } from "react";

const AVATAR_STATES = ["welcoming", "listening", "concerned", "supportive", "thinking"];

function App() {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hello, I'm Dr. Lane. What would you like to talk about today?" },
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [avatarState, setAvatarState] = useState("welcoming");
  const [affect, setAffect] = useState("a little tense but open");
  const [affectState, setAffectState] = useState("emotionally neutral");
  const [debug, setDebug] = useState({});
  const chatMessagesRef = useRef(null);


  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (chatMessagesRef.current) {
      chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;

    const newMessages = [...messages, { role: "user", content: text }];
    setMessages(newMessages);
    setInput("");

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          user_message: text,
          affect,
          avatar_state: avatarState,
        }),
      });
      const data = await res.json();

      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply },
      ]);
      setAvatarState(data.avatar_state || avatarState);
      setDebug(data.debug || {});
      if (data.debug && data.debug.affect_state) {
      setAffectState(data.debug.affect_state);
      }

    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `(Error contacting backend: ${err})` },
      ]);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const currentAvatarSrc = `/avatars/${avatarState}.png`;

  return (
    <div className="app-root">
      <div className="main-row">
        {/* Left: avatar */}
        <div className="avatar-pane">
          <img
            src={currentAvatarSrc}
            alt={`Clinician - ${avatarState}`}
            className="avatar-image"
            onError={(e) => (e.target.style.visibility = "hidden")}
          />
          <div className="avatar-controls">
            <span>Avatar state:</span>
            <div className="avatar-buttons">
              {AVATAR_STATES.map((state) => (
                <button
                  key={state}
                  className={state === avatarState ? "active" : ""}
                  onClick={() => setAvatarState(state)}
                >
                  {state}
                </button>
              ))}
            </div>
          </div>
          <div className="affect-control">
            <label>
              Current affect estimate:
              <div className="affect-display">
                {affectState}
              </div>
            </label>
          </div>
        </div>
        {/* Right: chat */}
        <div className="chat-pane">
          <div className="chat-messages" ref={chatMessagesRef}>
            {messages.map((m, i) => (
              <div
                key={i}
                className={`chat-message ${m.role === "assistant" ? "assistant" : "user"}`}
              >
                <div className="chat-bubble">
                  <strong>{m.role === "assistant" ? "Clinician" : "You"}: </strong>
                  {m.content}
                </div>
              </div>
            ))}
          </div>
          <div className="chat-input-row">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your message and press Enter..."
            />
            <button onClick={handleSend}>Send</button>
          </div>
        </div>
      </div>

      {/* Bottom: debug */}
      <div className="debug-pane">
        <h3>Debug / Control</h3>
        <pre>{JSON.stringify({ sessionId, avatarState, affect, debug }, null, 2)}</pre>
      </div>
    </div>
  );
}

export default App;
