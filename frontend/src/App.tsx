import { HashRouter, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Dashboard } from "@/components/Dashboard";
import { VaultExplorer } from "@/components/VaultExplorer";
import { useSessionToken } from "@/hooks/useSessionToken";

function TokenGate({ children }: { children: React.ReactNode }) {
  const { ready, error } = useSessionToken();
  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="glass p-6 max-w-md">
          <h2 className="text-accent-err font-mono uppercase text-xs tracking-widest mb-3">
            bridge unreachable
          </h2>
          <p className="text-ink-muted text-sm font-mono break-words">
            Could not read <code>~/MYKO/.session_token</code>. Is <code>python -m backend.bridge</code> running?
          </p>
          <p className="text-ink-muted text-xs font-mono mt-4 opacity-60 break-all">{error}</p>
        </div>
      </div>
    );
  }
  if (!ready) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-ink-muted font-mono text-xs uppercase tracking-widest">
          initializing…
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <HashRouter>
      <Layout>
        <TokenGate>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/vault" element={<VaultExplorer />} />
          </Routes>
        </TokenGate>
      </Layout>
    </HashRouter>
  );
}
