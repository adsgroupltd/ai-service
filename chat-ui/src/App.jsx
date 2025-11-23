import { useState } from "react";
import axios from "axios";

export default function App() {
  const [msg, setMsg] = useState("");
  const [history, setHistory] = useState([]);

  const send = async () => {
    if (!msg.trim()) return;
    const userMessage = { role: "user", content: msg };
    const newHist = [...history, userMessage];
    setHistory(newHist);
    setMsg("");

    try {
      // NOTE: the UI runs inside Docker (nginx) and talks to the
      // agent‑api container via its service name.
      const resp = await axios.post(
        "http://agent-api:8000/api/chat",
        {
          user_id: "demo_user",
          messages: newHist,
        }
      );

      const assistantMsg = {
        role: "assistant",
        content: resp.data.assistant,
      };
      setHistory([...newHist, assistantMsg]);
    } catch (e) {
      console.error(e);
      alert("Error – check browser console");
    }
  };

  return (
    <div style={{ maxWidth: "800px", margin: "auto", padding: "1rem" }}>
      <h2>🧠 LM‑Studio Agent Demo</h2>

      <div
        style={{
          border: "1px solid #ccc",
          minHeight: "300px",
          padding: "0.5rem",
          overflowY: "auto"
        }}
      >
        {history.map((m, i) => (
          <p key={i}>
            <strong>{m.role}:</strong> {m.content}
          </p>
        ))}
      </div>

      <textarea
        rows="3"
        style={{ width: "100%", marginTop: "0.5rem" }}
        value={msg}
        onChange={(e) => setMsg(e.target.value)}
        placeholder="Ask something…"
      />
      <button onClick={send} style={{ marginTop: "0.5rem" }}>
        Send
      </button>
    </div>
  );
}
