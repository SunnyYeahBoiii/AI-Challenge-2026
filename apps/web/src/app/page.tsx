"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { FilterPanel } from "@/components/filter-panel";
import { ResultsPanel } from "@/components/results-panel";
import { FrameDetailDialog } from "@/components/frame-detail-dialog";
import { DresSettingsDialog } from "@/components/dres-settings-dialog";
import { ModelSettingsDialog } from "@/components/model-settings-dialog";
import { SubmissionConfirmationDialog } from "@/components/submission-confirmation-dialog";
import { TrakeBoardPanel } from "@/components/trake-board-panel";
import { Icon } from "@/components/icon";
import { SubmissionsDashboard } from "@/components/submissions-dashboard";
import type { FrameResult } from "@/lib/api";
import { useDresSession } from "@/hooks/use-dres-session";
import { useSessionStorageState } from "@/hooks/use-session-storage";
import { useTemporalSearch } from "@/hooks/use-temporal-search";
import { useTrakeBoard } from "@/hooks/use-trake-board";
import type { FrameToTrake } from "@/lib/trake-types";
import { listQueries, listSubmissions, sortQueriesByQuestionId, type Query, type Submission } from "@/lib/submissions";
import { getNearestKeyframes, type KeyframeInfo } from "@/lib/api";
import { VideoPlayer, type VideoPlayerHandle } from "@/components/video-player";

type SubmissionType = "track" | "qa" | "kis";
type SubmitMode = "dres" | "cloud";
type View = "search" | "submissions";

export default function Home() {
  const { searchResult, queryCount, hasSearched, isLoading, searchError, setSearchError, handleSearch, clearSearch } =
    useTemporalSearch();
  const dres = useDresSession();

  const [selectedFrame, setSelectedFrame] = useState<FrameResult | null>(null);
  const [showDresSettings, setShowDresSettings] = useState(false);
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false);
  const [viewMode, setViewMode] = useState<"grouped" | "continuous">("grouped");
  const [gridCols, setGridCols] = useState(6);
  const [queries, setQueries] = useState<Query[]>([]);
  const [submissionType, setSubmissionType] = useSessionStorageState<SubmissionType>(
    "submissionType",
    "kis",
  );
  const [submitMode, setSubmitMode] = useSessionStorageState<SubmitMode>("submitMode", "dres");
  const [selectedQueryId, setSelectedQueryId] = useSessionStorageState<string | null>(
    "selectedQueryId",
    null,
  );
  const [view, setView] = useSessionStorageState<View>("view", "search");
  const [showQueryDetail, setShowQueryDetail] = useState(false);
  const [querySubmissions, setQuerySubmissions] = useState<Submission[]>([]);
  const [queryKeyframes, setQueryKeyframes] = useState<Record<string, KeyframeInfo | null>>({});
  const [queryVideoDialog, setQueryVideoDialog] = useState<{
    submission: Submission;
    keyframe: KeyframeInfo;
  } | null>(null);
  const queryVideoRef = useRef<VideoPlayerHandle>(null);

  // Submission state
  const [frameId, setFrameId] = useState("");
  const [videoId, setVideoId] = useState("");
  const [timeSec, setTimeSec] = useState("");
  const [qaAnswer, setQaAnswer] = useState("");
  const [trakeFrameIds, setTrakeFrameIds] = useState<number[] | null>(null);

  const trake = useTrakeBoard(submissionType === "track");

  const selectedQuery = queries.find((q) => q.id === selectedQueryId);

  const handleViewQueryDetail = useCallback(async () => {
    if (!selectedQuery) return;
    setShowQueryDetail(true);
    try {
      const subs = await listSubmissions();
      const filtered = subs.filter((s) => s.queryName === selectedQuery.name);
      setQuerySubmissions(filtered);

      const items = filtered.flatMap((sub) =>
        sub.frameIds.map((fi) => ({ video_id: sub.videoId, frame_index: fi, key: `${sub.videoId}-${fi}` }))
      );
      const kf = await getNearestKeyframes(items);
      setQueryKeyframes(kf);
    } catch {
      // ignore
    }
  }, [selectedQuery]);

  // Tasks can be added from the dashboard; refresh the topbar dropdown each
  // time the search view becomes active again.
  useEffect(() => {
    if (view === "search") {
      listQueries().then(setQueries).catch(() => {});
    }
  }, [view]);

  const addFrameToEvent = useCallback(
    (eventId: string, frame: FrameToTrake) => {
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
    [trake.setFocusedEventId, trake.addCandidate, setSearchError],
  );

  const addFrameToFocusedEvent = useCallback(
    (frame: FrameToTrake) => {
      addFrameToEvent(trake.focusedEventId ?? "", frame);
    },
    [addFrameToEvent, trake.focusedEventId],
  );

  const handleClear = useCallback(() => {
    clearSearch();
    setSelectedFrame(null);
    setFrameId("");
    setVideoId("");
    setTimeSec("");
    setQaAnswer("");
  }, [clearSearch]);

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

  if (view === "submissions") {
    return <SubmissionsDashboard onBack={() => setView("search")} />;
  }

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
        <header className="bg-surface-container-lowest border-b border-outline-variant flex items-center gap-4 px-container-padding w-full h-topbar-height shrink-0 z-20 overflow-x-auto">
          <div className="flex items-center gap-6 shrink-0 whitespace-nowrap">
            <span className="text-headline-sm font-bold text-on-surface tracking-tight shrink-0">
              Frame Seeker
            </span>
            <div className="h-6 w-px bg-outline-variant hidden md:block shrink-0" />

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

            {/* Submit Mode Toggle */}
            <div className="flex items-center gap-2 bg-surface-container-low p-1 rounded-lg border border-outline-variant">
              <span className="text-label-sm text-on-surface-variant px-2">Submit:</span>
              <label className="flex items-center gap-1 px-2 cursor-pointer">
                <input
                  type="radio"
                  name="submit_mode"
                  checked={submitMode === "dres"}
                  onChange={() => setSubmitMode("dres")}
                  className="text-primary focus:ring-primary h-3 w-3"
                />
                <span className="text-label-sm text-on-surface-variant">DRES</span>
              </label>
              <label className="flex items-center gap-1 px-2 cursor-pointer">
                <input
                  type="radio"
                  name="submit_mode"
                  checked={submitMode === "cloud"}
                  onChange={() => setSubmitMode("cloud")}
                  className="text-primary focus:ring-primary h-3 w-3"
                />
                <span className="text-label-sm text-on-surface-variant">Cloud</span>
              </label>
            </div>

            {/* Task Dropdown */}
            {submitMode === "cloud" && (
              <>
                <select
                  className="rounded border border-outline-variant bg-surface-container-low px-3 py-1.5 text-label-sm text-on-surface"
                  value={selectedQueryId ?? ""}
                  onChange={(e) => setSelectedQueryId(e.target.value || null)}
                >
                  <option value="">Select task...</option>
                  {sortQueriesByQuestionId(queries).map((q) => (
                    <option key={q.id} value={q.id}>
                      {q.name} ({q.queryType.toUpperCase()})
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleViewQueryDetail}
                  disabled={!selectedQuery}
                  title="View question detail"
                  className="flex items-center justify-center w-8 h-8 rounded border border-outline-variant bg-surface-container-low hover:bg-surface-container disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-on-surface-variant"
                >
                  <Icon name="visibility" size={18} />
                </button>
              </>
            )}

          </div>

          <div className="flex items-center gap-3 shrink-0 whitespace-nowrap ml-auto">
            {submitMode === "dres" && (
              <>
                {dres.sessionId && dres.username ? (
                  <div className="flex items-center gap-1.5">
                    <span
                      title="Logged in to DRES"
                      className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest text-label-md text-on-surface-variant"
                    >
                      <Icon name="groups" size={18} />
                      {dres.username}
                    </span>
                    <button
                      onClick={() => setShowDresSettings(true)}
                      title="Change DRES evaluation"
                      className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
                    >
                      <Icon name="tune" size={18} />
                    </button>
                    <button
                      onClick={dres.logout}
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
              </>
            )}
            <button
              onClick={() => setShowModelSettings(true)}
              className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
            >
              <Icon name="model_training" size={18} />
              Model Settings
            </button>
            {submitMode === "cloud" && (
              <button
                onClick={() => setView("submissions")}
                className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
              >
                <Icon name="list_alt" size={18} />
                Submissions
              </button>
            )}
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
          dresSessionId={dres.sessionId}
          dresEvaluationId={dres.evaluationId}
          gridCols={gridCols}
          hasSearched={hasSearched}
          trakeFocusedLabel={trake.focusedEvent?.displayLabel}
          onAddToTrake={
            submissionType === "track"
              ? (frame) => addFrameToFocusedEvent(frame)
              : undefined
          }
          submitMode={submitMode}
          onCloudQuickSubmit={(frame) => {
            setFrameId(String(frame.frame_idx));
            setVideoId(frame.video_id);
            setTimeSec(frame.timestamp.toFixed(1));
            setQaAnswer("");
            setTrakeFrameIds(null);
            setShowSubmitConfirm(true);
          }}
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
          sessionId={dres.sessionId}
          username={dres.username}
          evaluationId={dres.evaluationId}
          onClose={() => setShowDresSettings(false)}
          onLoginSuccess={dres.login}
          onEvaluationSelect={dres.selectEvaluation}
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
          sessionId={dres.sessionId}
          evaluationId={dres.evaluationId}
          answer={qaAnswer}
          trakeFrameIds={trakeFrameIds ?? undefined}
          submitMode={submitMode}
          queries={queries}
          selectedQueryId={selectedQueryId}
          onClose={() => {
            setShowSubmitConfirm(false);
            setTrakeFrameIds(null);
          }}
        />
      )}
    </div>
  );
}
