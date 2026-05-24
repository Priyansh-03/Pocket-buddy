import { FormEvent, useCallback, useEffect, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { formatNowIST } from "../lib/istClock";
import { EXTERNAL_AI_EXPORT_PROMPT } from "../prompts/externalExpenseExportPrompt";

type LlmOut = { provider: string; openrouter_http_referer: string | null; server_key_configured: boolean };
type ImportWallet = { id: number; label: string; balance_inr: number };
type ImportRecurring = { item: string; amount_inr: number; cadence: string; note: string };
type ImportExpense = { date: string; description: string; amount_inr: number; category: string };
type ImportData = {
  profile: { salary_day_of_month: number | null; monthly_rent_inr: number | null; daily_budget_inr: number | null; wallets: ImportWallet[] };
  recurring: ImportRecurring[];
  expenses: ImportExpense[];
};

export function SettingsPage() {
  const { token, user, refreshUser } = useAuth();
  const [istNow, setIstNow] = useState(() => formatNowIST());
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  // import state
  const [importJson, setImportJson] = useState("");
  const [importData, setImportData] = useState<ImportData | null>(null);
  const [importErr, setImportErr] = useState<string | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importDone, setImportDone] = useState(false);

  // provider state
  const [llm, setLlm] = useState<LlmOut | null>(null);
  const [provider, setProvider] = useState<"openai" | "openrouter" | "gemini">("openai");
  const [referer, setReferer] = useState("");

  // profile state (always-visible editable fields)
  const [salaryDay, setSalaryDay] = useState("");
  const [rent, setRent] = useState("");
  const [dailyBudget, setDailyBudget] = useState("");
  const [profileMsg, setProfileMsg] = useState<string | null>(null);

  // memory state
  const [foodMenu, setFoodMenu] = useState("");
  const [remember, setRemember] = useState("");

  useEffect(() => {
    const id = window.setInterval(() => setIstNow(formatNowIST()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const loadLlm = useCallback(async () => {
    if (!token) return;
    try {
      const l = await apiFetch<LlmOut>("/users/me/llm", { token, method: "GET" });
      setLlm(l);
      setProvider(l.provider as "openai" | "openrouter" | "gemini");
      setReferer(l.openrouter_http_referer || "");
    } catch { /* ignore */ }
  }, [token]);

  useEffect(() => { void loadLlm(); }, [loadLlm]);

  useEffect(() => {
    if (!user) return;
    setSalaryDay(user.salary_day != null ? String(user.salary_day) : "");
    setRent(user.monthly_rent_inr != null ? String(user.monthly_rent_inr) : "");
    setDailyBudget(user.daily_budget_inr != null ? String(user.daily_budget_inr) : "");
    setFoodMenu(user.food_menu_text ?? "");
    setRemember(user.remember_text ?? "");
  }, [user]);

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(EXTERNAL_AI_EXPORT_PROMPT);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setErr("Clipboard blocked — manually select and copy the text below.");
    }
  }

  function parseJson() {
    setImportErr(null);
    setImportDone(false);
    try {
      const raw = JSON.parse(importJson.trim()) as ImportData;
      const p = raw.profile ?? {};
      setImportData({
        profile: {
          salary_day_of_month: (p as ImportData["profile"]).salary_day_of_month ?? null,
          monthly_rent_inr: (p as ImportData["profile"]).monthly_rent_inr ?? null,
          daily_budget_inr: (p as ImportData["profile"]).daily_budget_inr ?? null,
          wallets: ((p as ImportData["profile"]).wallets ?? []).map((w) => ({ id: Number(w.id) || 1, label: w.label ?? "", balance_inr: Number(w.balance_inr) || 0 })),
        },
        recurring: (raw.recurring ?? []).map((r) => ({ item: r.item ?? "", amount_inr: Number(r.amount_inr) || 0, cadence: r.cadence ?? "monthly", note: r.note ?? "" })),
        expenses: (raw.expenses ?? []).map((e) => ({ date: e.date ?? "unknown", description: e.description ?? "", amount_inr: Number(e.amount_inr) || 0, category: e.category ?? "misc" })),
      });
    } catch {
      setImportErr("Invalid JSON — paste the raw JSON output from ChatGPT.");
    }
  }

  function updateWallet(idx: number, field: keyof ImportWallet, value: string) {
    if (!importData) return;
    setImportData({ ...importData, profile: { ...importData.profile, wallets: importData.profile.wallets.map((w, i) => i === idx ? { ...w, [field]: field === "balance_inr" || field === "id" ? Number(value) || 0 : value } : w) } });
  }
  function updateRecurring(idx: number, field: keyof ImportRecurring, value: string) {
    if (!importData) return;
    setImportData({ ...importData, recurring: importData.recurring.map((r, i) => i === idx ? { ...r, [field]: field === "amount_inr" ? Number(value) || 0 : value } : r) });
  }
  function updateExpense(idx: number, field: keyof ImportExpense, value: string) {
    if (!importData) return;
    setImportData({ ...importData, expenses: importData.expenses.map((e, i) => i === idx ? { ...e, [field]: field === "amount_inr" ? Number(value) || 0 : value } : e) });
  }

  async function doImport() {
    if (!importData || !token) return;
    setImportBusy(true);
    setImportErr(null);
    try {
      await apiFetch("/users/me/import", { method: "POST", token, body: JSON.stringify(importData) });
      await refreshUser();
      setImportDone(true);
      setImportData(null);
      setImportJson("");
    } catch (e) {
      setImportErr(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImportBusy(false);
    }
  }

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true); setProfileMsg(null); setErr(null);
    try {
      const body: Record<string, unknown> = {
        salary_day: salaryDay.trim() ? Number(salaryDay) : null,
        monthly_rent_inr: rent.trim() ? rent.trim() : null,
        daily_budget_inr: dailyBudget.trim() ? dailyBudget.trim() : null,
      };
      await apiFetch("/users/me", { method: "PATCH", token, body: JSON.stringify(body) });
      await refreshUser();
      setProfileMsg("Saved.");
      setTimeout(() => setProfileMsg(null), 2000);
    } catch (ex) { setErr(ex instanceof Error ? ex.message : "Save failed"); }
    finally { setBusy(false); }
  }

  async function saveLlm(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      await apiFetch("/users/me/llm", { method: "PUT", token, body: JSON.stringify({ provider, openrouter_http_referer: referer || null }) });
      await loadLlm();
      await refreshUser();
      setMsg("Provider saved.");
    } catch (ex) { setErr(ex instanceof Error ? ex.message : "Save failed"); }
    finally { setBusy(false); }
  }

  async function saveMemory(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      await apiFetch("/users/me", { method: "PATCH", token, body: JSON.stringify({ food_menu_text: foodMenu.trim() || null, remember_text: remember.trim() || null }) });
      await refreshUser();
      setMsg("Memory saved.");
    } catch (ex) { setErr(ex instanceof Error ? ex.message : "Save failed"); }
    finally { setBusy(false); }
  }

  const keyHint = provider === "openai" ? "OPENAI_API_KEY" : provider === "openrouter" ? "OPENROUTER_API_KEY" : "GEMINI_API_KEY";

  return (
    <div className="shell narrow">
      <header className="topbar">
        <div>
          <h1 className="title">Settings</h1>
          <p className="muted small ist-clock">{istNow}</p>
        </div>
        <Link className="btn ghost" to="/">← Chat</Link>
      </header>

      {msg && <div className="banner ok">{msg}</div>}
      {err && <div className="banner error">{err}</div>}

      {/* ── Budget & Profile ── */}
      <section className="card stack">
        <h2>Budget &amp; Profile</h2>
        <form className="stack" onSubmit={(e) => void saveProfile(e)}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
            <label className="field">
              <span>Daily budget (₹)</span>
              <input inputMode="decimal" value={dailyBudget} onChange={(e) => setDailyBudget(e.target.value)} placeholder="e.g. 500" />
            </label>
            <label className="field">
              <span>Monthly rent (₹)</span>
              <input inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} placeholder="e.g. 15000" />
            </label>
            <label className="field">
              <span>Salary day (1–31)</span>
              <input inputMode="numeric" value={salaryDay} onChange={(e) => setSalaryDay(e.target.value)} placeholder="e.g. 5" />
            </label>
          </div>

          {/* Wallets inline */}
          <div>
            <p className="muted small" style={{ marginBottom: "0.4rem" }}>Wallets</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "0.5rem" }}>
              {[1,2,3,4,5].map((wid) => {
                const val = user?.[`wallet_${wid}_inr` as keyof typeof user];
                if (val == null) return null;
                const loanKey = `wallet_${wid}_loan_inr` as keyof typeof user;
                const loan = user?.[loanKey];
                const loanNum = loan != null ? Number(loan) : null;
                return (
                  <div key={wid} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <label className="field" style={{ margin: 0 }}>
                      <span>Wallet {wid} (₹)</span>
                      <input
                        inputMode="decimal"
                        defaultValue={String(val)}
                        onBlur={async (e) => {
                          const clean = e.target.value.trim().replace(/,/g, "");
                          if (!clean || !token) return;
                          await apiFetch("/users/me", { method: "PATCH", token, body: JSON.stringify({ [`wallet_${wid}_inr`]: clean, active_wallet_id: wid }) });
                          await refreshUser();
                        }}
                      />
                    </label>
                    {wid !== 1 && loanNum != null && (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem" }}>
                        <span style={{ color: loanNum < 0 ? "#ef4444" : "#22c55e", fontWeight: 600 }}>
                          Loan: {loanNum < 0 ? "" : "+"}{loanNum.toLocaleString("en-IN")}
                        </span>
                        <button
                          type="button"
                          className="btn ghost"
                          style={{ padding: "0.1rem 0.5rem", fontSize: "0.75rem" }}
                          onClick={async () => {
                            if (!token) return;
                            await apiFetch("/users/me", { method: "PATCH", token, body: JSON.stringify({ clear_loan_wallet_ids: [wid] }) });
                            await refreshUser();
                          }}
                        >
                          Clear loan
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="row" style={{ alignItems: "center", gap: "0.75rem" }}>
            <button className="btn primary" type="submit" disabled={busy}>Save</button>
            {profileMsg && <span className="muted small">{profileMsg}</span>}
          </div>
        </form>
      </section>

      {/* ── STEP 1: Copy prompt ── */}
      <section className="card stack">
        <h2>Step 1 — Copy this prompt into ChatGPT / Claude</h2>
        <p className="muted small">Paste it into the AI where you've discussed your finances. It will output a JSON block. Then paste that JSON in Step 2.</p>
        <button type="button" className="btn primary" style={{ alignSelf: "flex-start" }} onClick={() => void copyPrompt()}>
          {copied ? "Copied!" : "Copy prompt"}
        </button>
        <textarea
          readOnly
          className="mono-readonly"
          rows={14}
          value={EXTERNAL_AI_EXPORT_PROMPT}
          style={{ fontSize: "0.78rem", fontFamily: "monospace" }}
        />
      </section>

      {/* ── STEP 2: Paste JSON → edit → import ── */}
      <section className="card stack">
        <h2>Step 2 — Paste JSON, edit, import</h2>
        {importDone && <div className="banner ok">Imported! Wallets and expenses updated.</div>}
        {importErr && <div className="banner error">{importErr}</div>}

        {!importData ? (
          <div className="stack">
            <textarea
              className="mono-readonly"
              rows={8}
              style={{ fontFamily: "monospace", fontSize: "0.78rem" }}
              placeholder={'Paste the JSON from ChatGPT here…\n{\n  "profile": { ... },\n  "recurring": [...],\n  "expenses": [...]\n}'}
              value={importJson}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setImportJson(e.target.value)}
            />
            <button className="btn primary" type="button" style={{ alignSelf: "flex-start" }} onClick={parseJson} disabled={!importJson.trim()}>
              Parse JSON
            </button>
          </div>
        ) : (
          <div className="stack">
            <h3 style={{ margin: 0 }}>Profile</h3>
            <table className="import-table">
              <tbody>
                <tr><td>Salary day</td><td><input type="number" min={1} max={31} value={importData.profile.salary_day_of_month ?? ""} onChange={(e) => setImportData({ ...importData, profile: { ...importData.profile, salary_day_of_month: e.target.value ? Number(e.target.value) : null } })} placeholder="null" /></td></tr>
                <tr><td>Monthly rent (₹)</td><td><input type="number" value={importData.profile.monthly_rent_inr ?? ""} onChange={(e) => setImportData({ ...importData, profile: { ...importData.profile, monthly_rent_inr: e.target.value ? Number(e.target.value) : null } })} placeholder="null" /></td></tr>
                <tr><td>Daily budget (₹)</td><td><input type="number" value={importData.profile.daily_budget_inr ?? ""} onChange={(e) => setImportData({ ...importData, profile: { ...importData.profile, daily_budget_inr: e.target.value ? Number(e.target.value) : null } })} placeholder="null" /></td></tr>
              </tbody>
            </table>

            <h3 style={{ margin: 0 }}>Wallets ({importData.profile.wallets.length})</h3>
            <table className="import-table">
              <thead><tr><th>ID</th><th>Label</th><th>Balance (₹)</th></tr></thead>
              <tbody>
                {importData.profile.wallets.map((w, i) => (
                  <tr key={i}>
                    <td><input type="number" min={1} max={5} value={w.id} onChange={(e) => updateWallet(i, "id", e.target.value)} /></td>
                    <td><input value={w.label} onChange={(e) => updateWallet(i, "label", e.target.value)} /></td>
                    <td><input type="number" value={w.balance_inr} onChange={(e) => updateWallet(i, "balance_inr", e.target.value)} /></td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h3 style={{ margin: 0 }}>Recurring ({importData.recurring.length})</h3>
            <table className="import-table">
              <thead><tr><th>Item</th><th>₹</th><th>Cadence</th><th>Note</th><th></th></tr></thead>
              <tbody>
                {importData.recurring.map((r, i) => (
                  <tr key={i}>
                    <td><input value={r.item} onChange={(e) => updateRecurring(i, "item", e.target.value)} /></td>
                    <td><input type="number" value={r.amount_inr} onChange={(e) => updateRecurring(i, "amount_inr", e.target.value)} /></td>
                    <td><input value={r.cadence} onChange={(e) => updateRecurring(i, "cadence", e.target.value)} /></td>
                    <td><input value={r.note} onChange={(e) => updateRecurring(i, "note", e.target.value)} /></td>
                    <td><button type="button" className="btn ghost" style={{ padding: "0 0.4rem" }} onClick={() => setImportData({ ...importData, recurring: importData.recurring.filter((_, j) => j !== i) })}>✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h3 style={{ margin: 0 }}>Expenses ({importData.expenses.length})</h3>
            <table className="import-table">
              <thead><tr><th>Date</th><th>Description</th><th>₹</th><th>Category</th><th></th></tr></thead>
              <tbody>
                {importData.expenses.map((e, i) => (
                  <tr key={i}>
                    <td><input value={e.date} onChange={(ev) => updateExpense(i, "date", ev.target.value)} /></td>
                    <td><input value={e.description} onChange={(ev) => updateExpense(i, "description", ev.target.value)} /></td>
                    <td><input type="number" value={e.amount_inr} onChange={(ev) => updateExpense(i, "amount_inr", ev.target.value)} /></td>
                    <td><input value={e.category} onChange={(ev) => updateExpense(i, "category", ev.target.value)} /></td>
                    <td><button type="button" className="btn ghost" style={{ padding: "0 0.4rem" }} onClick={() => setImportData({ ...importData, expenses: importData.expenses.filter((_, j) => j !== i) })}>✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="row" style={{ gap: "0.5rem" }}>
              <button className="btn primary" type="button" onClick={() => void doImport()} disabled={importBusy}>
                {importBusy ? "Importing…" : "Import to app"}
              </button>
              <button className="btn ghost" type="button" onClick={() => { setImportData(null); setImportDone(false); setImportErr(null); }}>
                Reset
              </button>
            </div>
          </div>
        )}
      </section>

      {/* ── AI Provider ── */}
      <section className="card stack">
        <h2>AI provider</h2>
        <form className="stack" onSubmit={(e) => void saveLlm(e)}>
          <div className="row wrap">
            {(["openai", "openrouter", "gemini"] as const).map((p) => (
              <label key={p} className="pill">
                <input type="radio" name="prov" checked={provider === p} onChange={() => setProvider(p)} />
                {p}
              </label>
            ))}
          </div>
          <p className="muted small">
            Key status:{" "}
            {!llm ? "loading…" : llm.server_key_configured
              ? <strong className="text-ok">OK — {keyHint} set</strong>
              : <strong className="text-bad">missing — set {keyHint} in apps/api/.env and restart</strong>}
          </p>
          {provider === "openrouter" && (
            <label className="field">
              <span>HTTP-Referer</span>
              <input value={referer} onChange={(e) => setReferer(e.target.value)} placeholder="https://your-site.example" />
            </label>
          )}
          <button className="btn primary" type="submit" disabled={busy} style={{ alignSelf: "flex-start" }}>Save provider</button>
        </form>
      </section>

      {/* ── Memory ── */}
      <section className="card stack">
        <h2>Assistant memory</h2>
        <form className="stack" onSubmit={(e) => void saveMemory(e)}>
          <label className="field">
            <span>Food menu (items + prices — shown to assistant every reply)</span>
            <textarea className="input-grow" rows={6} maxLength={50_000} value={foodMenu} onChange={(e) => setFoodMenu(e.target.value)} placeholder="e.g. Masala dosa ₹90, idli ₹40…" />
          </label>
          <label className="field">
            <span>Always remember</span>
            <textarea className="input-grow" rows={4} maxLength={50_000} value={remember} onChange={(e) => setRemember(e.target.value)} placeholder="Notes the assistant should always keep in mind…" />
          </label>
          <button className="btn primary" type="submit" disabled={busy} style={{ alignSelf: "flex-start" }}>Save memory</button>
        </form>
      </section>
    </div>
  );
}
