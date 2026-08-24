"use client";

import { useEffect, useState } from "react";
import { Icon } from "./icon";

interface DresEvaluation {
  id: string;
  status?: string;
}

interface DresSettingsDialogProps {
  /** Existing session, if the dialog is reopened while already logged in. */
  sessionId?: string | null;
  username?: string | null;
  /** Currently saved evaluation (contest) run, if any. */
  evaluationId?: string | null;
  dresUrl: string;
  onClose: () => void;
  onLoginSuccess: (sessionId: string, username: string) => void;
  onEvaluationSelect: (evaluationId: string) => void;
  onServerChange: (dresUrl: string) => void;
}

export function DresSettingsDialog({
  sessionId,
  username: initialUsername,
  evaluationId,
  dresUrl,
  onClose,
  onLoginSuccess,
  onEvaluationSelect,
  onServerChange,
}: DresSettingsDialogProps) {
  const [username, setUsername] = useState(initialUsername ?? "");
  const [password, setPassword] = useState("");
  const [loginStatus, setLoginStatus] = useState<"idle" | "loading" | "success" | "error">(
    sessionId ? "success" : "idle",
  );
  const [activeSessionId, setActiveSessionId] = useState<string | null>(sessionId ?? null);

  const [evaluations, setEvaluations] = useState<DresEvaluation[]>([]);
  const [evalStatus, setEvalStatus] = useState<"idle" | "loading" | "loaded" | "error">("idle");
  const [selectedEvalId, setSelectedEvalId] = useState(evaluationId ?? "");
  const [serverUrl, setServerUrl] = useState(dresUrl);
  const [serverUrlError, setServerUrlError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeSessionId) return;
    setEvalStatus("loading");
    const params = new URLSearchParams({ session: activeSessionId });
    if (dresUrl) params.set("dresUrl", dresUrl);
    fetch(`/api/dres/evaluations?${params.toString()}`)
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error?.description || "Failed to load evaluations");
        setEvaluations(data.evaluations || []);
        setEvalStatus("loaded");
      })
      .catch(() => setEvalStatus("error"));
  }, [activeSessionId, dresUrl]);

  const normalizeServerUrl = (): string | null => {
    const candidate = serverUrl.trim().replace(/\/+$/, "");
    if (!candidate) return "";
    try {
      const parsed = new URL(candidate);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") throw new Error();
      return candidate;
    } catch {
      setServerUrlError("Enter an absolute http(s) URL.");
      return null;
    }
  };

  const handleUseServer = () => {
    const normalized = normalizeServerUrl();
    if (normalized === null) return;
    setServerUrl(normalized);
    setServerUrlError(null);
    onServerChange(normalized);
    setActiveSessionId(null);
    setEvaluations([]);
    setSelectedEvalId("");
    setPassword("");
    setLoginStatus("idle");
  };

  const handleLogin = async () => {
    const normalized = normalizeServerUrl();
    if (normalized === null) return;
    setLoginStatus("loading");
    try {
      const res = await fetch("/api/dres/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, dresUrl: normalized || undefined }),
      });
      const data = await res.json();
      if (res.ok && data.sessionId) {
        const resolvedUsername = data.username || username;
        if (normalized !== dresUrl) onServerChange(normalized);
        onLoginSuccess(data.sessionId, resolvedUsername);
        setActiveSessionId(data.sessionId);
        setLoginStatus("success");
      } else {
        setLoginStatus("error");
      }
    } catch {
      setLoginStatus("error");
    }
  };

  const handleSaveEvaluation = () => {
    if (!selectedEvalId) return;
    onEvaluationSelect(selectedEvalId);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="DRES settings"
        className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-lg border border-outline-variant"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-outline-variant">
          <h2 className="text-headline-sm text-on-surface font-bold">
            DRES Settings
          </h2>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high rounded-full p-1 transition-colors"
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="dres-server-url" className="text-label-md text-on-surface-variant">
              DRES server URL
            </label>
            <div className="flex gap-2">
              <input
                id="dres-server-url"
                type="url"
                value={serverUrl}
                onChange={(event) => {
                  setServerUrl(event.target.value);
                  setServerUrlError(null);
                }}
                placeholder="Use server configured by the deployment"
                className="min-w-0 flex-1 bg-surface-container-low border border-outline-variant rounded px-3 py-2 text-body-sm outline-none focus:border-primary transition-colors"
              />
              <button
                type="button"
                onClick={handleUseServer}
                className="shrink-0 px-3 py-2 rounded border border-outline-variant text-label-md hover:bg-surface-container transition-colors"
              >
                Use server
              </button>
            </div>
            <p className="text-label-xs text-on-surface-variant">
              Switching server clears the current DRES session and evaluation.
            </p>
            {serverUrlError && <p className="text-label-xs text-error">{serverUrlError}</p>}
          </div>
          {!activeSessionId && (
            <>
              <div className="flex flex-col gap-1">
                <label className="text-label-md text-on-surface-variant">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 text-body-sm outline-none focus:border-primary transition-colors"
                  placeholder="Enter username"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-label-md text-on-surface-variant">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 text-body-sm outline-none focus:border-primary transition-colors"
                  placeholder="Enter password"
                  onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                />
              </div>

              {loginStatus === "error" && (
                <div className="flex items-center gap-2 text-sm text-error bg-error-container/30 p-2 rounded">
                  <Icon name="error" size={16} />
                  Connection failed
                </div>
              )}

              <button
                onClick={handleLogin}
                disabled={loginStatus === "loading" || !username || !password}
                className="px-4 py-2 rounded bg-primary-container text-on-primary-container text-label-md hover:bg-primary-fixed transition-colors disabled:opacity-50 self-end"
              >
                {loginStatus === "loading" ? "Connecting..." : "Login"}
              </button>
            </>
          )}

          {activeSessionId && (
            <>
              <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 p-2 rounded">
                <Icon name="check_circle" size={16} />
                Connected successfully
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-label-md text-on-surface-variant">
                  Evaluation (running contest)
                </label>
                {evalStatus === "loading" && (
                  <div className="text-body-sm text-on-surface-variant">Loading running evaluations…</div>
                )}
                {evalStatus === "error" && (
                  <div className="flex items-center gap-2 text-sm text-error bg-error-container/30 p-2 rounded">
                    <Icon name="error" size={16} />
                    Failed to load evaluations
                  </div>
                )}
                {evalStatus === "loaded" && evaluations.length === 0 && (
                  <div className="text-body-sm text-on-surface-variant">No running evaluation found.</div>
                )}
                {evalStatus === "loaded" && evaluations.length > 0 && (
                  <select
                    value={selectedEvalId}
                    onChange={(e) => setSelectedEvalId(e.target.value)}
                    className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 text-body-sm outline-none focus:border-primary transition-colors"
                  >
                    <option value="" disabled>
                      Select an evaluation…
                    </option>
                    {evaluations.map((ev) => (
                      <option key={ev.id} value={ev.id}>
                        {ev.id} ({ev.status ?? "ACTIVE"})
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-outline-variant">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border border-outline-variant text-label-md text-on-surface-variant hover:bg-surface-container transition-colors"
          >
            Cancel
          </button>
          {activeSessionId && (
            <button
              onClick={handleSaveEvaluation}
              disabled={!selectedEvalId}
              className="px-4 py-2 rounded bg-primary-container text-on-primary-container text-label-md hover:bg-primary-fixed transition-colors disabled:opacity-50"
            >
              Save
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
