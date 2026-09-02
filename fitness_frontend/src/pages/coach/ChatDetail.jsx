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
    const tempId = `temp-${Date.now()}`;
    setInput("");
    setError("");

    // Optimistic append of the user's message.
    setChat((prev) => ({
      ...prev,
      messages: [...prev.messages, { id: tempId, role: "user", content }],
    }));
    setSending(true);
    try {
      const res = await sendMessage(id, content);
      setChat((prev) => ({
        ...prev,
        title: prev.title === "New Chat" ? content.slice(0, 60) : prev.title,
        messages: [
          // Only replace THIS send's temp message -- a previous failed
          // send may still be sitting in the list (kept, not rolled
          // back, see the catch block below) and must not be wiped out
          // by a later unrelated success.
          ...prev.messages.filter((m) => m.id !== tempId),
          { id: `u-${Date.now()}`, role: "user", content },
          { id: res.message_id, role: "assistant", content: res.assistant_message },
        ],
      }));
    } catch (err) {
      setError(extractErrorMessage(err, "The assistant is unavailable right now -- check your GROQ_API_KEY / connection."));
      // Don't roll back the optimistic message: the backend saves the
      // user's message before attempting the LLM call, so it's genuinely
      // persisted even though generation failed. Hiding it here would
      // just make it silently reappear (with no explanation) next time
      // the chat loads -- instead we leave it visible and let the
      // "last message has no reply" check below flag it consistently,
      // both right now and on a future reload.
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
        {chat.messages.map((m, i) => (
          <MessageBubble
            key={m.id}
            role={m.role}
            content={m.content}
            noReply={!sending && i === chat.messages.length - 1 && m.role === "user"}
          />
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

function MessageBubble({ role, content, pending, noReply }) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: isUser ? "flex-end" : "flex-start" }}>
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
      {noReply && (
        <p style={{ fontSize: 11, color: "var(--chili)", marginTop: 4 }}>
          Didn't get a response -- send another message to try again.
        </p>
      )}
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
