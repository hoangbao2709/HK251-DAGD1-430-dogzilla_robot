"use client";

import { Bot } from "lucide-react";
import { SectionLabel } from "./Shared";

type CameraPanelProps = {
    cameraReady: boolean;
    cameraError: boolean;
    robotFps?: number;
    videoSrc: string;
    onLoad: () => void;
    onError: () => void;
};

export function CameraPanel({
    cameraReady,
    cameraError,
    robotFps,
    videoSrc,
    onLoad,
    onError,
}: CameraPanelProps) {
    return (
        <div className="flex h-full flex-col">
            <SectionLabel>Camera QR scan</SectionLabel>
            <div className="relative flex-1 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] min-h-[360px] xl:min-h-[560px]">
                {!cameraReady ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[linear-gradient(180deg,var(--surface),var(--surface-2))] px-4 text-center">
                        <div className="flex h-16 w-16 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--surface-elev)] shadow-sm">
                            <Bot size={28} className="text-[var(--accent)]" />
                        </div>
                        <div>
                            <p className="text-sm font-semibold text-[var(--foreground)]">
                                Waiting for QR camera stream
                            </p>
                            <p className="mt-1 text-xs text-[var(--muted)]">
                                The frame will appear here once the robot camera is available.
                            </p>
                        </div>
                        <div className="mt-2 h-1.5 w-48 overflow-hidden rounded-full bg-[rgba(23,19,39,0.10)] dark:bg-white/10">
                            <div className="h-full w-1/3 animate-pulse rounded-full bg-gradient-to-r from-[#FD749B] via-[#7C4DFF] to-[#00C2FF]" />
                        </div>
                    </div>
                ) : null}

                <img
                    src={videoSrc}
                    alt="QR video feed"
                    className={`block h-full w-full bg-[var(--surface-elev)] object-cover transition-opacity duration-300 ${
                        cameraReady ? "opacity-100" : "opacity-0"
                    }`}
                    onLoad={onLoad}
                    onError={onError}
                />

                <span className="absolute left-4 top-3 font-mono text-sm font-bold tracking-wider text-green-400">
                    FPS:{robotFps ?? "--"}
                </span>
            </div>

            {cameraError ? (
                <p className="mt-2 text-xs text-red-300/80">
                    Không tải được camera QR stream
                </p>
            ) : null}
        </div>
    );
}
