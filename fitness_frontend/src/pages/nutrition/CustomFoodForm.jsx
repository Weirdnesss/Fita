import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import ConfirmDialog from "../../components/ConfirmDialog";
import { ErrorBanner, extractErrorMessage } from "../../components/Status";
import { useToast } from "../../context/ToastContext";
import { createCustomFood, updateCustomFood, deleteCustomFood } from "../../api/nutrition";
import { CATEGORIES } from "./foodCategories";
import Pinned from "../../components/Pinned";

// Mirror nutrition.serializers.CustomFoodSerializer on the backend, so a
// mistake is caught here instead of after a round trip.
const MAX_CALORIE_MISMATCH = 0.4;
const MIN_CALORIES_TO_CHECK = 50;

const emptyToZero = (v) => (v === "" || v === null || v === undefined ? 0 : Number(v));

function fromFood(food) {
  return {
    name: food.name,
    category: food.category,
    serving_description: food.serving_description,
    serving_size_g: String(food.serving_size_g),
    calories: String(food.calories),
    protein_g: String(food.protein_g),
    carbs_g: String(food.carbs_g),
    fat_g: String(food.fat_g),
  };
}

/**
 * Add (or edit) a food of your own, for anything missing from the database.
 * Route: /nutrition/foods/custom. Arrives with location.state:
 *   { date, mealType, editingEntryId, editingMealType }  -- passed straight back to the search page
 *   { name }  -- optional prefill from what the user searched for
 *   { food }  -- present when editing an existing custom food
 */
export default function CustomFoodForm() {
  const navigate = useNavigate();
  const location = useLocation();
  const showToast = useToast();
  const { name: prefillName, food: editingFood, ...context } = location.state || {};
  const isEditing = !!editingFood;

  const [form, setForm] = useState(
    editingFood
      ? fromFood(editingFood)
      : {
          name: prefillName || "",
          category: "",
          serving_description: "",
          serving_size_g: "",
          calories: "",
          protein_g: "",
          carbs_g: "",
          fat_g: "",
        }
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const calories = form.calories === "" ? null : Number(form.calories);
  const protein = emptyToZero(form.protein_g);
  const carbs = emptyToZero(form.carbs_g);
  const fat = emptyToZero(form.fat_g);
  const impliedCalories = Math.round(protein * 4 + carbs * 4 + fat * 9);
  const anyMacro = form.protein_g !== "" || form.carbs_g !== "" || form.fat_g !== "";

  const mismatch =
    calories !== null &&
    calories >= MIN_CALORIES_TO_CHECK &&
    Math.abs(impliedCalories - calories) / calories > MAX_CALORIE_MISMATCH;

  const sizeG = Number(form.serving_size_g);
  const problem = (() => {
    if (!form.name.trim()) return "Enter a name.";
    if (!form.category) return "Choose a category.";
    if (!form.serving_description.trim()) return "Describe the serving, for example \"1 pack (60 g)\".";
    if (!(sizeG >= 1 && sizeG <= 2000)) return "Serving size must be between 1 and 2000 grams.";
    if (calories === null || !(calories >= 0 && calories <= 3000)) return "Calories must be between 0 and 3000 for one serving.";
    for (const v of [protein, carbs, fat]) {
      if (!(v >= 0 && v <= 500)) return "Protein, carbs and fat must be between 0 and 500 grams.";
    }
    if (mismatch) {
      return `These numbers don't add up: protein, carbs and fat come to about ${impliedCalories} kcal, but you entered ${Math.round(calories)}. Check the serving size and the numbers on the label.`;
    }
    return "";
  })();

  function goBackToSearch(extraState = {}) {
    navigate("/nutrition/search", { replace: true, state: { ...context, ...extraState } });
  }

  async function handleSave() {
    if (problem) return;
    setSaving(true);
    setError("");
    const payload = {
      name: form.name.trim(),
      category: form.category,
      serving_description: form.serving_description.trim(),
      serving_size_g: sizeG,
      calories,
      protein_g: protein,
      carbs_g: carbs,
      fat_g: fat,
    };
    try {
      const saved = isEditing ? await updateCustomFood(editingFood.id, payload) : await createCustomFood(payload);
      showToast(isEditing ? "Food updated" : `Saved ${saved.name}`, "success");
      // Straight on to the amount/meal screen, so adding it to the log is one more tap.
      goBackToSearch({ openFood: saved });
    } catch (err) {
      setError(extractErrorMessage(err));
      setSaving(false);
    }
  }

  async function handleDelete() {
    setConfirmDelete(false);
    setSaving(true);
    setError("");
    try {
      await deleteCustomFood(editingFood.id);
      showToast("Food deleted", "success");
      goBackToSearch();
    } catch (err) {
      setError(extractErrorMessage(err)); // 409: already in your log
      setSaving(false);
    }
  }

  return (
    <div className="page food-detail">
      <PageHeader
        title={isEditing ? "Edit Food" : "Add Your Own Food"}
        subtitle={isEditing ? undefined : "Only you can see foods you add."}
        back
      />

      <div>
        <label>Food name</label>
        <input
          autoFocus={!isEditing}
          value={form.name}
          maxLength={200}
          onChange={set("name")}
          placeholder="e.g. Lucky Me Pancit Canton"
        />
      </div>

      <div>
        <label>Category</label>
        <select value={form.category} onChange={set("category")}>
          <option value="">Choose a category</option>
          {CATEGORIES.map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
        <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 4 }}>
          Used for browsing and for meal ideas.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
        <div>
          <label>Serving</label>
          <input
            value={form.serving_description}
            maxLength={100}
            onChange={set("serving_description")}
            placeholder='e.g. 1 pack (60 g), or 100g'
          />
        </div>
        <div>
          <label>Grams</label>
          <input type="number" inputMode="decimal" min={1} max={2000} step="any" value={form.serving_size_g} onChange={set("serving_size_g")} />
        </div>
      </div>
      <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: -8 }}>
        Enter the values below for exactly this serving, as printed on the label. Tip: use "100g" with 100 grams to log by weight.
      </p>

      <div className="card">
        <p className="eyebrow" style={{ marginBottom: 8 }}>Nutrition per serving</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
          <NumberField label="Calories (kcal)" value={form.calories} onChange={set("calories")} />
          <NumberField label="Protein (g)" value={form.protein_g} onChange={set("protein_g")} placeholder="0" />
          <NumberField label="Carbs (g)" value={form.carbs_g} onChange={set("carbs_g")} placeholder="0" />
          <NumberField label="Fat (g)" value={form.fat_g} onChange={set("fat_g")} placeholder="0" />
        </div>
        {anyMacro && (
          <p style={{ fontSize: 12, color: mismatch ? "var(--chili)" : "var(--text-faint)", marginTop: 10 }}>
            Protein, carbs and fat add up to about {impliedCalories} kcal.
          </p>
        )}
      </div>

      <Pinned bottom>
        {problem && (form.name || form.calories) && (
          <p style={{ fontSize: 12, color: mismatch ? "var(--chili)" : "var(--text-faint)" }}>{problem}</p>
        )}
        <ErrorBanner message={error} />

        <button className="btn btn-primary btn-block" onClick={handleSave} disabled={saving || !!problem}>
          {saving ? "Saving..." : isEditing ? "Save Changes" : "Save Food"}
        </button>
      </Pinned>

      {isEditing && (
        <button className="btn-ghost" style={{ fontSize: 13 }} onClick={() => setConfirmDelete(true)} disabled={saving}>
          Delete this food
        </button>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this food?"
        message={`"${editingFood?.name}" will be removed from your foods. If it's already in your log, it can't be deleted.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}

function NumberField({ label, value, onChange, placeholder }) {
  return (
    <div>
      <label>{label}</label>
      <input type="number" inputMode="decimal" min={0} step="any" value={value} onChange={onChange} placeholder={placeholder} />
    </div>
  );
}
