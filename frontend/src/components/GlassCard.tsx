import { ReactNode, CSSProperties } from "react";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  accentColor?: string;
  stale?: boolean;
  title?: string;
}

export function GlassCard({ children, className = "", accentColor, stale, title }: GlassCardProps) {
  const style: CSSProperties = accentColor
    ? ({ ["--accent" as string]: accentColor } as CSSProperties)
    : {};

  return (
    <div
      className={`glass ${accentColor ? "glass-glow-top" : ""} p-5 relative ${className}`}
      style={style}
    >
      {title && (
        <div className="flex items-center justify-between mb-3">
          <h3
            className="text-xs uppercase tracking-widest text-ink-muted font-mono"
            style={{ color: accentColor ?? undefined, opacity: 0.9 }}
          >
            {title}
          </h3>
          {stale && (
            <span
              className="text-[10px] uppercase tracking-widest font-mono"
              style={{ color: "#EF4444" }}
              title="Last known data — could not reach bridge"
            >
              stale
            </span>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
