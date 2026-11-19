import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  return (
    <button
      className={cx(
        "inline-flex h-9 items-center justify-center gap-2 rounded-md px-3.5 text-sm font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-accent text-white hover:bg-[#1a4385]",
        variant === "secondary" && "border border-border bg-surface text-foreground hover:bg-background",
        variant === "ghost" && "text-muted hover:bg-background hover:text-foreground",
        variant === "danger" && "text-negative hover:bg-negative-soft",
        className,
      )}
      {...props}
    />
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-foreground">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

const control =
  "h-9 w-full rounded-md border border-border bg-surface px-3 text-sm text-foreground placeholder:text-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft disabled:bg-background disabled:text-muted";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(control, className)} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx(control, "pr-8", className)} {...props} />;
}

export function Card({ title, action, children, className }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-border bg-surface", className)}>
      {title && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-3.5">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "accent" | "positive" | "warning" | "negative"; children: ReactNode }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        tone === "neutral" && "bg-background text-muted",
        tone === "accent" && "bg-accent-soft text-accent",
        tone === "positive" && "bg-positive-soft text-positive",
        tone === "warning" && "bg-warning-soft text-warning",
        tone === "negative" && "bg-negative-soft text-negative",
      )}
    >
      {children}
    </span>
  );
}

export function Alert({ tone = "negative", children }: { tone?: "negative" | "positive" | "warning"; children: ReactNode }) {
  return (
    <div
      role={tone === "negative" ? "alert" : "status"}
      className={cx(
        "rounded-md px-3 py-2 text-sm",
        tone === "negative" && "bg-negative-soft text-negative",
        tone === "positive" && "bg-positive-soft text-positive",
        tone === "warning" && "bg-warning-soft text-warning",
      )}
    >
      {children}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex h-full min-h-32 flex-col items-center justify-center rounded-md border border-dashed border-border px-6 py-8 text-center">
      <p className="text-sm font-medium text-foreground">{title}</p>
      {children && <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted">{children}</p>}
    </div>
  );
}

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2 text-[15px] font-semibold tracking-tight text-foreground">
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
        <rect width="24" height="24" rx="5" fill="var(--foreground)" />
        <path d="M5 16l4-5 3.5 3 6.5-8" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      CostPilot <span className="font-normal text-muted">AI</span>
    </span>
  );
}
