"use client";

import { useState } from "react";
import { Icon } from "./icon";

interface DresSettingsDialogProps {
  onClose: () => void;
}

export function DresSettingsDialog({ onClose }: DresSettingsDialogProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

  const handleLogin = async () => {
    setStatus("loading");
    try {
      const res = await fetch("/api/dres/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        setStatus("success");
      } else {
        setStatus("error");
      }
    } catch {
      setStatus("error");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-labelledby="dres-settings-title" className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-lg border border-outline-variant">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-outline-variant">
          <h2 id="dres-settings-title" className="font-headline-sm text-headline-sm text-on-surface font-bold">
            DRES Settings
          </h2>
          <button
            aria-label="Close DRES settings"
            onClick={onClose}
            className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high rounded-full p-1 transition-colors"
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="dres-username" className="font-label-md text-label-md text-on-surface-variant">Username</label>
            <input
              id="dres-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 font-body-sm text-body-sm outline-none focus:border-primary transition-colors"
              placeholder="Enter username"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="dres-password" className="font-label-md text-label-md text-on-surface-variant">Password</label>
            <input
              id="dres-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 font-body-sm text-body-sm outline-none focus:border-primary transition-colors"
              placeholder="Enter password"
            />
          </div>

          {status === "success" && (
            <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 p-2 rounded">
              <Icon name="check_circle" size={16} />
              Connected successfully
            </div>
          )}
          {status === "error" && (
            <div className="flex items-center gap-2 text-sm text-error bg-error-container/30 p-2 rounded">
              <Icon name="error" size={16} />
              Connection failed
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-outline-variant">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border border-outline-variant font-label-md text-label-md text-on-surface-variant hover:bg-surface-container transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleLogin}
            disabled={status === "loading"}
            className="px-4 py-2 rounded bg-primary-container text-on-primary-container font-label-md text-label-md hover:bg-opacity-90 transition-colors disabled:opacity-50"
          >
            {status === "loading" ? "Connecting..." : "Login"}
          </button>
        </div>
      </div>
    </div>
  );
}
