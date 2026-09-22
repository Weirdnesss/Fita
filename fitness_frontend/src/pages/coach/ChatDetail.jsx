import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getChat, sendMessage } from "../../api/coach";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ChatDetail() {
  const { id } = useParams();
  const [chat, setChat] = useState(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);
  const [keyboardOffset, setKeyboardOffset] = useState(0);

  useEffect(() => {
    load();
  }, [id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat?.messages?.length]);

  // position: fixed alone isn't reliable once the on-screen keyboard opens --
  // most mobile browsers don't resize the layout viewport, so a fixed
  // element can end up hidden behind the keyboard or floating mid-screen.
  // window.visualViewport tracks the actually-visible area, so we can
  // measure how much of the screen the keyboard is covering and shift the
  // composer up to sit right above it. Browsers without visualViewport
  // support (rare) just keep the previous fixed-to-bottom-nav behavior.
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    function handleResize() {
      const occluded = window.innerHeight - vv.height - vv.offsetTop;
      setKeyboardOffset(Math.max(0, Math.round(occluded)));
    }

    vv.addEventListener("resize", handleResize);
    vv.addEventListener("scroll", handleResize);
    handleResize();

    return () => {
      vv.removeEventListener("resize", handleResize);
      vv.removeEventListener("scroll", handleResize);
    };
  }, []);

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
      setError(extractErrorMessage(err, "Couldn't reach the assistant -- check your connection and try again."));
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
    <div className="page chat-detail" style={{ paddingBottom: "calc(var(--nav-height) + 90px)" }}>
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

      <form
        onSubmit={handleSend}
        className="chat-composer"
        style={{ ...composerStyle, bottom: keyboardOffset > 0 ? keyboardOffset : composerStyle.bottom }}
      >
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
        className={isUser ? undefined : "chat-markdown"}
        style={{
          maxWidth: "82%",
          padding: "10px 14px",
          borderRadius: 14,
          background: isUser ? "var(--chili)" : "var(--bg-card)",
          color: isUser ? "#fff" : "var(--text)",
          fontSize: 14,
          lineHeight: 1.5,
          whiteSpace: isUser ? "pre-wrap" : "normal",
          opacity: pending ? 0.6 : 1,
        }}
      >
        {isUser ? content : <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>}
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
  border: "1px solid var(--border-soft)",
};