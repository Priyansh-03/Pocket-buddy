import { FormEvent, useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { formatNowIST } from "../lib/istClock";
import { EXTERNAL_AI_EXPORT_PROMPT } from "../prompts/externalExpenseExportPrompt";

const PROFILE_CHAT_SESSION = "survival_money_profile_session";

const MONEY_ONBOARDING_INTRO =
  "Money & savings — yahan Shift+Enter se nayi line, Enter se bhejo.\n\n" +
  "Upar Copy prompt wala text ChatGPT ya kisi aur AI mein paste karo jahan tumne spends discuss ki hon; woh BEGIN_EXPORT … END_EXPORT block dega. Poora block yahan paste karo — main PROFILE merge aur clear INR par expenses add kar sakti hoon.\n\n" +
  "Ya seedha likho: salary kab (mahine ki 1–31), rent / fixed, rough bank / UPI cash, goals / EMI. Main chat mein bonus / refund bata kar estimated cash bhi update ho sakta hai.";

type LlmOut = {
  provider: string;
  openrouter_http_referer: string | null;
  server_key_configured: boolean;
};

type ChatMsg = { role: "user" | "assistant"; content: string };

function bubbleText(s: string) {
  return s.replace(/\*\*/g, "");
}

export function SettingsPage() {
  const { token, user, refreshUser } = useAuth();
  const [llm, setLlm] = useState<LlmOut | null>(null);
  const [provider, setProvider] = useState<"openai" | "openrouter" | "gemini">("openai");
  const [referer, setReferer] = useState("");
  const [salaryDay, setSalaryDay] = useState<string>("");
  const [rent, setRent] = useState("");
  const [cash, setCash] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [moneyMsgs, setMoneyMsgs] = useState<ChatMsg[]>([{ role: "assistant", content: MONEY_ONBOARDING_INTRO }]);
  const [moneySessionId, setMoneySessionId] = useState<string | null>(() => localStorage.getItem(PROFILE_CHAT_SESSION));
  const [moneyInput, setMoneyInput] = useState("");
  const [moneySending, setMoneySending] = useState(false);
  const [promptCopied, setPromptCopied] = useState(false);
  const [istNow, setIstNow] = useState(() => formatNowIST());
  const moneyBottomRef = useRef<HTMLDivElement | null>(null);

  const loadLlm = useCallback(async () => {
    if (!token) return;
    try {
      const l = await apiFetch<LlmOut>("/users/me/llm", { token, method: "GET" });
      setLlm(l);
      setProvider(l.provider as "openai" | "openrouter" | "gemini");
      setReferer(l.openrouter_http_referer || "");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load AI settings");
    }
  }, [token]);

  useEffect(() => {
    void loadLlm();
  }, [loadLlm]);

  useEffect(() => {
    if (!user) return;
    setSalaryDay(user.salary_day != null ? String(user.salary_day) : "");
    setRent(user.monthly_rent_inr != null ? String(user.monthly_rent_inr) : "");
    setCash(user.estimated_cash_inr != null ? String(user.estimated_cash_inr) : "");
  }, [user]);

  useEffect(() => {
    moneyBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [moneyMsgs, moneySending]);

  useEffect(() => {
    const id = window.setInterval(() => setIstNow(formatNowIST()), 1000);
    return () => window.clearInterval(id);
  }, []);

  async function copyExternalPrompt() {
    try {
      await navigator.clipboard.writeText(EXTERNAL_AI_EXPORT_PROMPT);
      setPromptCopied(true);
      window.setTimeout(() => setPromptCopied(false), 2500);
      setErr(null);
    } catch {
      setErr("Clipboard blocked — neeche box se manually select karke copy karo.");
    }
  }

  async function submitMoneyChat() {
    const t = moneyInput.trim();
    if (!t || !token || !llm?.server_key_configured || moneySending) return;
    setMoneyInput("");
    setErr(null);
    setMoneySending(true);
    setMoneyMsgs((m) => [...m, { role: "user", content: t }]);
    try {
      const body: { message: string; session_id?: string } = { message: t };
      if (moneySessionId) body.session_id = moneySessionId;
      const res = await apiFetch<{ session_id: string; reply: string }>("/chat", {
        method: "POST",
        token,
        body: JSON.stringify(body),
      });
      setMoneySessionId(res.session_id);
      localStorage.setItem(PROFILE_CHAT_SESSION, res.session_id);
      setMoneyMsgs((m) => [...m, { role: "assistant", content: res.reply }]);
      await refreshUser();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Message failed");
      setMoneyMsgs((m) => [...m, { role: "assistant", content: "Could not reach the assistant — check API key / network." }]);
    } finally {
      setMoneySending(false);
    }
  }

  async function sendMoneyChat(e: FormEvent) {
    e.preventDefault();
    await submitMoneyChat();
  }

  function onMoneyKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.shiftKey) return;
    e.preventDefault();
    void submitMoneyChat();
  }

  function resetMoneyChat() {
    localStorage.removeItem(PROFILE_CHAT_SESSION);
    setMoneySessionId(null);
    setMoneyMsgs([{ role: "assistant", content: MONEY_ONBOARDING_INTRO }]);
  }

  async function saveLlm(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await apiFetch<LlmOut>("/users/me/llm", {
        method: "PUT",
        token,
        body: JSON.stringify({
          provider,
          openrouter_http_referer: referer || null,
        }),
      });
      const fresh = await apiFetch<LlmOut>("/users/me/llm", { token, method: "GET" });
      setLlm(fresh);
      setMsg(
        fresh.server_key_configured
          ? "Provider save ho gaya. LLM key apps/api/.env se aa rahi hai."
          : "Provider save ho gaya — lekin is provider ke liye server .env mein abhi key nahi mili (neeche dekho).",
      );
      await refreshUser();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setErr(null);
    setMsg(null);

    const body: Record<string, unknown> = {};
    const sdRaw = salaryDay.trim();
    if (sdRaw) {
      if (!/^\d{1,2}$/.test(sdRaw)) {
        setErr("Salary day: sirf 1–31 tak ki puri sankhya (mahine ki date), bina dash/comma.");
        return;
      }
      const n = parseInt(sdRaw, 10);
      if (n < 1 || n > 31) {
        setErr("Salary day 1 se 31 ke beech hona chahiye (kis din salary aati hai).");
        return;
      }
      body.salary_day = n;
    } else {
      body.salary_day = null;
    }
    if (rent.trim()) body.monthly_rent_inr = rent;
    else body.monthly_rent_inr = null;
    if (cash.trim()) body.estimated_cash_inr = cash;
    else body.estimated_cash_inr = null;

    setBusy(true);
    try {
      await apiFetch("/users/me", { method: "PATCH", token, body: JSON.stringify(body) });
      await refreshUser();
      setMsg("Numbers manually save ho gaye.");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Profile save failed");
    } finally {
      setBusy(false);
    }
  }

  const keyHint =
    provider === "openai"
      ? "OPENAI_API_KEY (ya OUTSPARK_OPENAI_STAGING_API_KEY)"
      : provider === "openrouter"
        ? "OPENROUTER_API_KEY"
        : "GEMINI_API_KEY";

  return (
    <div className="shell narrow">
      <header className="topbar">
        <div>
          <h1 className="title">Settings</h1>
          <p className="muted small">
            LLM API keys sirf <strong>apps/api/.env</strong> (server) par rakho — UI par key paste nahi hoti.
          </p>
          <p className="muted small ist-clock" title="Asia/Kolkata (IST)">
            {istNow}
          </p>
        </div>
        <Link className="btn ghost" to="/">
          ← Chat
        </Link>
      </header>

      {msg && <div className="banner ok">{msg}</div>}
      {err && <div className="banner error">{err}</div>}

      <section className="card stack">
        <h2>Money & savings</h2>
        <p className="muted small">
          Lamba budget / export bhej sakte ho (server ab zyada bada message accept karta hai). Main chat mein bhi spends + bonus bata sakte ho; assistant tools se cash / runway update hota hai.
        </p>

        <div className="external-prompt-block">
          <p className="muted small" style={{ margin: 0 }}>
            <strong>ChatGPT / doosri AI</strong> se list nikalwane ke liye: neeche prompt <strong>Copy</strong> karo → wahan paste → jo structured block mile (BEGIN_EXPORT … END_EXPORT) woh <strong>niche assistant</strong> mein paste karo. Agar doosri AI ke paas tumhari spends ka context nahi, woh pehle sawal puchegi — jawab deke phir export lo.
          </p>
          <div className="row wrap align-end">
            <button type="button" className="btn primary" onClick={() => void copyExternalPrompt()}>
              Copy prompt (for ChatGPT / other AI)
            </button>
            {promptCopied ? <span className="muted small">Copied.</span> : null}
          </div>
          <textarea readOnly className="mono-readonly" rows={12} value={EXTERNAL_AI_EXPORT_PROMPT} aria-label="Prompt to copy into another AI" />
        </div>

        {!llm?.server_key_configured && (
          <p className="muted small text-bad">
            AI abhi band hai — neeche provider section mein server key fix karo, phir yahan type kar paoge.
          </p>
        )}
        <h3 className="title" style={{ fontSize: "1rem", margin: "0.25rem 0 0" }}>
          Assistant — yahan export paste karo ya budget likho
        </h3>
        <div className="settings-chat">
          {moneyMsgs.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {bubbleText(m.content)}
            </div>
          ))}
          {moneySending && (
            <div className="bubble assistant typing">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          )}
          <div ref={moneyBottomRef} />
        </div>
        <form className="row align-end wrap" onSubmit={sendMoneyChat}>
          <textarea
            className="grow input-grow"
            rows={3}
            maxLength={100_000}
            placeholder={llm?.server_key_configured ? "Export paste ya budget… Shift+Enter newline, Enter send" : "Pehle server key…"}
            value={moneyInput}
            onChange={(e) => setMoneyInput(e.target.value)}
            onKeyDown={onMoneyKeyDown}
            disabled={!llm?.server_key_configured || moneySending}
          />
          <button className="btn primary" type="submit" disabled={!llm?.server_key_configured || moneySending || !moneyInput.trim()}>
            Send
          </button>
          <button type="button" className="btn ghost" onClick={resetMoneyChat}>
            Reset chat
          </button>
        </form>

        <details className="manual-block">
          <summary>Optional — numbers manually (salary date / rent / cash)</summary>
          <form className="stack" onSubmit={saveProfile}>
            <label className="field">
              <span>Salary day — mahine ki kaunsi tareekh (1–31)</span>
              <input inputMode="numeric" value={salaryDay} onChange={(e) => setSalaryDay(e.target.value)} placeholder="e.g. 5 ya 28" />
              <span className="muted small">Rent/cash nahi — sirf calendar date.</span>
            </label>
            <label className="field">
              <span>Monthly rent (₹)</span>
              <input inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} />
            </label>
            <label className="field">
              <span>Estimated cash now (₹)</span>
              <input inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} />
            </label>
            <button className="btn primary" type="submit" disabled={busy}>
              Save numbers
            </button>
          </form>
        </details>
      </section>

      <section className="card stack">
        <h2>AI provider</h2>
        <form className="stack" onSubmit={saveLlm}>
          <div className="row wrap">
            {(["openai", "openrouter", "gemini"] as const).map((p) => (
              <label key={p} className="pill">
                <input type="radio" name="prov" checked={provider === p} onChange={() => setProvider(p)} />
                {p}
              </label>
            ))}
          </div>
          <p className="muted small">
            Server key status (chosen provider):{" "}
            {!llm ? (
              "loading…"
            ) : llm.server_key_configured ? (
              <strong className="text-ok">OK — {keyHint} set hai</strong>
            ) : (
              <strong className="text-bad">
                missing — apps/api/.env mein {keyHint} add karo, API restart karo
              </strong>
            )}
          </p>
          {provider === "openrouter" && (
            <label className="field">
              <span>HTTP-Referer (OpenRouter)</span>
              <input value={referer} onChange={(e) => setReferer(e.target.value)} placeholder="https://your-site.example" />
            </label>
          )}
          <button className="btn primary" type="submit" disabled={busy}>
            Save provider
          </button>
        </form>
      </section>
    </div>
  );
}
