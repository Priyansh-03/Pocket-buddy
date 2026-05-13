import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Wallet2, X } from "lucide-react";
import { ChatComposer, type LlmProviderId } from "@/components/chat/ChatComposer";
import { apiFetch, apiUrl } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { formatNowIST } from "../lib/istClock";

type Msg = { role: "user" | "assistant"; content: string };

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
  if (p === "openrouter" || p === "gemini") return p;
  return "openai";
}

function walletText(v: string | null | undefined): string {
  if (v == null || v === "") return "not set";
  return v;
}

export function ChatPage() {
  const { token, logout, user, refreshUser } = useAuth();
  const [messages, setMessages] = useState<Msg[]>([
    { role: "assistant", content: "Main tumhare paise ka accountant dost hoon 😄 Jo likhoge woh yaad, jo nahi likhoge woh hawa.😉" },
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [recordingWhisper, setRecordingWhisper] = useState(false);
  const [istNow, setIstNow] = useState(() => formatNowIST());
  const [walletSaving, setWalletSaving] = useState(false);
  const [walletEditOpenFor, setWalletEditOpenFor] = useState<number | null>(null);
  const [walletEditDraft, setWalletEditDraft] = useState("");
  const walletEditRef = useRef<HTMLInputElement | null>(null);
  const recRef = useRef<SpeechRecognition | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const id = window.setInterval(() => setIstNow(formatNowIST()), 1000);
    return () => window.clearInterval(id);
  }, []);

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
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Chat failed");
        setMessages((m) => [...m, { role: "assistant", content: "Something went wrong — check Settings → API key." }]);
      } finally {
        setSending(false);
      }
    },
    [token, sessionId, refreshUser],
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
    const clean = raw.trim();
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

  function toggleListen() {
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      setErr("Voice typing not supported in this browser.");
      return;
    }
    if (listening) {
      recRef.current?.stop();
      setListening(false);
      return;
    }
    setErr(null);
    const rec = new Ctor();
    rec.lang = "en-IN";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (ev: SpeechRecognitionEvent) => {
      let text = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) text += ev.results[i][0].transcript;
      setInput((prev) => `${prev} ${text}`.trim());
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    rec.start();
    recRef.current = rec;
    setListening(true);
  }

  async function recordWhisper() {
    if (!token) return;
    setErr(null);
    setRecordingWhisper(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : undefined;
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks: BlobPart[] = [];
      mr.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      const done = new Promise<void>((resolve) => {
        mr.onstop = () => resolve();
      });
      mr.start(250);
      await new Promise((r) => setTimeout(r, 4000));
      if (mr.state === "recording") mr.stop();
      await done;
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: mime || "audio/webm" });
      const fd = new FormData();
      fd.append("file", blob, "clip.webm");
      const res = await fetch(apiUrl("/transcribe"), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const j = await res.json();
          if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      const j = (await res.json()) as { text: string };
      setInput((p) => `${p} ${j.text || ""}`.trim());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Transcription failed");
    } finally {
      setRecordingWhisper(false);
    }
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
          <div className="row">
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
              return (
                <button key={wid} type="button" className={`wallet-tab ${active ? "active" : ""}`} onClick={() => void switchWallet(wid)}>
                  <Wallet2 size={13} className="wallet-chip-icon" />
                  <span>wallet {wid}: ₹{walletText(val)}</span>
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
          onRecordClick={() => void recordWhisper()}
          listening={listening}
          recording={recordingWhisper}
        />
      </div>
    </div>
  );
}
