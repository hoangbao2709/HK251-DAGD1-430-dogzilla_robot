"use client";

import { Mic, Square, Volume2 } from "lucide-react";
import { DarkCard, SectionLabel } from "./Shared";

type VoiceCommandPanelProps = {
  isDark: boolean;
  commandText: string;
  isSendingCommand: boolean;
  commandResult: any | null;
  commandError: string;
  isListening: boolean;
  onStartListening: () => void;
  onStopListening: () => void;
};

export function VoiceCommandPanel({
  isDark,
  commandText,
  isSendingCommand,
  commandResult,
  commandError,
  isListening,
  onStartListening,
  onStopListening,
}: VoiceCommandPanelProps) {
  const resultItems = Array.isArray(commandResult?.results)
    ? commandResult.results
    : commandResult?.result
      ? [commandResult.result]
      : [];
  const plannedActions = Array.isArray(commandResult?.plan?.actions)
    ? commandResult.plan.actions
    : [];
  const sourceText = commandResult?.planner_source
    ? String(commandResult.planner_source)
    : commandResult?.result?.mapping?.source
      ? String(commandResult.result.mapping.source)
      : "";

  const shellClass = isDark
    ? "space-y-4 bg-[#0f0822] shadow-[0_18px_40px_rgba(0,194,255,0.08)]"
    : "space-y-4 bg-[#fffdfd] shadow-[0_18px_40px_rgba(0,194,255,0.08)]";
  const panelClass = isDark
    ? "rounded-2xl border border-white/10 bg-[#160a28] p-4"
    : "rounded-2xl border border-[#dacfff] bg-white p-4 shadow-[0_10px_24px_rgba(124,77,255,0.06)]";
  const labelClass = isDark
    ? "text-[10px] uppercase tracking-[0.22em] text-white/50"
    : "text-[10px] uppercase tracking-[0.22em] text-[#705d94]";
  const metaClass = isDark ? "text-xs text-white/45" : "text-xs text-[#8d84a8]";
  const transcriptClass = isDark
    ? "mt-3 flex min-h-[168px] items-center rounded-2xl border border-white/10 bg-[#12071f] px-4 py-4 text-base leading-6 text-white"
    : "mt-3 flex min-h-[168px] items-center rounded-2xl border border-[#d8cbff] bg-[#fffdfd] px-4 py-4 text-base leading-6 text-[#1f1640]";
  const secondaryButtonClass = isDark
    ? "inline-flex items-center justify-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/[0.08]"
    : "inline-flex items-center justify-center gap-2 rounded-full border border-[#d8cbff] bg-[#f8f4ff] px-4 py-2.5 text-sm font-semibold text-[#24163f] transition hover:bg-[#f1ebff]";
  const resultBodyClass = isDark ? "space-y-2 text-sm text-white/80" : "space-y-2 text-sm text-[#483b61]";

  return (
    <DarkCard className={shellClass}>
      <div className="flex items-center justify-between gap-3">
        <SectionLabel>Voice conversation command</SectionLabel>
        <span className={isListening ? "text-[11px] font-medium text-cyan-600 dark:text-cyan-400" : metaClass}>
          {isListening ? "Listening" : isSendingCommand ? "Processing" : "Idle"}
        </span>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className={panelClass}>
          <div className={labelClass}>Transcript</div>
          <div className={transcriptClass}>
            <span className={commandText ? "" : isDark ? "text-white/30" : "text-[#9f96b8]"}>
              {commandText}
            </span>
          </div>
        </div>

        <div className={panelClass}>
          <div className={labelClass}>Conversation</div>
          <div className="mt-3 grid gap-2">
            {!isListening ? (
              <button
                onClick={onStartListening}
                disabled={isSendingCommand}
                className={`cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${secondaryButtonClass}`}
              >
                <Mic size={16} />
                {isSendingCommand ? "Processing..." : "Start mic"}
              </button>
            ) : (
              <button onClick={onStopListening} className={`cursor-pointer ${secondaryButtonClass}`}>
                <Square size={16} />
                Stop mic
              </button>
            )}
          </div>
        </div>
      </div>

      {commandError ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-200">
          {commandError}
        </div>
      ) : null}

      <div className={panelClass}>
        <div className={labelClass}>Result</div>
        {commandResult ? (
          <div className={`mt-3 ${resultBodyClass}`}>
            <div className="flex items-start justify-between gap-3">
              <span className={isDark ? "text-white/55" : "text-[#7a6f95]"}>Input</span>
              <span className={isDark ? "text-right text-white" : "text-right text-[#1f1640]"}>
                {commandResult.input_text || commandText || "-"}
              </span>
            </div>
            {sourceText ? (
              <div className="flex items-start justify-between gap-3">
                <span className={isDark ? "text-white/55" : "text-[#7a6f95]"}>Planner</span>
                <span className={isDark ? "text-right text-white" : "text-right text-[#1f1640]"}>
                  {sourceText}
                </span>
              </div>
            ) : null}
            {commandResult.reply_text ? (
              <div className="flex items-start justify-between gap-3">
                <span className={isDark ? "text-white/55" : "text-[#7a6f95]"}>Reply</span>
                <span className={isDark ? "text-right text-white" : "text-right text-[#1f1640]"}>
                  {commandResult.reply_text}
                </span>
              </div>
            ) : null}
            {commandResult.llm_error ? (
              <div className="flex items-start justify-between gap-3">
                <span className={isDark ? "text-white/55" : "text-[#7a6f95]"}>Fallback</span>
                <span className={isDark ? "text-right text-amber-200" : "text-right text-amber-700"}>
                  {commandResult.llm_error}
                </span>
              </div>
            ) : null}
            {plannedActions.length ? (
              <pre className={isDark ? "mt-2 overflow-auto rounded-xl bg-[#241139] p-3 text-xs text-white/65" : "mt-2 overflow-auto rounded-xl bg-[#f6f2ff] p-3 text-xs text-[#62577f]"}>
                {JSON.stringify(plannedActions, null, 2)}
              </pre>
            ) : null}
            {resultItems.length ? (
              <div className="space-y-2">
                {resultItems.map((item: any, index: number) => (
                  <div key={`${item?.tool || "result"}-${index}`} className={isDark ? "rounded-xl border border-white/10 bg-white/[0.03] p-3" : "rounded-xl border border-[#e2d9ff] bg-[#fbf9ff] p-3"}>
                    <div className="flex items-start justify-between gap-3">
                      <span className={isDark ? "text-white/55" : "text-[#7a6f95]"}>
                        Tool {resultItems.length > 1 ? index + 1 : ""}
                      </span>
                      <span className={isDark ? "text-right text-white" : "text-right text-[#1f1640]"}>
                        {item?.tool || "unknown"}
                      </span>
                    </div>
                    {item?.arguments ? (
                      <pre className={isDark ? "mt-2 overflow-auto rounded-lg bg-[#12071f] p-2 text-xs text-white/65" : "mt-2 overflow-auto rounded-lg bg-white p-2 text-xs text-[#62577f]"}>
                        {JSON.stringify(item.arguments, null, 2)}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <div className={isDark ? "mt-3 text-sm text-white/45" : "mt-3 text-sm text-[#8d84a8]"}>
            No command sent yet.
          </div>
        )}
      </div>
    </DarkCard>
  );
}
