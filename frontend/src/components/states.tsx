import type { ReactNode } from "react";
import { DASH } from "../utils/format";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-ink-700/50 bg-ink-850/60 p-4 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-600 border-t-accent" />
      {label}
    </div>
  );
}

export function EmptyState({
  title = "No data",
  hint,
}: {
  title?: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-dashed border-ink-600/60 bg-ink-850/40 p-6 text-center">
      <div className="text-sm font-medium text-muted">{title}</div>
      {hint ? <div className="mt-1 text-xs text-muted/70">{hint}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Request failed",
  detail,
  onRetry,
}: {
  title?: string;
  detail?: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-lg border border-neg/30 bg-neg/5 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-neg">{title}</div>
        {onRetry ? (
          <button
            onClick={onRetry}
            className="rounded border border-ink-600 px-2.5 py-1 text-xs text-muted hover:text-accent"
          >
            Retry
          </button>
        ) : null}
      </div>
      {detail ? <div className="mt-2 whitespace-pre-wrap text-xs text-muted">{detail}</div> : null}
    </div>
  );
}

export function PageContainer({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex h-full flex-col">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-slate-100">{title}</h1>
          {subtitle ? <p className="mt-0.5 text-xs text-muted">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </header>
      <div className="flex-1">{children}</div>
    </section>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-lg border border-ink-700/50 bg-ink-850/60 ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-ink-700/50 px-4 py-2.5">
      <h2 className="text-sm font-medium text-slate-200">{title}</h2>
      {right}
    </div>
  );
}

export function Body({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`p-4 ${className}`}>{children}</div>;
}

export function Dash() {
  return <span className="text-muted/50">{DASH}</span>;
}
