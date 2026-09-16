import { useEffect, useState } from "react";

import { useNavigate } from "react-router-dom";

import PageHeader from "../../components/PageHeader";

import {
  Loading,
  ErrorBanner,
  EmptyState,
  extractErrorMessage,
} from "../../components/Status";

import ConfirmDialog from "../../components/ConfirmDialog";

import { useToast } from "../../context/ToastContext";

import { listChats, deleteChat } from "../../api/coach";

export default function ChatHistory() {
  const navigate = useNavigate();
  const showToast = useToast();

  const [chats, setChats] = useState(null);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);

  const [currentPage, setCurrentPage] = useState(1);

  const chatsPerPage = 6;

  useEffect(() => {
    listChats()
      .then(setChats)
      .catch((err) => setError(extractErrorMessage(err)));
  }, []);

  useEffect(() => {
    if (!chats) return;

    const totalPages = Math.max(
      1,
      Math.ceil(chats.length / chatsPerPage)
    );

    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [chats, currentPage]);

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

  const totalPages = chats
    ? Math.ceil(chats.length / chatsPerPage)
    : 0;

  const startIndex = (currentPage - 1) * chatsPerPage;

  const paginatedChats = chats
    ? chats.slice(startIndex, startIndex + chatsPerPage)
    : [];

  return (
    <div className="page">
      <PageHeader
        title="Chat History"
        subtitle="View your previous Fitness Assistant conversations"
      />

      <ErrorBanner message={error} />

      {chats === null && <Loading />}

      {chats?.length === 0 && (
        <EmptyState
          title="No chats yet"
          eyebrow="Start a new chat to get personalized fitness recommendations."
        />
      )}

      {chats && chats.length > 0 && (
        <>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 10,
            }}
          >
            <h3>All Chats</h3>

            <span
              style={{
                fontSize: 12,
                color: "var(--text-faint)",
              }}
            >
              {chats.length} chats
            </span>
          </div>

          {chats.length > chatsPerPage && (
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                gap: 12,
                marginBottom: 16,
              }}
            >
              <button
                className="btn btn-secondary"
                onClick={() =>
                  setCurrentPage((p) => Math.max(p - 1, 1))
                }
                disabled={currentPage === 1}
              >
                Previous
              </button>

              <span
                style={{
                  fontSize: 13,
                  color: "var(--text-faint)",
                }}
              >
                Page {currentPage} of {totalPages}
              </span>

              <button
                className="btn btn-secondary"
                onClick={() =>
                  setCurrentPage((p) =>
                    Math.min(p + 1, totalPages)
                  )
                }
                disabled={currentPage === totalPages}
              >
                Next
              </button>
            </div>
          )}

          <div className="chat-list-grid">
            {paginatedChats.map((c) => (
              <div
                key={c.id}
                className="card card-tab"
                style={{
                  marginBottom: 10,
                  cursor: "pointer",
                }}
                onClick={() => navigate(`/coach/${c.id}`)}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <p style={{ fontWeight: 600 }}>{c.title}</p>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setPendingDelete({
                        id: c.id,
                        title: c.title,
                      });
                    }}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--text-faint)",
                      fontSize: 12,
                    }}
                  >
                    Delete
                  </button>
                </div>

                <p
                  style={{
                    fontSize: 12,
                    color: "var(--text-faint)",
                  }}
                >
                  {new Date(c.updated_at).toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        </>
      )}

      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete chat"
        message={
          pendingDelete
            ? `Delete "${pendingDelete.title}"? This can't be undone.`
            : ""
        }
        confirmLabel="Delete"
        onConfirm={confirmDeleteChat}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}