import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getChat, sendMessage } from "../../api/coach";

export default function ChatDetail() {
  const { id } = useParams();
  const [chat, setChat] = useState(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    load();
  }, [id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat?.messages?.length]);

  async function load() {
    try {
      const c = await getChat(id);
      setChat(c);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  async function handleSend(e) {
    e.preventDefault();
    if (!input.trim() || sending) return;
    const content = input.trim();
    setInput("");
    setError("");

    // Optimistic append of the user's message.
    setChat((prev) => ({
      ...prev,
      messages: [...prev.messages, { id: `temp-${Date.now()}`, role: "user", content }],
    }));
    setSending(true);
    try {
      const res = await sendMessage(id, content);
      setChat((prev) => ({
        ...prev,
        title: prev.title === "New Chat" ? content.slice(0, 60) : prev.title,
        messages: [
          ...prev.messages.filter((m) => !String(m.id).startsWith("temp-")),
          { id: `u-${Date.now()}`, role: "user", content },
          { id: res.message_id, role: "assistant", content: res.assistant_message },
        ],
      }));
    } catch (err) {
      setError(extractErrorMessage(err, "The assistant is unavailable right now -- check your GROQ_API_KEY / connection."));
      // Roll back the optimistic message on failure.
      setChat((prev) => ({
        ...prev,
        messages: prev.messages.filter((m) => !String(m.id).startsWith("temp-")),
      }));
    } finally {
      setSending(false);
    }
  }

  if (!chat) {
    return (
      <div className="page">
        <PageHeader title="Loading" back />
        <ErrorBanner message={error} />
        {!error && <Loading />}
      </div>
    );
  }

  return (
    <div className="page" style={{ paddingBottom: "calc(var(--nav-height) + 90px)" }}>
      <PageHeader title={chat.title} back />

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {chat.messages.length === 0 && (
          <div className="empty-state">
            <p>Ask about workouts, nutrition, or fitness advice!</p>
          </div>
        )}
        {chat.messages.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} />
        ))}
        {sending && <MessageBubble role="assistant" content="..." pending />}
        <div ref={bottomRef} />
      </div>

      <ErrorBanner message={error} />

      <form onSubmit={handleSend} style={composerStyle}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about workouts, nutrition, or fitness advice..."
          disabled={sending}
        />
        <button className="btn btn-primary" type="submit" disabled={sending || !input.trim()} style={{ padding: "11px 16px" }}>
          →
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ role, content, pending }) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start" }}>
      <div
        style={{
          maxWidth: "82%",
          padding: "10px 14px",
          borderRadius: 14,
          background: isUser ? "var(--chili)" : "var(--bg-card)",
          color: isUser ? "#fff" : "var(--text)",
          fontSize: 14,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
          opacity: pending ? 0.6 : 1,
        }}
      >
        {content}
      </div>
    </div>
  );
}

const composerStyle = {
  position: "fixed",
  bottom: "var(--nav-height)",
  left: "50%",
  transform: "translateX(-50%)",
  width: "100%",
  maxWidth: "var(--max-width)",
  display: "flex",
  gap: 8,
  padding: "10px 16px",
  background: "var(--bg)",
  borderTop: "1px solid var(--border-soft)",
};
