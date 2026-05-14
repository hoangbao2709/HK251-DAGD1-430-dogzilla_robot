"use client";

import { useCallback, useMemo } from "react";
import type { QrPositionData } from "../types";

export function SectionLabel({ children }: { children: React.ReactNode }) {
    return (
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-[var(--muted)]">
            {children}
        </h3>
    );
}

export function DarkCard({
    children,
    className = "",
}: {
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <div className={`rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 ${className}`}>
            {children}
        </div>
    );
}

export function TopDownQrView({ data }: { data: QrPositionData | null }) {
    const width = 260;
    const height = 260;
    const padding = 18;
    const baselineY = height - 18;

    const rangeM = useMemo(() => {
        const candidates = [
            data?.render_hint?.suggested_max_range_m,
            data?.lidar?.distance_m,
            data?.position?.distance_m,
            data?.target?.distance_m,
            data?.position?.forward_z_m,
            data?.target?.z_m,
        ].filter((value): value is number => typeof value === "number" && isFinite(value));

        if (candidates.length === 0) return 3;
        const farthest = Math.max(...candidates);
        return Math.min(Math.max(farthest + 0.5, 2), 4);
    }, [data]);

    const toX = useCallback(
        (meters: number) => width / 2 + (meters / rangeM) * ((width / 2) - padding),
        [rangeM]
    );

    const toY = useCallback(
        (meters: number) => baselineY - (meters / rangeM) * (baselineY - padding),
        [baselineY, rangeM]
    );

    const qrPoint =
        typeof data?.position?.lateral_x_m === "number" &&
        typeof data?.position?.forward_z_m === "number"
            ? {
                  x: toX(data.position.lateral_x_m),
                  y: toY(data.position.forward_z_m),
              }
            : null;
    const lidarDistance =
        typeof data?.lidar?.distance_m === "number"
            ? data.lidar.distance_m
            : undefined;
    const displayDistance =
        typeof lidarDistance === "number"
            ? lidarDistance
            : undefined;
    const distanceText =
        typeof displayDistance === "number"
            ? `${displayDistance.toFixed(2)} m`
            : "N/A";
    const sourceText =
        typeof displayDistance === "number" ? "LiDAR" : "N/A";

    const targetPoint =
        typeof data?.target?.x_m === "number" && typeof data?.target?.z_m === "number"
            ? {
                  x: toX(data.target.x_m),
                  y: toY(data.target.z_m),
              }
            : null;

    return (
        <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-elev)] shadow-[inset_0_0_0_1px_rgba(80,140,255,0.06)]">
            <svg viewBox={`0 0 ${width} ${height}`} className="h-[220px] w-full">
                <rect x="0" y="0" width={width} height={height} fill="#081321" />

                {Array.from({ length: 6 }).map((_, row) => {
                    const y = padding + ((height - padding * 2) / 5) * row;
                    return (
                        <line
                            key={`row-${row}`}
                            x1="0"
                            y1={y}
                            x2={width}
                            y2={y}
                            stroke="rgba(59,130,246,0.12)"
                            strokeWidth="1"
                        />
                    );
                })}

                {Array.from({ length: 6 }).map((_, col) => {
                    const x = padding + ((width - padding * 2) / 5) * col;
                    return (
                        <line
                            key={`col-${col}`}
                            x1={x}
                            y1="0"
                            x2={x}
                            y2={height}
                            stroke="rgba(59,130,246,0.12)"
                            strokeWidth="1"
                        />
                    );
                })}

                <line
                    x1={width / 2}
                    y1={padding}
                    x2={width / 2}
                    y2={baselineY}
                    stroke="#f8dc53"
                    strokeWidth="2.5"
                    strokeOpacity="0.95"
                />

                {targetPoint ? (
                    <>
                        <line
                            x1={width / 2}
                            y1={baselineY}
                            x2={targetPoint.x}
                            y2={targetPoint.y}
                            stroke="rgba(34,211,238,0.75)"
                            strokeDasharray="5 5"
                        />
                        <circle cx={targetPoint.x} cy={targetPoint.y} r="6" fill="#22d3ee" />
                    </>
                ) : null}

                {qrPoint ? (
                    <>
                        <line
                            x1={width / 2}
                            y1={baselineY}
                            x2={qrPoint.x}
                            y2={qrPoint.y}
                            stroke="rgba(255,122,69,0.9)"
                            strokeWidth="2"
                        />
                        <circle cx={qrPoint.x} cy={qrPoint.y} r="7" fill="#ff7a45" />
                        <text
                            x={qrPoint.x}
                            y={Math.max(qrPoint.y - 10, 18)}
                            textAnchor="middle"
                            fill="#ffd560"
                            fontSize="10"
                            fontWeight="700"
                        >
                            {data?.qr?.text || "QR"}
                        </text>
                    </>
                ) : (
                    <text
                        x={width / 2}
                        y="34"
                        textAnchor="middle"
                        fill="#ff7f7f"
                        fontSize="11"
                        fontWeight="700"
                    >
                        QR NOT FOUND
                    </text>
                )}

                <circle cx={width / 2} cy={baselineY} r="10" fill="#22d3ee" />
                <circle
                    cx={width / 2}
                    cy={baselineY}
                    r="16"
                    fill="none"
                    stroke="rgba(34,211,238,0.45)"
                    strokeWidth="2"
                />
            </svg>
            <div className="grid grid-cols-2 gap-2 border-t border-[var(--border)] px-3 py-2 text-xs">
                <div>
                    <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">Distance</div>
                    <div className="mt-0.5 font-semibold text-[var(--foreground)]">{distanceText}</div>
                </div>
                <div>
                    <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">Source</div>
                    <div className="mt-0.5 font-semibold text-[var(--foreground)]">{sourceText}</div>
                </div>
            </div>
        </div>
    );
}
