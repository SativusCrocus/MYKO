import { ReactNode } from "react";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="w-screen h-screen bg-ink-bg text-ink-fg overflow-hidden relative">
      <header className="absolute top-0 left-0 right-0 z-20 flex items-center gap-3 px-5 py-3 pointer-events-none">
        <img
          src="/logo.svg"
          alt="MYKO"
          className="w-8 h-8 drop-shadow-[0_0_12px_rgba(0,240,255,0.45)]"
        />
        <div className="font-mono text-ink-fg text-sm tracking-[0.35em] font-semibold">MYKO</div>
        <div className="font-mono text-ink-muted text-[10px] tracking-[0.3em] opacity-70 ml-1">
          SOVEREIGN · LIFE · OS
        </div>
      </header>
      {children}
    </div>
  );
}
