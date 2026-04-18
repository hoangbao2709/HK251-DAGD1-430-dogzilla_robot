"use client";

import { Mic, Send, Square } from "lucide-react";
import { DarkCard, SectionLabel } from "./Shared";

type VoiceCommandPanelProps = {
    isDark: boolean;
    commandText: string;
    isSendingCommand: boolean;
    commandResult: any | null;
    commandError: string;
    isListening: boolean;
    onCommandTextChange: (value: string) => void;
    onStartListening: () => void;
    onStopListening: () => void;
    onSendVoiceCommand: () => void;
};

export function VoiceCommandPanel({
    isDark,
    commandText,
    isSendingCommand,
    commandResult,
    commandError,
    isListening,
    onCommandTextChange,
    onStartListening,
    onStopListening,
    onSendVoiceCommand,
}: VoiceCommandPanelProps) {
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
    const textareaClass = isDark
        ? "mt-3 min-h-[168px] w-full resize-none rounded-2xl border border-white/10 bg-[#12071f] px-4 py-4 text-base leading-6 text-white outline-none placeholder:text-white/30"
        : "mt-3 min-h-[168px] w-full resize-none rounded-2xl border border-[#d8cbff] bg-[#fffdfd] px-4 py-4 text-base leading-6 text-[#1f1640] outline-none placeholder:text-[#9f96b8]";
    const primaryButtonClass =
        "inline-flex items-center justify-center gap-2 rounded-full bg-[#10b981] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0ea56f] disabled:cursor-not-allowed disabled:opacity-50";
    const secondaryButtonClass = isDark
        ? "inline-flex items-center justify-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/[0.08]"
        : "inline-flex items-center justify-center gap-2 rounded-full border border-[#d8cbff] bg-[#f8f4ff] px-4 py-2.5 text-sm font-semibold text-[#24163f] transition hover:bg-[#f1ebff]";
    const resultBodyClass = isDark ? "space-y-2 text-sm text-white/80" : "space-y-2 text-sm text-[#483b61]";

    return (
        <DarkCard className={shellClass}>
            <div className="flex items-center justify-between gap-3">
                <SectionLabel>Voice navigation command</SectionLabel>
                <span
                    className={
                        isListening ? "text-[11px] font-medium text-cyan-600 dark:text-cyan-400" : metaClass
                    }
                >
                    {isListening ? "Listening" : "Idle"}
                </span>
            </div>

            <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                    <div className={panelClass}>
                        <div className={labelClass}>Command</div>

                        <textarea
                            value={commandText}
                        onChange={(e) => onCommandTextChange(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                onSendVoiceCommand();
                            }
                        }}
                            placeholder="Hãy cho robot đi đến điểm A"
                            className={textareaClass}
                        />
                    </div>

                <div className={panelClass}>
                    <div className={labelClass}>Controls</div>
                    <div className="mt-3 grid gap-2">
                        {!isListening ? (
                            <button onClick={onStartListening} className={secondaryButtonClass}>
                                <Mic size={16} />
                                Start mic
                            </button>
                        ) : (
                            <button onClick={onStopListening} className={secondaryButtonClass}>
                                <Square size={16} />
                                Stop mic
                            </button>
                        )}
                        <button
                            onClick={onSendVoiceCommand}
                            disabled={isSendingCommand}
                            className={primaryButtonClass}
                        >
                            <Send size={16} />
                            {isSendingCommand ? "Sending..." : "Send now"}
                        </button>
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
                                {commandResult.input_text || commandText || "—"}
                            </span>
                        </div>
                        {commandResult.result?.tool ? (
                            <div className="flex items-start justify-between gap-3">
                                <span className={isDark ? "text-white/55" : "text-[#7a6f95]"}>Tool</span>
                                <span className={isDark ? "text-right text-white" : "text-right text-[#1f1640]"}>
                                    {commandResult.result.tool}
                                </span>
                            </div>
                        ) : null}
                        {commandResult.result?.arguments ? (
                            <pre className={isDark ? "mt-2 overflow-auto rounded-xl bg-[#241139] p-3 text-xs text-white/65" : "mt-2 overflow-auto rounded-xl bg-[#f6f2ff] p-3 text-xs text-[#62577f]"}>
                                {JSON.stringify(commandResult.result.arguments, null, 2)}
                            </pre>
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
