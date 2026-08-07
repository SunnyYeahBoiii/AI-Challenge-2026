"use client";

import { useState, useCallback, useEffect } from "react";
import { FilterPanel, type SearchFilter } from "@/components/filter-panel";
import { ResultsPanel } from "@/components/results-panel";
import { FrameDetailDialog } from "@/components/frame-detail-dialog";
import { DresSettingsDialog } from "@/components/dres-settings-dialog";
import { SubmissionConfirmationDialog } from "@/components/submission-confirmation-dialog";
import { YoutubePlayerDialog } from "@/components/youtube-player-dialog";
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
  const [showYoutubePlayer, setShowYoutubePlayer] = useState(false);
  const [youtubePlayerUrl, setYoutubePlayerUrl] = useState("");
  const [youtubePlayerVideoId, setYoutubePlayerVideoId] = useState("");
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
    setFrameId(frame.id);
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

            {/* Submission Inputs */}
            <div className="flex gap-2">
              <input
                className="w-20 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors"
                type="text"
                placeholder="Frame ID"
                aria-label="Frame ID"
                value={frameId}
                onChange={(e) => setFrameId(e.target.value)}
              />
              <input
                className="w-48 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors text-ellipsis overflow-hidden whitespace-nowrap"
                type="text"
                placeholder="Video ID"
                aria-label="Video ID"
                value={videoId}
                onChange={(e) => setVideoId(e.target.value)}
              />
              <input
                className="w-40 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors"
                type="text"
                placeholder="Time (s)"
                aria-label="Time in seconds"
                value={timeSec}
                onChange={(e) => setTimeSec(e.target.value)}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                if (selectedFrame) {
                  setYoutubePlayerUrl(selectedFrame.watch_url);
                  setYoutubePlayerVideoId(selectedFrame.video_id);
                } else if (videoId.trim()) {
                  setYoutubePlayerUrl("");
                  setYoutubePlayerVideoId(videoId.trim());
                }
                setShowYoutubePlayer(true);
              }}
              title="Open YouTube Player"
              className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
            >
              <Icon name="play_circle" size={18} />
              YouTube Player
            </button>
            <button
              onClick={() => setShowSubmitConfirm(true)}
              disabled={!canSubmit}
              title={canSubmit ? "Submit to DRES" : "Select a frame or fill Frame ID and Video ID first"}
              className="bg-primary-container text-on-primary-container text-label-md px-4 py-1.5 rounded hover:bg-primary-fixed transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Submit
            </button>
            <div className="h-6 w-px bg-outline-variant mx-2" />
            <button
              onClick={() => setShowDresSettings(true)}
              className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
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
          onFrameNavigate={(frame) => {
            setSelectedFrame(frame);
            handleFrameSelect(frame);
          }}
          onOpenYoutube={(watchUrl, videoId) => {
            setYoutubePlayerUrl(watchUrl);
            setYoutubePlayerVideoId(videoId);
            setSelectedFrame(null);
            setShowYoutubePlayer(true);
          }}
        />
      )}

      {showDresSettings && <DresSettingsDialog onClose={() => setShowDresSettings(false)} />}

      {showYoutubePlayer && (
        <YoutubePlayerDialog
          watchUrl={youtubePlayerUrl}
          videoId={youtubePlayerVideoId || undefined}
          submissionType={submissionType}
          onSubmissionTypeChange={setSubmissionType}
          onClose={() => setShowYoutubePlayer(false)}
          onSubmit={(submission) => {
            setFrameId(submission.frameId);
            setVideoId(submission.videoId);
            setTimeSec(submission.timeSec);
            setShowYoutubePlayer(false);
            setShowSubmitConfirm(true);
          }}
        />
      )}

      {showSubmitConfirm && canSubmit && (
        <SubmissionConfirmationDialog
          frameId={frameId.trim()}
          videoId={videoId.trim()}
          timestamp={Number.parseFloat(timeSec) || 0}
          submissionType={submissionType}
          onClose={() => setShowSubmitConfirm(false)}
        />
      )}
    </div>
  );
}
