"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  Clock3,
  Loader2,
  RefreshCw,
  Route,
  TableProperties,
} from "lucide-react";
import { RobotAPI, robotId } from "@/app/lib/robotApi";

type EvaluationResponse = {
  success?: boolean;
  robot_id?: string;
  run_meta?: Record<string, unknown> | null;
  summary?: Record<string, unknown> | null;
  derived_metrics?: Record<string, unknown> | null;
  paper_tables?: {
    table_i_localization?: Record<string, unknown> | null;
    table_ii_qr_ablation?: Record<string, unknown> | null;
    table_iii_navigation?: Record<string, unknown> | null;
  } | null;
  raw_metrics?: Record<string, unknown> | null;
};

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return value.toString();
    return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (typeof value === "boolean") return value ? "True" : "False";
  return String(value);
}

function formatLabel(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function StatCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-2 flex items-center gap-2 text-[var(--muted)] text-xs font-medium">
        <div className="rounded-lg bg-[var(--surface-2)] p-1.5">{icon}</div>
        <span>{label}</span>
      </div>
      <div className="text-2xl font-bold text-[var(--foreground)]">{value}</div>
      {hint ? <div className="mt-1 text-xs text-[var(--muted)]">{hint}</div> : null}
    </div>
  );
}

function MetricTable({
  title,
  subtitle,
  rows,
}: {
  title: string;
  subtitle?: string;
  rows: Array<{ label: string; value: React.ReactNode }>;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
      <div className="border-b border-[var(--border)] px-5 py-4">
        <div className="text-sm font-semibold text-[var(--foreground)]">{title}</div>
        {subtitle ? <div className="mt-1 text-xs text-[var(--muted)]">{subtitle}</div> : null}
      </div>
      <div className="divide-y divide-[var(--border)]">
        {rows.map((row) => (
          <div key={row.label} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-3 text-sm">
            <div className="text-[var(--muted)]">{row.label}</div>
            <div className="text-right font-medium text-[var(--foreground)]">{row.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TableSupportBadge({ supported }: { supported: boolean }) {
  return supported ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-400">
      <CheckCircle2 size={13} />
      Supported
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-400">
      <AlertCircle size={13} />
      Partial
    </span>
  );
}

export default function EvaluationPage() {
  const [data, setData] = useState<EvaluationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState("");
  const [lastRefresh, setLastRefresh] = useState("-");

  const refresh = useCallback(async () => {
    try {
      setErrorText("");
      const next = (await RobotAPI.evaluationMetrics()) as EvaluationResponse;
      setData(next);
      setLastRefresh(
        new Date().toLocaleTimeString("vi-VN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      );
    } catch (err: any) {
      setErrorText(err?.message || "Failed to load evaluation metrics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const summary = data?.summary ?? {};
  const derived = data?.derived_metrics ?? {};
  const runMeta = data?.run_meta ?? {};
  const paperTables = data?.paper_tables ?? {};
  const tableI = paperTables.table_i_localization ?? {};
  const tableII = paperTables.table_ii_qr_ablation ?? {};
  const tableIII = paperTables.table_iii_navigation ?? {};

  const derivedEntries = Object.entries(derived);
  const metaEntries = Object.entries(runMeta);

  return (
    <section className="min-h-screen p-5 text-[var(--foreground)]">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="gradient-title text-2xl">Evaluation</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Paper-mapped evaluation metrics for <span className="text-blue-300">{data?.robot_id || robotId}</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1 text-xs text-[var(--foreground)]/70">
            Last refresh: {lastRefresh}
          </span>
          <button
            onClick={refresh}
            disabled={loading}
            className="cursor-pointer inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm hover:bg-[var(--surface-2)] disabled:opacity-50"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            Refresh
          </button>
        </div>
      </div>

      {errorText ? (
        <div className="mt-5 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {errorText}
        </div>
      ) : null}

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Run Duration"
          value={`${formatValue(summary.run_duration_sec)} s`}
          hint="summary.run_duration_sec"
          icon={<Clock3 size={16} className="text-cyan-400" />}
        />
        <StatCard
          label="Trajectory Samples"
          value={formatValue(summary.trajectory_samples)}
          hint="summary.trajectory_samples"
          icon={<Route size={16} className="text-emerald-400" />}
        />
        <StatCard
          label="Path Length"
          value={`${formatValue(derived.path_length_m)} m`}
          hint="derived_metrics.path_length_m"
          icon={<BarChart3 size={16} className="text-violet-400" />}
        />
        <StatCard
          label="Final Drift"
          value={`${formatValue(derived.final_drift_from_origin_m)} m`}
          hint="derived_metrics.final_drift_from_origin_m"
          icon={<TableProperties size={16} className="text-orange-400" />}
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <MetricTable
          title="Run Metadata"
          subtitle="Context attached to the current evaluation run"
          rows={
            metaEntries.length
              ? metaEntries.map(([key, value]) => ({
                  label: formatLabel(key),
                  value: formatValue(value),
                }))
              : [{ label: "Metadata", value: "N/A" }]
          }
        />

        <MetricTable
          title="Summary"
          subtitle="Direct counters returned by the backend evaluation endpoint"
          rows={[
            { label: "Run Duration Sec", value: formatValue(summary.run_duration_sec) },
            { label: "Trajectory Samples", value: formatValue(summary.trajectory_samples) },
            { label: "Mission Count", value: formatValue(summary.mission_count) },
            { label: "Completed Missions", value: formatValue(summary.completed_missions) },
            { label: "Failed Or Aborted Missions", value: formatValue(summary.failed_or_aborted_missions) },
          ]}
        />
      </div>

      <div className="mt-5 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <div className="border-b border-[var(--border)] px-5 py-4">
          <div className="text-sm font-semibold text-[var(--foreground)]">Derived Metrics</div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            Values computed by backend from trajectory and raw robot metrics
          </div>
        </div>
        <div className="grid grid-cols-1 gap-x-6 gap-y-0 md:grid-cols-2 xl:grid-cols-3">
          {derivedEntries.length ? (
            derivedEntries.map(([key, value]) => (
              <div
                key={key}
                className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 border-b border-[var(--border)] px-5 py-3 text-sm last:border-b-0"
              >
                <div className="text-[var(--muted)]">{formatLabel(key)}</div>
                <div className="text-right font-medium text-[var(--foreground)]">{formatValue(value)}</div>
              </div>
            ))
          ) : (
            <div className="px-5 py-4 text-sm text-[var(--muted)]">No derived metrics available.</div>
          )}
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
          <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
            <div>
              <div className="text-sm font-semibold text-[var(--foreground)]">Table I Localization</div>
              <div className="mt-1 text-xs text-[var(--muted)]">Mapped to the localization table in the paper</div>
            </div>
            <TableSupportBadge supported={true} />
          </div>
          <div className="divide-y divide-[var(--border)]">
            {Object.entries(tableI).map(([key, value]) => (
              <div key={key} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-3 text-sm">
                <div className="text-[var(--muted)]">{formatLabel(key)}</div>
                <div className="text-right font-medium text-[var(--foreground)]">{formatValue(value)}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
          <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
            <div>
              <div className="text-sm font-semibold text-[var(--foreground)]">Table II QR Ablation</div>
              <div className="mt-1 text-xs text-[var(--muted)]">QR weighting and ablation data mapped for FE</div>
            </div>
            <TableSupportBadge supported={Boolean(tableII.supported)} />
          </div>
          <div className="divide-y divide-[var(--border)]">
            {Object.entries(tableII).map(([key, value]) => (
              <div key={key} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-3 text-sm">
                <div className="text-[var(--muted)]">{formatLabel(key)}</div>
                <div className="text-right font-medium text-[var(--foreground)]">{formatValue(value)}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
          <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
            <div>
              <div className="text-sm font-semibold text-[var(--foreground)]">Table III Navigation</div>
              <div className="mt-1 text-xs text-[var(--muted)]">Mission-level navigation metrics aligned with the paper</div>
            </div>
            <TableSupportBadge supported={Boolean(tableIII.supported)} />
          </div>
          <div className="divide-y divide-[var(--border)]">
            {Object.entries(tableIII).map(([key, value]) => (
              <div key={key} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-3 text-sm">
                <div className="text-[var(--muted)]">{formatLabel(key)}</div>
                <div className="text-right font-medium text-[var(--foreground)]">{formatValue(value)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
