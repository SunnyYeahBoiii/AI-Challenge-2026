"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { FilterPanel, type SearchFilter } from "@/components/filter-panel";
import { ResultsPanel } from "@/components/results-panel";
import { FrameDetailDialog } from "@/components/frame-detail-dialog";
import { DresSettingsDialog } from "@/components/dres-settings-dialog";
import { ModelSettingsDialog } from "@/components/model-settings-dialog";
import { SubmissionConfirmationDialog } from "@/components/submission-confirmation-dialog";
import { TrakeBoardPanel } from "@/components/trake-board-panel";
import { Icon } from "@/components/icon";
import type { FrameResult, TemporalSearchResponse, TemporalVideoResult } from "@/lib/api";
import { multiBoxSearch, searchVideoFrames, healthCheck } from "@/lib/api";
import { useTrakeBoard } from "@/hooks/use-trake-board";

function emptySearchResult(mode: "parallel" | "sequential" = "parallel"): TemporalSearchResponse {
  return { mode, videos: [], total_videos: 0, total_valid_frames: 0 };
}

function videoFramesResponse(
  frames: FrameResult[],
  mode: "parallel" | "sequential"
): TemporalSearchResponse {
  const grouped = new Map<string, FrameResult[]>();
  frames.forEach((frame) => {
    const current = grouped.get(frame.video_id) ?? [];
    const score = Number.isFinite(frame.score) ? frame.score : 0;
    current.push({
      ...frame,
      score,
      matches: [{ query_index: 0, similarity: score }],
    });
    grouped.set(frame.video_id, current);
  });
  const videos: TemporalVideoResult[] = Array.from(grouped.entries()).map(([videoId, results]) => {
    const validFrames = [...results].sort((left, right) => left.frame_idx - right.frame_idx);
    const best = [...validFrames].sort(
      (left, right) => right.score - left.score || left.frame_idx - right.frame_idx
    )[0];
    return {
      video_id: videoId,
      video_score: best?.score ?? 0,
      has_vector_score: false,
      valid_frames: validFrames,
      best_sequence: {
        sequence_id: `${videoId}:${best?.frame_index ?? 0}`,
        sequence_score: best?.score ?? 0,
        total_span_seconds: 0,
        frames: best ? [{ ...best, query_index: 0, similarity: best.score }] : [],
      },
    };
  });
  videos.sort((left, right) => right.video_score - left.video_score);
  return {
    mode,
    videos,
    total_videos: videos.length,
    total_valid_frames: videos.reduce((total, video) => total + video.valid_frames.length, 0),
  };
}

export default function Home() {
  const [searchResult, setSearchResult] = useState<TemporalSearchResponse>(() => emptySearchResult());
  const [queryCount, setQueryCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [selectedFrame, setSelectedFrame] = useState<FrameResult | null>(null);
  const [showDresSettings, setShowDresSettings] = useState(false);
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false);
  const [dresSessionId, setDresSessionId] = useState<string | null>(null);
  const [dresUsername, setDresUsername] = useState<string | null>(null);
  const [dresEvaluationId, setDresEvaluationId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"grouped" | "continuous">("grouped");
  const [gridCols, setGridCols] = useState(6);
  const [healthStatus, setHealthStatus] = useState<string>("loading");
  const searchIdRef = useRef(0);

  // Submission state
  const [submissionType, setSubmissionType] = useState<"track" | "qa" | "kis">("kis");
  const [frameId, setFrameId] = useState("");
  const [videoId, setVideoId] = useState("");
  const [timeSec, setTimeSec] = useState("");
  const [qaAnswer, setQaAnswer] = useState("");
  const [trakeFrameIds, setTrakeFrameIds] = useState<number[] | null>(null);

  const trake = useTrakeBoard(submissionType === "track");

  const addFrameToEvent = useCallback(
    (
      eventId: string,
      frame: {
        video_id: string;
        timestamp: number;
        frame_idx: number;
        fps: number;
        thumbnail_url: string;
      },
    ) => {
      if (!eventId) {
        setSearchError("Select or add an Event on the TRAKE board first.");
        return;
      }
      trake.setFocusedEventId(eventId);
      trake.addCandidate({
        eventId,
        videoId: frame.video_id,
        ptsTime: frame.timestamp,
        previewFrameId: String(frame.frame_idx),
        fps: frame.fps,
        frameIdx: frame.frame_idx,
        thumbnailUrl: frame.thumbnail_url,
      });
    },
    [trake.setFocusedEventId, trake.addCandidate],
  );

  const addFrameToFocusedEvent = useCallback(
    (frame: {
      video_id: string;
      timestamp: number;
      frame_idx: number;
      fps: number;
      thumbnail_url: string;
    }) => {
      addFrameToEvent(trake.focusedEventId ?? "", frame);
    },
    [addFrameToEvent, trake.focusedEventId],
  );

  useEffect(() => {
    healthCheck()
      .then((h) => setHealthStatus(h.status))
      .catch(() => setHealthStatus("error"));
  }, []);

  useEffect(() => {
    setDresSessionId(sessionStorage.getItem("dresSessionId"));
    setDresUsername(sessionStorage.getItem("dresUsername"));
    setDresEvaluationId(sessionStorage.getItem("dresEvaluationId"));
  }, []);

  const handleDresLogin = useCallback((sessionId: string, username: string) => {
    sessionStorage.setItem("dresSessionId", sessionId);
    sessionStorage.setItem("dresUsername", username);
    setDresSessionId(sessionId);
    setDresUsername(username);
  }, []);

  const handleDresEvaluationSelect = useCallback((evaluationId: string) => {
    sessionStorage.setItem("dresEvaluationId", evaluationId);
    setDresEvaluationId(evaluationId);
  }, []);

  const handleDresLogout = useCallback(() => {
    const sessionId = dresSessionId;
    sessionStorage.removeItem("dresSessionId");
    sessionStorage.removeItem("dresUsername");
    sessionStorage.removeItem("dresEvaluationId");
    setDresSessionId(null);
    setDresUsername(null);
    setDresEvaluationId(null);
    if (sessionId) {
      fetch("/api/dres/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId }),
      }).catch(() => {});
    }
  }, [dresSessionId]);

  const handleSearch = useCallback(async (newFilter: SearchFilter) => {
    const currentSearchId = ++searchIdRef.current;
    setIsLoading(true);
    setSearchError(null);
    setHasSearched(true);
    try {
      if (newFilter.videoId) {
        const data = await searchVideoFrames(newFilter.videoId);
        if (currentSearchId !== searchIdRef.current) return;
        setSearchResult(videoFramesResponse(data.results, newFilter.mode));
        setQueryCount(1);
      } else {
        const enabledQueries = newFilter.queries.filter(
          (q) => q.enabled && Boolean(
            q.content.trim() || q.tags?.length || q.ocrKeywords?.length || q.asrKeywords?.length
          )
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
          topk: q.topK ?? 1000,
          enhance: q.enhance ?? true,
        }));
        const data = await multiBoxSearch({
          box_queries: boxQueries,
          mode: newFilter.mode,
          temporal_window_seconds: newFilter.temporalWindowSeconds,
        });
        if (currentSearchId !== searchIdRef.current) return;
        setSearchResult(data);
        setQueryCount(enabledQueries.length);
      }
    } catch (error) {
      if (currentSearchId !== searchIdRef.current) return;
      console.error("Search failed:", error);
      setSearchError(error instanceof Error ? error.message : "Search failed. Check the API connection and try again.");
      setSearchResult(emptySearchResult(newFilter.mode));
      setQueryCount(0);
    } finally {
      if (currentSearchId === searchIdRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  const handleClear = useCallback(() => {
    searchIdRef.current += 1;
    setSearchResult(emptySearchResult());
    setQueryCount(0);
    setSearchError(null);
    setSelectedFrame(null);
    setFrameId("");
    setVideoId("");
    setTimeSec("");
    setQaAnswer("");
    setHasSearched(false);
    setIsLoading(false);
  }, []);

  const handleFrameSelect = useCallback((frame: FrameResult) => {
    setFrameId(String(frame.frame_idx));
    setVideoId(frame.video_id);
    setTimeSec(frame.timestamp.toFixed(1));
  }, []);

  const handleFrameDetail = useCallback((frame: FrameResult) => {
    setSelectedFrame(frame);
  }, []);

  const canSubmit =
    submissionType === "track"
      ? Boolean(trakeFrameIds?.length && videoId.trim())
      : frameId.trim().length > 0 && videoId.trim().length > 0;

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <FilterPanel
        onSearch={handleSearch}
        onClear={handleClear}
        onValidationError={setSearchError}
        isLoading={isLoading}
        gridCols={gridCols}
        onGridColsChange={setGridCols}
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
            {searchResult.total_valid_frames > 0 && (
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
                  {dresEvaluationId && (
                    <span className="text-on-surface-variant/70">· {dresEvaluationId}</span>
                  )}
                </span>
                <button
                  onClick={() => setShowDresSettings(true)}
                  title="Change DRES evaluation"
                  className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
                >
                  <Icon name="tune" size={18} />
                </button>
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
            <button
              onClick={() => setShowModelSettings(true)}
              className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
            >
              <Icon name="model_training" size={18} />
              Model Settings
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
          result={searchResult}
          queryCount={queryCount}
          viewMode={viewMode}
          onFrameSelect={handleFrameSelect}
          onFrameDetail={handleFrameDetail}
          isLoading={isLoading}
          submissionType={submissionType}
          dresSessionId={dresSessionId}
          dresEvaluationId={dresEvaluationId}
          gridCols={gridCols}
          hasSearched={hasSearched}
          trakeFocusedLabel={trake.focusedEvent?.displayLabel}
          onAddToTrake={
            submissionType === "track"
              ? (frame) => addFrameToFocusedEvent(frame)
              : undefined
          }
        />
      </div>

      {submissionType === "track" && (
        <TrakeBoardPanel
          trake={trake}
          onSubmitTrake={({ videoId: v, frameIds }) => {
            setVideoId(v);
            setTrakeFrameIds(frameIds);
            setFrameId(String(frameIds[0] ?? ""));
            setTimeSec("0");
            setShowSubmitConfirm(true);
          }}
        />
      )}

      {/* Dialogs */}
      {selectedFrame && (
        <FrameDetailDialog
          frame={selectedFrame}
          submissionType={submissionType}
          onClose={() => setSelectedFrame(null)}
          trakeEvents={
            trake.board?.events.map((e) => ({
              id: e.id,
              displayLabel: e.displayLabel,
            })) ?? []
          }
          trakeFocusedEventId={trake.focusedEventId}
          onAddToTrake={
            submissionType === "track"
              ? (submission) => {
                  addFrameToEvent(submission.eventId, {
                    video_id: submission.videoId,
                    timestamp: Number.parseFloat(submission.timeSec) || 0,
                    frame_idx: submission.frameIdx,
                    fps: submission.fps,
                    thumbnail_url: submission.thumbnailUrl,
                  });
                  setSelectedFrame(null);
                }
              : undefined
          }
          onSubmit={(submission) => {
            setFrameId(submission.frameId);
            setVideoId(submission.videoId);
            setTimeSec(submission.timeSec);
            setQaAnswer(submission.answer ?? "");
            setTrakeFrameIds(null);
            setSelectedFrame(null);
            setShowSubmitConfirm(true);
          }}
        />
      )}

      {showDresSettings && (
        <DresSettingsDialog
          sessionId={dresSessionId}
          username={dresUsername}
          evaluationId={dresEvaluationId}
          onClose={() => setShowDresSettings(false)}
          onLoginSuccess={handleDresLogin}
          onEvaluationSelect={handleDresEvaluationSelect}
        />
      )}

      {showModelSettings && (
        <ModelSettingsDialog onClose={() => setShowModelSettings(false)} />
      )}

      {showSubmitConfirm && canSubmit && (
        <SubmissionConfirmationDialog
          frameId={frameId.trim()}
          videoId={videoId.trim()}
          timestamp={Number.parseFloat(timeSec) || 0}
          submissionType={submissionType}
          sessionId={dresSessionId}
          evaluationId={dresEvaluationId}
          answer={qaAnswer}
          trakeFrameIds={trakeFrameIds ?? undefined}
          onClose={() => {
            setShowSubmitConfirm(false);
            setTrakeFrameIds(null);
          }}
        />
      )}
    </div>
  );
}
