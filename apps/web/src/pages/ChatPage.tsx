import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Wallet2, X } from "lucide-react";
import { ChatComposer, type LlmProviderId } from "@/components/chat/ChatComposer";
import { apiFetch } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { formatNowIST } from "../lib/istClock";

type Msg = { role: "user" | "assistant"; content: string };

const LISTEN_MAX_MS = 55_000;
/** Ring completes 0→1 over this window (visual matches typical short sessions). */
const MIC_RING_PERIOD_MS = 5_000;
const SILENCE_END_MS = 2_800;

/** Hide raw ** from model / old copy in the UI */
function bubbleText(s: string) {
  return s.replace(/\*\*/g, "");
}

function getSpeechRecognition(): (new () => SpeechRecognition) | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognition;
    webkitSpeechRecognition?: new () => SpeechRecognition;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

function normalizeProvider(p: string | undefined): LlmProviderId {
  if (p === "openai" || p === "openrouter" || p === "gemini") return p;
  return "openrouter";
}

function walletText(v: string | null | undefined): string {
  if (v == null || v === "") return "not set";
  return v;
}

export function ChatPage() {
  const { token, logout, user, refreshUser } = useAuth();
  const [profitSnap, setProfitSnap] = useState<{ budget: number | null; profit: number | null }>({ budget: null, profit: null });

  const refreshProfit = useCallback(async () => {
    if (!token) return;
    try {
      const today = await apiFetch<{ budget_inr: string | null; profit_inr: string | null }>("/users/me/today", { token, method: "GET" });
      setProfitSnap({
        budget: today.budget_inr != null ? Number(today.budget_inr) : null,
        profit: today.profit_inr != null ? Number(today.profit_inr) : null,
      });
    } catch { /* non-critical */ }
  }, [token]);

  const [messages, setMessages] = useState<Msg[]>([
    { role: "assistant", content: "Main tumhare paise ka accountant dost hoon 😄 Jo likhoge woh yaad, jo nahi likhoge woh hawa.😉" },
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [micRing, setMicRing] = useState(0);
  const [istNow, setIstNow] = useState(() => formatNowIST());
  const [walletSaving, setWalletSaving] = useState(false);
  const [walletEditOpenFor, setWalletEditOpenFor] = useState<number | null>(null);
  const [walletEditDraft, setWalletEditDraft] = useState("");
  const walletEditRef = useRef<HTMLInputElement | null>(null);
  const recRef = useRef<SpeechRecognition | null>(null);
  const listenRafRef = useRef<number | null>(null);
  const silenceIvRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const listenStartedAtRef = useRef(0);
  const lastResultAtRef = useRef(0);
  const heardSpeechRef = useRef(false);
  const listenCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const id = window.setInterval(() => setIstNow(formatNowIST()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => { void refreshProfit(); }, [refreshProfit]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const send = useCallback(
    async (text: string) => {
      const t = text.trim();
      if (!t || !token) return;
      setErr(null);
      setSending(true);
      setMessages((m) => [...m, { role: "user", content: t }]);
      try {
        const body: { message: string; session_id?: string } = { message: t };
        if (sessionId) body.session_id = sessionId;
        const res = await apiFetch<{ session_id: string; reply: string }>("/chat", {
          method: "POST",
          token,
          body: JSON.stringify(body),
        });
        setSessionId(res.session_id);
        setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
        await refreshUser();
        void refreshProfit();
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Chat failed");
        setMessages((m) => [...m, { role: "assistant", content: "Something went wrong — network check karo ya Settings → provider." }]);
      } finally {
        setSending(false);
      }
    },
    [token, sessionId, refreshUser, refreshProfit],
  );

  async function submitChat() {
    const t = input.trim();
    if (!t || !token || sending) return;
    setInput("");
    await send(t);
  }

  async function changeProvider(id: LlmProviderId) {
    if (!token) return;
    setErr(null);
    try {
      await apiFetch("/users/me/llm", {
        method: "PUT",
        token,
        body: JSON.stringify({ provider: id }),
      });
      await refreshUser();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not switch provider");
    }
  }

  const wallets = [
    user?.wallet_1_inr ?? null,
    user?.wallet_2_inr ?? null,
    user?.wallet_3_inr ?? null,
    user?.wallet_4_inr ?? null,
    user?.wallet_5_inr ?? null,
  ];

  const walletLoans = [
    user?.wallet_1_loan_inr ?? null,
    user?.wallet_2_loan_inr ?? null,
    user?.wallet_3_loan_inr ?? null,
    user?.wallet_4_loan_inr ?? null,
    user?.wallet_5_loan_inr ?? null,
  ];

  useEffect(() => {
    if (walletEditOpenFor == null) return;
    const idx = walletEditOpenFor - 1;
    const currentVal = wallets[idx];
    setWalletEditDraft(currentVal ?? "");
  }, [walletEditOpenFor, user?.wallet_1_inr, user?.wallet_2_inr, user?.wallet_3_inr, user?.wallet_4_inr, user?.wallet_5_inr]);

  useEffect(() => {
    if (walletEditOpenFor == null) return;
    const t = window.setTimeout(() => walletEditRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [walletEditOpenFor]);

  async function switchWallet(next: number) {
    if (!token || walletSaving || next < 1 || next > 5) return;
    setWalletSaving(true);
    setErr(null);
    try {
      await apiFetch("/users/me", {
        method: "PATCH",
        token,
        body: JSON.stringify({ active_wallet_id: next }),
      });
      await refreshUser();
      setWalletEditOpenFor(next);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not switch wallet");
    } finally {
      setWalletSaving(false);
    }
  }

  async function saveWalletValue(walletId: number, raw: string) {
    if (!token || walletSaving) return;
    const clean = raw.trim().replace(/,/g, "");
    const payload: Record<string, unknown> = {
      active_wallet_id: walletId,
      [`wallet_${walletId}_inr`]: clean ? clean : null,
    };
    setWalletSaving(true);
    setErr(null);
    try {
      await apiFetch("/users/me", {
        method: "PATCH",
        token,
        body: JSON.stringify(payload),
      });
      await refreshUser();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save wallet value");
    } finally {
      setWalletSaving(false);
    }
  }

  async function addWalletTab() {
    if (!token || walletSaving) return;
    const idx = wallets.findIndex((v) => v == null);
    if (idx === -1) return;
    const walletId = idx + 1;
    setWalletSaving(true);
    setErr(null);
    try {
      await apiFetch("/users/me", {
        method: "PATCH",
        token,
        body: JSON.stringify({
          [`wallet_${walletId}_inr`]: "0",
          active_wallet_id: walletId,
        }),
      });
      await refreshUser();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not add wallet");
    } finally {
      setWalletSaving(false);
    }
  }

  async function clearWalletLoan(walletId: number) {
    if (!token || walletSaving) return;
    setWalletSaving(true);
    setErr(null);
    try {
      await apiFetch("/users/me", {
        method: "PATCH",
        token,
        body: JSON.stringify({ clear_loan_wallet_ids: [walletId] }),
      });
      await refreshUser();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not clear loan");
    } finally {
      setWalletSaving(false);
    }
  }

  async function removeWalletTab(walletId: number) {
    if (!token || walletSaving || walletId < 1 || walletId > 5) return;
    setWalletSaving(true);
    setErr(null);
    try {
      await apiFetch("/users/me", {
        method: "PATCH",
        token,
        body: JSON.stringify({ remove_wallet_ids: [walletId] }),
      });
      await refreshUser();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not remove wallet");
    } finally {
      setWalletSaving(false);
    }
  }

  useEffect(() => {
    return () => {
      if (listenCloseTimerRef.current != null) {
        clearTimeout(listenCloseTimerRef.current);
        listenCloseTimerRef.current = null;
      }
      if (listenRafRef.current != null) cancelAnimationFrame(listenRafRef.current);
      if (silenceIvRef.current != null) clearInterval(silenceIvRef.current);
      try {
        recRef.current?.stop();
      } catch {
        /* ignore */
      }
    };
  }, []);

  const stopVoiceSession = useCallback((opts?: { immediate?: boolean }) => {
    if (listenCloseTimerRef.current != null) {
      clearTimeout(listenCloseTimerRef.current);
      listenCloseTimerRef.current = null;
    }
    if (listenRafRef.current != null) {
      cancelAnimationFrame(listenRafRef.current);
      listenRafRef.current = null;
    }
    if (silenceIvRef.current != null) {
      clearInterval(silenceIvRef.current);
      silenceIvRef.current = null;
    }
    const r = recRef.current;
    recRef.current = null;
    if (r) {
      r.onend = null;
      r.onerror = null;
      try {
        r.stop();
      } catch {
        /* already stopped */
      }
    }
    if (opts?.immediate) {
      setListening(false);
      setMicRing(0);
      return;
    }
    setMicRing(1);
    listenCloseTimerRef.current = setTimeout(() => {
      listenCloseTimerRef.current = null;
      setListening(false);
      setMicRing(0);
    }, 220);
  }, []);

  function toggleListen() {
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      setErr("Voice typing not supported in this browser.");
      return;
    }
    if (listening) {
      stopVoiceSession({ immediate: true });
      return;
    }
    if (listenCloseTimerRef.current != null) {
      clearTimeout(listenCloseTimerRef.current);
      listenCloseTimerRef.current = null;
    }
    setErr(null);
    heardSpeechRef.current = false;
    lastResultAtRef.current = Date.now();
    listenStartedAtRef.current = Date.now();
    const rec = new Ctor();
    rec.lang = "en-IN";
    rec.interimResults = true;
    rec.continuous = true;
    rec.onresult = (ev: SpeechRecognitionEvent) => {
      heardSpeechRef.current = true;
      lastResultAtRef.current = Date.now();
      let text = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) text += ev.results[i][0].transcript;
      setInput((prev) => `${prev} ${text}`.trim());
    };
    rec.onerror = () => stopVoiceSession();
    rec.onend = () => {
      stopVoiceSession();
    };
    rec.start();
    recRef.current = rec;
    setListening(true);
    setMicRing(0);

    const tick = () => {
      const elapsedMs = Date.now() - listenStartedAtRef.current;
      setMicRing(Math.min(1, elapsedMs / MIC_RING_PERIOD_MS));
      if (elapsedMs >= LISTEN_MAX_MS) {
        stopVoiceSession();
        return;
      }
      listenRafRef.current = requestAnimationFrame(tick);
    };
    listenRafRef.current = requestAnimationFrame(tick);

    silenceIvRef.current = setInterval(() => {
      if (!heardSpeechRef.current) return;
      if (Date.now() - lastResultAtRef.current >= SILENCE_END_MS) {
        stopVoiceSession();
      }
    }, 350);
  }

  const provider = normalizeProvider(user?.llm_provider);

  return (
    <div className="shell chat-shell">
      <header className="topbar">
        <div>
          <h1 className="title">Pocket Buddy</h1>
          <p className="muted small ist-clock" title="Asia/Kolkata (IST)">
            {istNow}
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.35rem" }}>
          <div className="topbar-settings-block">
            <Link className="btn ghost" to="/settings">
              Settings
            </Link>
            <button type="button" className="btn ghost" onClick={() => logout()}>
              Log out
            </button>
          </div>
          <div className="wallet-tabs-row">
            {wallets.map((val, i) => {
              const wid = i + 1;
              if (val == null) return null;
              const active = (user?.active_wallet_id ?? 1) === wid;
              const loan = wid === 1 ? null : walletLoans[i]; // wallet 1 never shows loan indicator
              const loanNum = loan != null ? Number(loan) : null;
              const loanPositive = loanNum != null && loanNum > 0;
              const loanNegative = loanNum != null && loanNum < 0;
              return (
                <button key={wid} type="button" className={`wallet-tab ${active ? "active" : ""}`} onClick={() => void switchWallet(wid)}>
                  <Wallet2 size={13} className="wallet-chip-icon" />
                  <span>wallet {wid}: ₹{walletText(val)}</span>
                  {loanNegative && (
                    <span style={{ display: "flex", alignItems: "center", gap: "0.1rem" }}>
                      <span style={{ color: "#ef4444", fontWeight: 600, fontSize: "0.7rem" }}>{loanNum!.toLocaleString("en-IN")}</span>
                      <span className="wallet-tab-close" title="Clear loan" onClick={(e) => { e.stopPropagation(); void clearWalletLoan(wid); }}><X size={10} /></span>
                    </span>
                  )}
                  {loanPositive && (
                    <span style={{ display: "flex", alignItems: "center", gap: "0.1rem" }}>
                      <span style={{ color: "#22c55e", fontWeight: 600, fontSize: "0.7rem" }}>+{loanNum!.toLocaleString("en-IN")}</span>
                      <span className="wallet-tab-close" title="Clear loan" onClick={(e) => { e.stopPropagation(); void clearWalletLoan(wid); }}><X size={10} /></span>
                    </span>
                  )}
                  <span
                    className="wallet-tab-close"
                    onClick={(e) => {
                      e.stopPropagation();
                      void removeWalletTab(wid);
                    }}
                  >
                    <X size={12} />
                  </span>
                </button>
              );
            })}
            <button type="button" className="wallet-plus" onClick={() => void addWalletTab()} title="Add wallet" disabled={walletSaving || wallets.every((w) => w != null)}>
              <Plus size={13} />
            </button>
          </div>
          {(profitSnap.budget != null || profitSnap.profit != null) && (() => {
            const profit = profitSnap.profit ?? 0;
            const isPos = profit >= 0;
            const color = isPos ? "#22c55e" : "#ef4444";
            const sign = isPos ? "+" : "-";
            return (
              <div style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem", marginTop: "0.15rem" }}>
                <span style={{ color: "var(--muted)" }}>Buffer</span>
                <span style={{ color, fontWeight: 700 }}>{sign}₹{Math.abs(profit).toLocaleString("en-IN")}</span>
              </div>
            );
          })()}
          {walletEditOpenFor != null && (
            <div className="wallet-inline-edit">
              <span>Wallet {walletEditOpenFor}</span>
              <input
                ref={walletEditRef}
                value={walletEditDraft}
                inputMode="decimal"
                onChange={(e) => setWalletEditDraft(e.target.value)}
                onBlur={() => {
                  void saveWalletValue(walletEditOpenFor, walletEditDraft);
                  setWalletEditOpenFor(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    const el = e.currentTarget;
                    void saveWalletValue(walletEditOpenFor, walletEditDraft);
                    setWalletEditOpenFor(null);
                    el.blur();
                  }
                }}
                placeholder="Enter amount"
              />
            </div>
          )}
        </div>
      </header>

      <main className="chat-main">
        <div className="thread">
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {bubbleText(m.content)}
            </div>
          ))}
          {sending && (
            <div className="bubble assistant typing">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </main>

      {err && <div className="banner error">{err}</div>}

      <div className="composer-tailwind">
        <ChatComposer
          value={input}
          onChange={setInput}
          onSend={() => void submitChat()}
          disabled={sending || !token}
          placeholder="Talk to me about your budget ..."
          provider={provider}
          onProviderChange={(id) => void changeProvider(id)}
          onMicClick={toggleListen}
          listening={listening}
          micListenElapsedFraction={micRing}
        />
      </div>
    </div>
  );
}
