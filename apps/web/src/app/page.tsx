"use client";

import { useState, useCallback, useEffect } from "react";
import { FilterPanel, type SearchFilter } from "@/components/filter-panel";
import { ResultsPanel } from "@/components/results-panel";
import { FrameDetailDialog } from "@/components/frame-detail-dialog";
import { DresSettingsDialog } from "@/components/dres-settings-dialog";
import { SubmissionConfirmationDialog } from "@/components/submission-confirmation-dialog";
import { Icon } from "@/components/icon";
import type { FrameResult } from "@/lib/api";
import { multiBoxSearch, searchVideoFrames, healthCheck } from "@/lib/api";

function sortFrames(frames: FrameResult[]): FrameResult[] {
  return [...frames].sort((a, b) => b.score - a.score);
}

export default function Home() {
  const [frames, setFrames] = useState<FrameResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedFrame, setSelectedFrame] = useState<FrameResult | null>(null);
  const [showDresSettings, setShowDresSettings] = useState(false);
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false);
  const [dresSessionId, setDresSessionId] = useState<string | null>(null);
  const [dresUsername, setDresUsername] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"grouped" | "continuous">("grouped");
  const [healthStatus, setHealthStatus] = useState<string>("loading");

  // Submission state
  const [submissionType, setSubmissionType] = useState<"track" | "qa" | "kis">("kis");
  const [frameId, setFrameId] = useState("");
  const [videoId, setVideoId] = useState("");
  const [timeSec, setTimeSec] = useState("");

  useEffect(() => {
    healthCheck()
      .then((h) => setHealthStatus(h.status))
      .catch(() => setHealthStatus("error"));
  }, []);

  useEffect(() => {
    setDresSessionId(sessionStorage.getItem("dresSessionId"));
    setDresUsername(sessionStorage.getItem("dresUsername"));
  }, []);

  const handleDresLogin = useCallback((sessionId: string, username: string) => {
    sessionStorage.setItem("dresSessionId", sessionId);
    sessionStorage.setItem("dresUsername", username);
    setDresSessionId(sessionId);
    setDresUsername(username);
  }, []);

  const handleDresLogout = useCallback(() => {
    const sessionId = dresSessionId;
    sessionStorage.removeItem("dresSessionId");
    sessionStorage.removeItem("dresUsername");
    setDresSessionId(null);
    setDresUsername(null);
    if (sessionId) {
      fetch("/api/dres/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId }),
      }).catch(() => {});
    }
  }, [dresSessionId]);

  const handleSearch = useCallback(async (newFilter: SearchFilter) => {
    setIsLoading(true);
    setSearchError(null);
    try {
      if (newFilter.videoId) {
        const data = await searchVideoFrames(newFilter.videoId);
        setFrames(sortFrames(data.results));
      } else {
        const enabledQueries = newFilter.queries.filter(
          (q) => q.enabled && (q.content || q.tags?.length)
        );
        const boxQueries = enabledQueries.map((q) => ({
          text: q.type === "text" ? q.content : undefined,
          image: q.type === "image" ? q.content : undefined,
          tags: q.tags?.length ? q.tags : undefined,
          tag_match_mode: q.tags?.length ? (q.tagMatchMode ?? "and") : undefined,
          ocr_keywords: q.ocrKeywords?.length ? q.ocrKeywords : undefined,
          asr_keywords: q.asrKeywords?.length ? q.asrKeywords : undefined,
          ocr_match_mode: q.ocrKeywords?.length ? (q.ocrMatchMode ?? "and") : undefined,
          asr_match_mode: q.asrKeywords?.length ? (q.asrMatchMode ?? "and") : undefined,
          topk: q.topK ?? 100,
          enhance: q.enhance ?? false,
        }));
        // Request-level topk drives merge_rrf / merge_temporal; box topk alone is ignored.
        const topk = Math.max(...enabledQueries.map((q) => q.topK ?? 100), 1);
        const data = await multiBoxSearch({
          box_queries: boxQueries,
          mode: newFilter.mode,
          topk,
        });
        setFrames(sortFrames(data.results));
      }
    } catch (error) {
      console.error("Search failed:", error);
      setSearchError(error instanceof Error ? error.message : "Search failed. Check the API connection and try again.");
      setFrames([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleClear = useCallback(() => {
    setFrames([]);
    setSearchError(null);
    setSelectedFrame(null);
    setFrameId("");
    setVideoId("");
    setTimeSec("");
  }, []);

  const handleFrameSelect = useCallback((frame: FrameResult) => {
    setFrameId(String(frame.frame_idx));
    setVideoId(frame.video_id);
    setTimeSec(frame.pts_time.toFixed(1));
  }, []);

  const handleFrameDetail = useCallback((frame: FrameResult) => {
    setSelectedFrame(frame);
  }, []);

  const canSubmit = frameId.trim().length > 0 && videoId.trim().length > 0;

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <FilterPanel
        onSearch={handleSearch}
        onClear={handleClear}
        onValidationError={setSearchError}
        isLoading={isLoading}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top Bar */}
        <header className="bg-surface-container-lowest border-b border-outline-variant flex justify-between items-center px-container-padding w-full h-topbar-height shrink-0 z-20">
          <div className="flex items-center gap-6">
            <span className="text-headline-sm font-bold text-on-surface tracking-tight">
              Frame Seeker
            </span>
            <div className="h-6 w-px bg-outline-variant hidden md:block" />

            {/* View Mode Toggle */}
            {frames.length > 0 && (
              <div className="flex items-center gap-2 mr-2 bg-surface-container-low p-1 rounded-lg border border-outline-variant">
                <button
                  onClick={() => setViewMode("grouped")}
                  className={`px-3 py-1 rounded text-label-sm transition-colors ${
                    viewMode === "grouped"
                      ? "bg-primary-container text-on-primary-container"
                      : "hover:bg-surface-variant text-on-surface-variant"
                  }`}
                >
                  Grouped
                </button>
                <button
                  onClick={() => setViewMode("continuous")}
                  className={`px-3 py-1 rounded text-label-sm transition-colors ${
                    viewMode === "continuous"
                      ? "bg-primary-container text-on-primary-container"
                      : "hover:bg-surface-variant text-on-surface-variant"
                  }`}
                >
                  Continuous
                </button>
              </div>
            )}

            {/* Submission Type Radio */}
            <div className="flex items-center gap-2 mr-4 bg-surface-container-low p-1 rounded-lg border border-outline-variant">
              {(["track", "qa", "kis"] as const).map((type) => (
                <label key={type} className="flex items-center gap-1 px-2 cursor-pointer">
                  <input
                    type="radio"
                    name="search_type"
                    checked={submissionType === type}
                    onChange={() => setSubmissionType(type)}
                    className="text-primary focus:ring-primary h-3 w-3"
                  />
                  <span className="text-label-sm text-on-surface-variant">
                    {type.toUpperCase()}
                  </span>
                </label>
              ))}
            </div>

          </div>

          <div className="flex items-center gap-3">
            {dresSessionId && dresUsername ? (
              <div className="flex items-center gap-1.5">
                <span
                  title="Logged in to DRES"
                  className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest text-label-md text-on-surface-variant"
                >
                  <Icon name="groups" size={18} />
                  {dresUsername}
                </span>
                <button
                  onClick={handleDresLogout}
                  title="Log out of DRES"
                  className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
                >
                  <Icon name="logout" size={18} />
                  Logout
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowDresSettings(true)}
                className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
              >
                <Icon name="settings" size={18} />
                DRES Settings
              </button>
            )}
            <div className="flex items-center gap-1.5 ml-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  healthStatus === "healthy" ? "bg-green-500" : healthStatus === "degraded" ? "bg-yellow-500" : "bg-gray-400"
                }`}
              />
              <span className="text-label-sm text-on-surface-variant">
                {healthStatus === "healthy" ? "API OK" : healthStatus === "degraded" ? "Degraded" : "..."}
              </span>
            </div>
          </div>
        </header>

        {/* Search error banner */}
        {searchError && (
          <div
            role="alert"
            className="flex items-center gap-2 px-container-padding py-2.5 bg-error-container text-on-error-container text-body-sm border-b border-outline-variant"
          >
            <Icon name="error" size={18} />
            <span className="flex-1">{searchError}</span>
            <button
              onClick={() => setSearchError(null)}
              aria-label="Dismiss error"
              className="hover:opacity-70 transition-opacity"
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        )}

        {/* Results */}
        <ResultsPanel
          frames={frames}
          viewMode={viewMode}
          onFrameSelect={handleFrameSelect}
          onFrameDetail={handleFrameDetail}
          isLoading={isLoading}
          submissionType={submissionType}
          dresSessionId={dresSessionId}
        />
      </div>

      {/* Dialogs */}
      {selectedFrame && (
        <FrameDetailDialog
          frame={selectedFrame}
          submissionType={submissionType}
          onSubmissionTypeChange={setSubmissionType}
          onClose={() => setSelectedFrame(null)}
          onSubmit={(submission) => {
            setFrameId(submission.frameId);
            setVideoId(submission.videoId);
            setTimeSec(submission.timeSec);
            setSelectedFrame(null);
            setShowSubmitConfirm(true);
          }}
        />
      )}

      {showDresSettings && (
        <DresSettingsDialog
          onClose={() => setShowDresSettings(false)}
          onLoginSuccess={handleDresLogin}
        />
      )}

      {showSubmitConfirm && canSubmit && (
        <SubmissionConfirmationDialog
          frameId={frameId.trim()}
          videoId={videoId.trim()}
          timestamp={Number.parseFloat(timeSec) || 0}
          submissionType={submissionType}
          sessionId={dresSessionId}
          onClose={() => setShowSubmitConfirm(false)}
        />
      )}
    </div>
  );
}
