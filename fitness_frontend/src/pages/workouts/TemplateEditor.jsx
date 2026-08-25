import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { createTemplate, getTemplate, addExerciseToTemplate, searchExercises } from "../../api/workouts";

export default function TemplateEditor() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [template, setTemplate] = useState(null);
  const [title, setTitle] = useState("New Template");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [showSearch, setShowSearch] = useState(false);

  useEffect(() => {
    if (id) {
      getTemplate(id).then((t) => {
        setTemplate(t);
        setTitle(t.title);
      }).catch((err) => setError(extractErrorMessage(err)));
    } else {
      // Create the shell immediately so exercises can be added right away.
      createTemplate({ title: "New Template", kind: searchParams.get("kind") || "main" })
        .then((t) => {
          setTemplate(t);
          navigate(`/workouts/templates/${t.id}`, { replace: true });
        })
        .catch((err) => setError(extractErrorMessage(err)));
    }
  }, [id]);

  async function handleExerciseAdded(updatedTemplate) {
    setTemplate(updatedTemplate);
    setShowSearch(false);
  }

  if (!template) {
    return (
      <div className="page">
        <PageHeader title="Loading" back />
        <ErrorBanner message={error} />
        {!error && <Loading />}
      </div>
    );
  }

  if (showSearch) {
    return (
      <ExerciseSearch
        onAdd={async (wgerExerciseId) => {
          try {
            const updated = await addExerciseToTemplate(template.id, { wgerExerciseId });
            handleExerciseAdded(updated);
          } catch (err) {
            setError(extractErrorMessage(err, "Couldn't add that exercise. Check your connection."));
          }
        }}
        onClose={() => setShowSearch(false)}
      />
    );
  }

  return (
    <div className="page">
      <PageHeader
        title="Edit Routine"
        back
        action={
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => navigate("/workouts")}>
              Save
            </button>
            {template.exercises.length > 0 && (
              <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => navigate(`/workouts/templates/${template.id}/start`)}>
                Start
              </button>
            )}
          </div>
        }
      />
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Enter template title..."
        style={{ fontSize: 18, fontWeight: 600 }}
      />
      <ErrorBanner message={error} />

      <div>
        <h3 style={{ marginBottom: 10 }}>Exercises ({template.exercises.length})</h3>
        {template.exercises.length === 0 && (
          <div className="empty-state">
            <p>No exercises added yet</p>
          </div>
        )}
        {template.exercises.map((ex) => (
          <div key={ex.id} className="card" style={{ marginBottom: 10 }}>
            <p style={{ fontWeight: 600 }}>{ex.exercise_name}</p>
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
              {ex.category_name} {ex.equipment_name ? `· ${ex.equipment_name}` : ""}
            </p>
            <p style={{ fontSize: 13, marginTop: 6 }}>{ex.target_sets} target sets</p>
          </div>
        ))}
        <button className="btn btn-secondary btn-block" onClick={() => setShowSearch(true)}>
          + Add Exercise
        </button>
      </div>
    </div>
  );
}

function ExerciseSearch({ onAdd, onClose }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const r = await searchExercises(query);
        setResults(r);
      } catch (err) {
        setError("Couldn't search exercises. Has the exercise database been synced yet? Run: python manage.py sync_wger_exercises");
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="page">
      <PageHeader title="Add Exercise" back={false} action={<button className="btn-ghost" style={{ background: "none", border: "none" }} onClick={onClose}>Close</button>} />
      <input autoFocus placeholder="Search for an exercise" value={query} onChange={(e) => setQuery(e.target.value)} />
      {loading && <Loading label="Searching" />}
      <ErrorBanner message={error} />
      {!loading && query.length >= 2 && results.length === 0 && !error && (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>No exercises found for "{query}".</p>
      )}
      {results.map((ex) => (
        <div
          key={ex.wger_exercise_id}
          className="card"
          style={{ marginBottom: 8, cursor: "pointer" }}
          onClick={() => onAdd(ex.wger_exercise_id)}
        >
          <p style={{ fontWeight: 600 }}>{ex.name}</p>
          {ex.category && <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{ex.category}</p>}
        </div>
      ))}
    </div>
  );
}
