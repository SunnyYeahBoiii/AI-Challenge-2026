"use client";

import { useState, useCallback, useEffect } from "react";
import axios from "axios";
import { FilterPanel, type SearchFilter } from "@/components/filter-panel";
import { ResultsPanel } from "@/components/results-panel";
import { FrameDetailDialog } from "@/components/frame-detail-dialog";
import { DresSettingsDialog } from "@/components/dres-settings-dialog";
import { SubmissionConfirmationDialog } from "@/components/submission-confirmation-dialog";
import { Icon } from "@/components/icon";
import type { FrameResult } from "@/lib/api";
import {
  competitionFrameIndex,
  healthCheck,
  multiBoxSearch,
  searchVideoFrames,
} from "@/lib/api";

function sortResults(
  results: FrameResult[],
  sortBy: SearchFilter["sortBy"],
): FrameResult[] {
  return [...results].sort((left, right) => {
    if (sortBy === "score") {
      return (right.score ?? right.fusion_score ?? 0) - (left.score ?? left.fusion_score ?? 0);
    }
    return (
      left.video_id.localeCompare(right.video_id) ||
      competitionFrameIndex(left) - competitionFrameIndex(right)
    );
  });
}

export default function Home() {
  const [frames, setFrames] = useState<FrameResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedFrame, setSelectedFrame] = useState<FrameResult | null>(null);
  const [submissionFrame, setSubmissionFrame] = useState<FrameResult | null>(null);
  const [showDresSettings, setShowDresSettings] = useState(false);
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false);
  const [viewMode, setViewMode] = useState<"grouped" | "continuous">("grouped");
  const [healthStatus, setHealthStatus] = useState<string>("loading");
  const [searchError, setSearchError] = useState<string | null>(null);

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

  const handleSearch = useCallback(async (newFilter: SearchFilter) => {
    setIsLoading(true);
    setSearchError(null);
    try {
      if (newFilter.videoId) {
        const data = await searchVideoFrames(newFilter.videoId);
        setFrames(sortResults(data.results, newFilter.sortBy));
      } else {
        const enabledQueries = newFilter.queries.filter((q) => q.enabled && q.content);
        const boxQueries = enabledQueries.map((q) => ({
          text: q.type === "text" ? q.content : undefined,
          image: q.type === "image" ? q.content : undefined,
          tags: q.tags?.length ? q.tags : undefined,
          keywords: q.keywords?.length ? q.keywords : undefined,
          topk: q.topK ?? 100,
          enhance: q.enhance ?? false,
        }));
        const data = await multiBoxSearch({
          box_queries: boxQueries,
        });
        setFrames(sortResults(data.results, newFilter.sortBy));
      }
    } catch (error) {
      console.error("Search failed:", error);
      setFrames([]);
      if (axios.isAxiosError(error)) {
        const payload = error.response?.data as
          | { error?: { message?: string } | string }
          | undefined;
        const message =
          typeof payload?.error === "string"
            ? payload.error
            : payload?.error?.message;
        setSearchError(message || error.message || "Search request failed");
      } else {
        setSearchError(error instanceof Error ? error.message : "Search request failed");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleClear = useCallback(() => {
    setFrames([]);
    setSelectedFrame(null);
    setSubmissionFrame(null);
    setSearchError(null);
  }, []);

  const handleFrameSelect = useCallback((frame: FrameResult) => {
    setSubmissionFrame(frame);
    setFrameId(String(competitionFrameIndex(frame)));
    setVideoId(frame.video_id);
    setTimeSec(frame.pts_time.toFixed(1));
  }, []);

  const handleFrameDetail = useCallback((frame: FrameResult) => {
    setSelectedFrame(frame);
  }, []);

  const handleSubmit = () => {
    if (!submissionFrame) return;
    setShowSubmitConfirm(true);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <FilterPanel onSearch={handleSearch} onClear={handleClear} isLoading={isLoading} />

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top Bar */}
        <header className="bg-surface-container-lowest border-b border-outline-variant flex justify-between items-center gap-3 px-container-padding w-full h-topbar-height shrink-0 z-20 overflow-x-auto">
          <div className="flex items-center gap-3 min-w-max">
            <span className="hidden xl:inline font-headline-sm text-headline-sm font-bold text-on-surface tracking-tight">
              Frame Seeker
            </span>
            <div className="h-6 w-px bg-outline-variant hidden xl:block" />

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
            <div className="flex items-center gap-2 bg-surface-container-low p-1 rounded-lg border border-outline-variant">
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
                readOnly
              />
              <input
                className="w-40 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono-sm text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors text-ellipsis overflow-hidden whitespace-nowrap"
                type="text"
                placeholder="Video ID"
                value={videoId}
                readOnly
              />
              <input
                className="w-28 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono-sm text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors"
                type="text"
                placeholder="Time (s)"
                value={timeSec}
                readOnly
              />
            </div>
          </div>

          <div className="flex items-center gap-2 min-w-max">
            <button
              onClick={handleSubmit}
              disabled={!submissionFrame}
              className="bg-primary-container text-on-primary-container font-label-md text-label-md px-4 py-1.5 rounded hover:bg-opacity-90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            >
              Submit
            </button>
            <div className="h-6 w-px bg-outline-variant mx-2" />
            <button
              onClick={() => setShowDresSettings(true)}
              className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors font-label-md text-label-md text-on-surface-variant"
            >
              <Icon name="settings" size={18} />
              <span className="hidden 2xl:inline">DRES Settings</span>
            </button>
            <div className="hidden 2xl:flex items-center gap-1.5 ml-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  healthStatus === "healthy"
                    ? "bg-green-500"
                    : healthStatus === "degraded"
                      ? "bg-yellow-500"
                      : healthStatus === "error"
                        ? "bg-red-500"
                        : "bg-gray-400"
                }`}
              />
              <span className="font-label-sm text-label-sm text-on-surface-variant">
                {healthStatus === "healthy"
                  ? "API OK"
                  : healthStatus === "degraded"
                    ? "Degraded"
                    : healthStatus === "error"
                      ? "Offline"
                      : "Checking"}
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
          error={searchError}
        />
      </div>

      {/* Dialogs */}
      {selectedFrame && (
        <FrameDetailDialog
          key={`${selectedFrame.video_id}:${selectedFrame.frame_index}`}
          frame={selectedFrame}
          submissionType={submissionType}
          onSubmissionTypeChange={setSubmissionType}
          onClose={() => setSelectedFrame(null)}
          onSubmit={(frame) => {
            handleFrameSelect(frame);
            setSelectedFrame(null);
            setShowSubmitConfirm(true);
          }}
          onFrameNavigate={(frame) => {
            setSelectedFrame(frame);
            handleFrameSelect(frame);
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
