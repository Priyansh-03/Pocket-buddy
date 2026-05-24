import { ArrowRight, Check, ChevronDown, Mic, Paperclip, Plus } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, type KeyboardEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface UseAutoResizeTextareaProps {
  minHeight: number;
  maxHeight?: number;
}

function useAutoResizeTextarea({ minHeight, maxHeight }: UseAutoResizeTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(
    (reset?: boolean) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      if (reset) {
        textarea.style.height = `${minHeight}px`;
        return;
      }

      textarea.style.height = `${minHeight}px`;
      const cap = maxHeight ?? Number.POSITIVE_INFINITY;
      const newHeight = Math.max(minHeight, Math.min(textarea.scrollHeight, cap));
      textarea.style.height = `${newHeight}px`;
    },
    [minHeight, maxHeight],
  );

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) textarea.style.height = `${minHeight}px`;
  }, [minHeight]);

  useEffect(() => {
    const handleResize = () => adjustHeight();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [adjustHeight]);

  return { textareaRef, adjustHeight };
}

const OPENAI_ICON = (
  <span
    aria-hidden
    style={{
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      width: 16,
      height: 16,
      borderRadius: 999,
      border: "none",
      background: "rgba(255,255,255,0.9)",
      color: "#111",
      fontSize: 8,
      fontWeight: 700,
      lineHeight: 1,
      boxShadow: "0 1px 2px rgba(55,38,62,0.15)",
    }}
  >
    AI
  </span>
);

const OPENROUTER_ICON = (
  <span
    aria-hidden
    style={{
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      width: 16,
      height: 16,
      borderRadius: 999,
      border: "none",
      background: "rgba(255,255,255,0.9)",
      color: "#111",
      fontSize: 8,
      fontWeight: 700,
      lineHeight: 1,
      boxShadow: "0 1px 2px rgba(55,38,62,0.15)",
    }}
  >
    OR
  </span>
);

function GeminiIcon({ gradId }: { gradId: string }) {
  const safe = gradId.replace(/[^a-zA-Z0-9_-]/g, "");
  return (
    <svg height="1em" className="h-4 w-4" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id={safe} x1="0%" x2="68.73%" y1="100%" y2="30.395%">
          <stop offset="0%" stopColor="#1C7DFF" />
          <stop offset="52.021%" stopColor="#1C69FF" />
          <stop offset="100%" stopColor="#F0DCD6" />
        </linearGradient>
      </defs>
      <path
        d="M12 24A14.304 14.304 0 000 12 14.304 14.304 0 0012 0a14.305 14.305 0 0012 12 14.305 14.305 0 00-12 12"
        fill={`url(#${safe})`}
        fillRule="nonzero"
      />
    </svg>
  );
}

export type LlmProviderId = "openai" | "openrouter" | "gemini";

export type ChatComposerProps = {
  value: string;
  onChange: (next: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
  provider: LlmProviderId;
  onProviderChange?: (id: LlmProviderId) => void;
  onMicClick?: () => void;
  listening?: boolean;
  /** 0 = full ring, 1 = time up (stroke fully drawn away). */
  micListenElapsedFraction?: number;
};

export function ChatComposer({
  value,
  onChange,
  onSend,
  disabled,
  placeholder = "Example: 120 auto, chai…",
  provider,
  onProviderChange,
  onMicClick,
  listening,
  micListenElapsedFraction = 0,
}: ChatComposerProps) {
  const geminiGradId = useId().replace(/:/g, "");
  const providers = useMemo(
    () =>
      [
        { id: "openai" as const, label: "OpenAI", icon: OPENAI_ICON },
        { id: "openrouter" as const, label: "OpenRouter", icon: OPENROUTER_ICON },
        { id: "gemini" as const, label: "Gemini", icon: <GeminiIcon gradId={`gg-${geminiGradId}`} /> },
      ] satisfies { id: LlmProviderId; label: string; icon: ReactNode }[],
    [geminiGradId],
  );

  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 72,
    maxHeight: 300,
  });

  const selected = providers.find((p) => p.id === provider) ?? providers[0];

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && value.trim() && !disabled) {
      e.preventDefault();
      onSend();
      requestAnimationFrame(() => adjustHeight(true));
    }
  };

  const send = () => {
    if (!value.trim() || disabled) return;
    onSend();
    adjustHeight(true);
  };

  const insertUpdatePrefix = useCallback(() => {
    const prev = value;
    const t = prev.trimStart();
    if (/^\/update\b/i.test(t)) return;
    const body = prev.trimStart();
    const next = body ? `/update ${body}` : "/update ";
    onChange(next);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      const n = el.value.length;
      el.setSelectionRange(n, n);
      adjustHeight();
    });
  }, [value, onChange, textareaRef, adjustHeight]);

  const ringFrac = listening ? Math.min(1, Math.max(0, micListenElapsedFraction)) : 0;
  const micArcR = 16;
  const micArcLen = 2 * Math.PI * micArcR;
  const micDashOffset = micArcLen * ringFrac;

  return (
    <div className="w-full max-w-3xl py-2">
      <div className="rounded-2xl bg-white/28 p-1.5 shadow-md shadow-black/5 ring-1 ring-white/50">
        <div className="relative flex flex-col">
          <div className="relative flex max-h-[400px] items-end gap-2 overflow-y-auto pr-2 pb-2">
            <div className="relative min-h-[72px] min-w-0 flex-1">
              <Textarea
                id="chat-composer-input"
                value={value}
                placeholder={placeholder}
                className={cn(
                  "w-full resize-none rounded-xl rounded-b-none bg-white/46 py-3 pr-4 pl-10 pb-10 text-[var(--text)] shadow-inner shadow-black/5 ring-1 ring-white/55",
                  "placeholder:text-[var(--muted)] focus-visible:ring-0 focus-visible:ring-offset-0",
                  "min-h-[72px]",
                )}
                ref={textareaRef}
                maxLength={100_000}
                disabled={disabled}
                onKeyDown={handleKeyDown}
                onChange={(e) => {
                  onChange(e.target.value);
                  adjustHeight();
                }}
              />
              <div className="pointer-events-none absolute bottom-2 left-2 z-10">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className={cn(
                        "pointer-events-auto flex h-7 w-7 items-center justify-center rounded-full",
                        "bg-white/80 text-[var(--text)] shadow-md shadow-black/8 ring-1 ring-white/60",
                        "transition-transform duration-200 ease-out data-[state=open]:rotate-180",
                        "disabled:pointer-events-none disabled:opacity-40",
                      )}
                      aria-label="Composer tools"
                      title="Tools"
                      disabled={disabled}
                    >
                      <Plus className="h-3 w-3" strokeWidth={2.5} />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    side="top"
                    align="start"
                    sideOffset={8}
                    className="min-w-[13.5rem] rounded-lg bg-[rgba(255,250,252,0.98)] p-1 text-[var(--text)] shadow-lg shadow-black/10 ring-1 ring-white/70"
                  >
                    <DropdownMenuItem
                      className="flex cursor-pointer flex-col items-start gap-0.5 rounded-md py-2.5 pl-2.5 pr-2 focus:bg-black/[0.06]"
                      onSelect={() => insertUpdatePrefix()}
                    >
                      <span className="font-mono text-[13px] font-semibold tracking-tight text-[#111]">/update</span>
                      <span className="text-[11px] leading-snug text-[var(--muted)]">update if any new expense</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
            <button
              type="button"
              className={cn(
                "rounded-lg bg-white/50 p-2 shadow-md shadow-black/6 ring-1 ring-white/55",
                "hover:bg-white/55",
                "disabled:opacity-40",
              )}
              aria-label="Send message"
              disabled={!value.trim() || disabled}
              onClick={send}
            >
              <ArrowRight
                className={cn(
                  "h-4 w-4 text-[var(--text)] transition-opacity duration-200",
                  value.trim() && !disabled ? "opacity-100" : "opacity-30",
                )}
              />
            </button>
          </div>

          <div className="relative flex h-14 min-h-14 shrink-0 items-center rounded-b-xl bg-white/28 px-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] ring-1 ring-white/45">
            <div className="flex min-h-0 w-full min-w-0 flex-1 flex-nowrap items-center justify-between gap-2 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-8 shrink-0 gap-1 rounded-md pl-1 pr-2 text-xs text-[var(--text)]"
                      disabled={!onProviderChange}
                    >
                      <span className="flex items-center gap-1">
                        {selected.icon}
                        {selected.label}
                        <ChevronDown className="h-3 w-3 opacity-50" />
                      </span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    {providers.map((p) => (
                      <DropdownMenuItem
                        key={p.id}
                        className="gap-2"
                        onSelect={() => onProviderChange?.(p.id)}
                      >
                        <span className="flex items-center gap-2">
                          {p.icon}
                          {p.label}
                        </span>
                        {provider === p.id ? <Check className="h-4 w-4 text-cyan-400" /> : null}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                <div className="mx-0.5 h-4 w-px shrink-0 bg-black/55" />

                {onMicClick ? (
                  <button
                    type="button"
                    onClick={onMicClick}
                    disabled={disabled}
                    aria-label={listening ? "Stop voice input" : "Voice input"}
                    className={cn(
                      "relative box-border flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/92",
                      "border-2 border-solid shadow-none outline-none ring-0",
                      listening ? "border-cyan-500" : "border-neutral-900/80",
                      "hover:bg-white",
                      "focus-visible:ring-2 focus-visible:ring-cyan-400/35 focus-visible:ring-offset-0",
                      disabled && "pointer-events-none opacity-40",
                    )}
                    style={{ WebkitTapHighlightColor: "transparent" }}
                  >
                    {listening ? (
                      <svg
                        className="pointer-events-none absolute inset-0 block h-full w-full"
                        viewBox="0 0 40 40"
                        preserveAspectRatio="xMidYMid meet"
                        aria-hidden
                      >
                        <circle
                          cx="20"
                          cy="20"
                          r={micArcR}
                          fill="none"
                          stroke="#06b6d4"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeDasharray={micArcLen}
                          strokeDashoffset={micDashOffset}
                          transform="rotate(-90 20 20)"
                        />
                      </svg>
                    ) : null}
                    <Mic
                      className={cn(
                        "relative z-[1] size-4 shrink-0",
                        listening ? "text-cyan-600" : "text-neutral-600",
                      )}
                    />
                  </button>
                ) : null}

                <label
                  className={cn(
                    "shrink-0 cursor-not-allowed rounded-lg bg-white/35 p-2 opacity-70 shadow-sm ring-1 ring-white/40",
                  )}
                  aria-label="Attach file (soon)"
                  title="Coming soon"
                >
                  <input type="file" className="hidden" disabled />
                  <Paperclip className="h-4 w-4 text-[var(--muted)]" />
                </label>
              </div>
            </div>
          </div>
      </div>
    </div>
  );
}

export { ChatComposer as AI_Prompt };
