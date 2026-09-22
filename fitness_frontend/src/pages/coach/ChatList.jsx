import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import { listChats, createChat, deleteChat } from "../../api/coach";

const CHATS_PAGE_SIZE = 6;

export default function ChatList() {
  const navigate = useNavigate();
  const showToast = useToast();
  const [chats, setChats] = useState(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null); // { id, title } | null
  const [visibleCount, setVisibleCount] = useState(CHATS_PAGE_SIZE);

  useEffect(() => {
    listChats().then(setChats).catch((err) => setError(extractErrorMessage(err)));
  }, []);

  async function handleNewChat() {
    setCreating(true);
    try {
      const chat = await createChat();
      navigate(`/coach/${chat.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function confirmDeleteChat() {
    const { id } = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteChat(id);
      setChats((cs) => cs.filter((c) => c.id !== id));
      showToast("Chat deleted", "success");
    } catch (err) {
      showToast(extractErrorMessage(err), "error");
    }
  }

  const visibleChats = chats ? chats.slice(0, visibleCount) : [];

  return (
    <div className="page">
      <PageHeader title="Fitness Assistant" subtitle="Chat for explanations and recommendations" />
      <ErrorBanner message={error} />

      <button className="btn btn-primary chat-new-button" onClick={handleNewChat} disabled={creating}>
        {creating ? "Starting..." : "+ New Chat"}
      </button>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
          <h3>Previous Chats</h3>
          <span style={{ fontSize: 12, color: "var(--text-faint)" }}>{chats ? `${chats.length} chats` : ""}</span>
        </div>

        {chats === null && <Loading />}
        {chats?.length === 0 && (
          <EmptyState title="No chats yet" eyebrow="Start a new chat to get personalized fitness recommendations." />
        )}

        <div className="chat-list-grid">
        {visibleChats.map((c) => (
          <div key={c.id} className="card card-tab" style={{ marginBottom: 10, cursor: "pointer" }} onClick={() => navigate(`/coach/${c.id}`)}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <p style={{ fontWeight: 600 }}>{c.title}</p>
              <button className="button btn-ghost"
                onClick={(e) => { e.stopPropagation(); setPendingDelete({ id: c.id, title: c.title }); }}
                style={{ background: "none", border: "none", color: "var(--chili)", fontSize: 12 }}
              >
                Delete
              </button>
            </div>
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{new Date(c.updated_at).toLocaleString()}</p>
          </div>
        ))}
        </div>

        {chats?.length > visibleCount && (
          <button
            className="btn btn-secondary"
            style={{ width: "100%", marginTop: 4 }}
            onClick={() => setVisibleCount((c) => c + CHATS_PAGE_SIZE)}
          >
            Load More ({chats.length - visibleCount} left)
          </button>
        )}
      </div>

      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete chat"
        message={pendingDelete ? `Delete "${pendingDelete.title}"? This can't be undone.` : ""}
        confirmLabel="Delete"
        onConfirm={confirmDeleteChat}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}