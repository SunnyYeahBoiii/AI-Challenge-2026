"use client";

import { useState, useCallback, useEffect } from "react";
import { FilterPanel, type SearchFilter } from "@/components/filter-panel";
import { ResultsPanel } from "@/components/results-panel";
import { FrameDetailDialog } from "@/components/frame-detail-dialog";
import { DresSettingsDialog } from "@/components/dres-settings-dialog";
import { SubmissionConfirmationDialog } from "@/components/submission-confirmation-dialog";
import { Icon } from "@/components/icon";
import type { FrameResult } from "@/lib/api";
import { searchText, searchVideoFrames, healthCheck } from "@/lib/api";

export default function Home() {
  const [filter, setFilter] = useState<SearchFilter | null>(null);
  const [frames, setFrames] = useState<FrameResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedFrame, setSelectedFrame] = useState<FrameResult | null>(null);
  const [submissionFrame, setSubmissionFrame] = useState<FrameResult | null>(null);
  const [showDresSettings, setShowDresSettings] = useState(false);
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false);
  const [viewMode, setViewMode] = useState<"grouped" | "continuous">("grouped");
  const [healthStatus, setHealthStatus] = useState<string>("loading");

  // Submission state
  const [submissionType, setSubmissionType] = useState<"track" | "qa" | "kis">("kis");
  const [frameId, setFrameId] = useState("");
  const [videoId, setVideoId] = useState("");
  const [timeMs, setTimeMs] = useState("");

  useEffect(() => {
    healthCheck()
      .then((h) => setHealthStatus(h.status))
      .catch(() => setHealthStatus("error"));
  }, []);

  const handleSearch = useCallback(async (newFilter: SearchFilter) => {
    setFilter(newFilter);
    setIsLoading(true);
    try {
      if (newFilter.videoId) {
        const data = await searchVideoFrames(newFilter.videoId);
        setFrames(data.results);
      } else {
        const enabledQueries = newFilter.queries.filter((q) => q.enabled && q.content);
        const text = enabledQueries.map((q) => q.content).join(",");
        const tags = [...new Set(enabledQueries.flatMap((q) => q.tags ?? []))];
        const keywords = [...new Set(enabledQueries.flatMap((q) => q.keywords ?? []))];
        const data = await searchText({
          text,
          tags: tags.length > 0 ? tags : undefined,
          keywords: keywords.length > 0 ? keywords : undefined,
          topk: newFilter.topK,
          enhance: newFilter.enhance,
        });
        setFrames(data.results);
      }
    } catch (error) {
      console.error("Search failed:", error);
      setFrames([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleClear = useCallback(() => {
    setFilter(null);
    setFrames([]);
    setSelectedFrame(null);
    setSubmissionFrame(null);
  }, []);

  const handleFrameSelect = useCallback((frame: FrameResult) => {
    setSubmissionFrame(frame);
    setFrameId(frame.id);
    setVideoId(frame.video_id);
    setTimeMs(frame.pts_time.toFixed(0));
  }, []);

  const handleFrameDetail = useCallback((frame: FrameResult) => {
    setSelectedFrame(frame);
  }, []);

  const handleSubmit = () => {
    setShowSubmitConfirm(true);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <FilterPanel onSearch={handleSearch} onClear={handleClear} isLoading={isLoading} />

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top Bar */}
        <header className="bg-surface-container-lowest border-b border-outline-variant flex justify-between items-center px-container-padding w-full h-topbar-height shrink-0 z-20">
          <div className="flex items-center gap-6">
            <span className="font-headline-sm text-headline-sm font-bold text-on-surface tracking-tight">
              Frame Seeker
            </span>
            <div className="h-6 w-px bg-outline-variant hidden md:block" />

            {/* View Mode Toggle */}
            {frames.length > 0 && (
              <div className="flex items-center gap-2 mr-2 bg-surface-container-low p-1 rounded-lg border border-outline-variant">
                <button
                  onClick={() => setViewMode("grouped")}
                  className={`px-3 py-1 rounded font-label-sm text-label-sm transition-colors ${
                    viewMode === "grouped"
                      ? "bg-primary-container text-on-primary-container"
                      : "hover:bg-surface-variant text-on-surface-variant"
                  }`}
                >
                  Grouped
                </button>
                <button
                  onClick={() => setViewMode("continuous")}
                  className={`px-3 py-1 rounded font-label-sm text-label-sm transition-colors ${
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
                  <span className="font-label-sm text-label-sm text-on-surface-variant">
                    {type.toUpperCase()}
                  </span>
                </label>
              ))}
            </div>

            {/* Submission Inputs */}
            <div className="flex gap-2">
              <input
                className="w-20 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono-sm text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors"
                type="text"
                placeholder="Frame ID"
                value={frameId}
                onChange={(e) => setFrameId(e.target.value)}
              />
              <input
                className="w-48 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono-sm text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors text-ellipsis overflow-hidden whitespace-nowrap"
                type="text"
                placeholder="Video ID"
                value={videoId}
                onChange={(e) => setVideoId(e.target.value)}
              />
              <input
                className="w-40 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono-sm text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors"
                type="text"
                placeholder="Time (ms)"
                value={timeMs}
                onChange={(e) => setTimeMs(e.target.value)}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSubmit}
              className="bg-primary-container text-on-primary-container font-label-md text-label-md px-4 py-1.5 rounded hover:bg-opacity-90 transition-colors"
            >
              Submit
            </button>
            <div className="h-6 w-px bg-outline-variant mx-2" />
            <button
              onClick={() => setShowDresSettings(true)}
              className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors font-label-md text-label-md text-on-surface-variant"
            >
              <Icon name="settings" size={18} />
              DRES Settings
            </button>
            <div className="flex items-center gap-1.5 ml-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  healthStatus === "healthy" ? "bg-green-500" : healthStatus === "degraded" ? "bg-yellow-500" : "bg-gray-400"
                }`}
              />
              <span className="font-label-sm text-label-sm text-on-surface-variant">
                {healthStatus === "healthy" ? "API OK" : healthStatus === "degraded" ? "Degraded" : "..."}
              </span>
            </div>
          </div>
        </header>

        {/* Results */}
        <ResultsPanel
          frames={frames}
          viewMode={viewMode}
          onFrameSelect={handleFrameSelect}
          onFrameDetail={handleFrameDetail}
          isLoading={isLoading}
        />
      </div>

      {/* Dialogs */}
      {selectedFrame && (
        <FrameDetailDialog
          frame={selectedFrame}
          onClose={() => setSelectedFrame(null)}
          onSubmit={(frame) => {
            setSubmissionFrame(frame);
            setSelectedFrame(null);
            setShowSubmitConfirm(true);
          }}
        />
      )}

      {showDresSettings && <DresSettingsDialog onClose={() => setShowDresSettings(false)} />}

      {showSubmitConfirm && submissionFrame && (
        <SubmissionConfirmationDialog
          frame={submissionFrame}
          submissionType={submissionType}
          onClose={() => setShowSubmitConfirm(false)}
        />
      )}
    </div>
  );
}
