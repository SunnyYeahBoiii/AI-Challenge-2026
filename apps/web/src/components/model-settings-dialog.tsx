"use client";

import { useEffect, useState } from "react";
import { getModelStatus, setActiveModel, type ModelStatus } from "@/lib/api";
import { Icon } from "./icon";
import { KeywordSearchOptions, type KeywordSearchConfig } from "./keyword-search-options";

interface ModelSettingsDialogProps {
  onClose: () => void;
  seekStepSeconds: number;
  onSeekStepSecondsChange: (seconds: number) => void;
  temporalWindowSeconds: number;
  onTemporalWindowSecondsChange: (seconds: number) => void;
  ocrSearchConfig: KeywordSearchConfig;
  onOcrSearchConfigChange: (config: KeywordSearchConfig) => void;
  asrSearchConfig: KeywordSearchConfig;
  onAsrSearchConfigChange: (config: KeywordSearchConfig) => void;
}

export function ModelSettingsDialog({
  onClose,
  seekStepSeconds,
  onSeekStepSecondsChange,
  temporalWindowSeconds,
  onTemporalWindowSecondsChange,
  ocrSearchConfig,
  onOcrSearchConfigChange,
  asrSearchConfig,
  onAsrSearchConfigChange,
}: ModelSettingsDialogProps) {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [collectionName, setCollectionName] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    getModelStatus()
      .then(({ status, available_models }) => {
        setStatus(status);
        setAvailableModels(available_models);
        setSelectedModel(status.model_id ?? available_models[0] ?? "");
        setCollectionName(status.collection_name ?? "");
      })
      .catch(() => setErrorMessage("Failed to load model status"));
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const handleLoad = async () => {
    if (!selectedModel) return;
    setBusy(true);
    setErrorMessage(null);
    try {
      const { status: initial } = await setActiveModel(selectedModel, collectionName.trim());
      setStatus(initial);
      if (initial.state === "error") {
        setErrorMessage(initial.error);
        setBusy(false);
        return;
      }
      // Poll until ready or error — avoids proxy / axios timeout on long loads.
      const start = Date.now();
      setElapsed(0);
      const timer = setInterval(() => setElapsed(Math.round((Date.now() - start) / 1000)), 1000);
      try {
        while (true) {
          await new Promise((r) => setTimeout(r, 1000));
          const { status: s } = await getModelStatus();
          setStatus(s);
          setCollectionName(s.collection_name ?? "");
          if (s.state === "ready") {
            setErrorMessage(null);
            break;
          }
          if (s.state === "error") {
            setErrorMessage(s.error ?? "Failed to load model");
            break;
          }
          if (Date.now() - start > 5 * 60 * 1000) {
            setErrorMessage("Load timed out after 5 minutes");
            break;
          }
        }
      } finally {
        clearInterval(timer);
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      setStatus((err as { response?: { data?: { status?: ModelStatus } } })?.response?.data?.status ?? null);
      setErrorMessage(msg ?? "Failed to load model");
    } finally {
      setBusy(false);
    }
  };

  const handleUnload = async () => {
    setBusy(true);
    setErrorMessage(null);
    try {
      const { status } = await setActiveModel(null);
      setStatus(status);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      setErrorMessage(msg ?? "Failed to unload model");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-2xl max-h-[calc(100vh-2rem)] border border-outline-variant flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-outline-variant">
          <h2 className="text-headline-sm text-on-surface font-bold">Setting</h2>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high rounded-full p-1 transition-colors"
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 flex flex-col gap-4 overflow-y-auto">
          <div className="flex items-center gap-2 text-body-sm">
            <span className="text-on-surface-variant">Active:</span>
            {status?.state === "ready" && (
              <span className="text-on-surface font-medium">{status.model_id}</span>
            )}
            {status?.state === "none" && <span className="text-on-surface-variant">none</span>}
            {status?.state === "loading" && <span className="text-on-surface-variant">loading…</span>}
            {status?.state === "error" && <span className="text-error">error</span>}
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-label-md text-on-surface-variant">Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={busy || availableModels.length === 0}
              className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 text-body-sm outline-none focus:border-primary transition-colors"
            >
              {availableModels.map((modelId) => (
                <option key={modelId} value={modelId}>
                  {modelId}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1 border-t border-outline-variant pt-4">
            <label htmlFor="keyboard-seek-step" className="text-label-md text-on-surface-variant">
              Keyboard seek step (seconds)
            </label>
            <input
              id="keyboard-seek-step"
              type="number"
              min={0.05}
              max={10}
              step={0.05}
              value={seekStepSeconds}
              onChange={(event) => {
                const value = Number(event.target.value);
                if (Number.isFinite(value)) {
                  onSeekStepSecondsChange(Math.min(10, Math.max(0.05, value)));
                }
              }}
              className="w-36 bg-surface-container-low border border-outline-variant rounded px-3 py-2 text-body-sm outline-none focus:border-primary transition-colors"
            />
            <p className="text-label-xs text-on-surface-variant">
              Alt + Shift + ← / → seeks by this amount. Default: 0.2 seconds.
            </p>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="temporal-window" className="text-label-md text-on-surface-variant">
              Max consecutive gap (seconds)
            </label>
            <input
              id="temporal-window"
              type="number"
              min={0.1}
              step={1}
              value={temporalWindowSeconds}
              onChange={(event) =>
                onTemporalWindowSecondsChange(Math.max(0.1, Number(event.target.value) || 0.1))
              }
              className="w-36 bg-surface-container-low border border-outline-variant rounded px-3 py-2 text-body-sm outline-none focus:border-primary transition-colors"
            />
            <p className="text-label-xs text-on-surface-variant">
              Limits the gap between consecutive query matches in temporal search.
            </p>
          </div>

          <section className="border-t border-outline-variant pt-4">
            <div className="mb-3">
              <h3 className="text-label-md text-on-surface-variant">OCR & ASR keyword matching</h3>
              <p className="text-label-xs text-on-surface-variant">
                Applies to every OCR or ASR keyword filter in this session.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-label-sm text-on-surface">OCR</p>
                <KeywordSearchOptions
                  source="OCR"
                  config={ocrSearchConfig}
                  onChange={onOcrSearchConfigChange}
                />
              </div>
              <div>
                <p className="mb-1 text-label-sm text-on-surface">ASR</p>
                <KeywordSearchOptions
                  source="ASR"
                  config={asrSearchConfig}
                  onChange={onAsrSearchConfigChange}
                />
              </div>
            </div>
          </section>

          <div className="flex flex-col gap-1">
            <label className="text-label-md text-on-surface-variant">
              Milvus collection <span className="text-on-surface-variant/60">(optional override)</span>
            </label>
            <input
              type="text"
              value={collectionName}
              onChange={(e) => setCollectionName(e.target.value)}
              disabled={busy}
              placeholder="default: data_frames_<model_id>"
              className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 text-body-sm outline-none focus:border-primary transition-colors placeholder:text-on-surface-variant/50"
            />
          </div>

          {errorMessage && (
            <div className="flex items-center gap-2 text-sm text-error bg-error-container/30 p-2 rounded">
              <Icon name="error" size={16} />
              {errorMessage}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-outline-variant">
          <button
            onClick={handleUnload}
            disabled={busy || !status?.model_id}
            className="px-4 py-2 rounded border border-outline-variant text-label-md text-on-surface-variant hover:bg-surface-container transition-colors disabled:opacity-50"
          >
            Unload
          </button>
          <button
            onClick={handleLoad}
            disabled={busy || !selectedModel}
            className="px-4 py-2 rounded bg-primary-container text-on-primary-container text-label-md hover:bg-primary-fixed transition-colors disabled:opacity-50"
          >
            {busy ? `Loading... ${elapsed}s` : "Load"}
          </button>
        </div>
      </div>
    </div>
  );
}
