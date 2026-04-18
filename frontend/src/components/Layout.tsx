import { ReactNode } from "react";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="w-screen h-screen bg-ink-bg text-ink-fg overflow-hidden relative">
      {children}
    </div>
  );
}
