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
import { useTheme } from "@/hooks/use-theme";
import { useTrakeBoard } from "@/hooks/use-trake-board";
import type { FrameToTrake } from "@/lib/trake-types";
import { listQueries, listSubmissions, sortQueriesByQuestionId, type Query, type Submission } from "@/lib/submissions";
import { getNearestKeyframes, type KeyframeInfo } from "@/lib/api";
import { VideoPlayer, type VideoPlayerHandle } from "@/components/video-player";
import {
  DEFAULT_ASR_SEARCH_CONFIG,
  DEFAULT_OCR_SEARCH_CONFIG,
  type KeywordSearchConfig,
} from "@/components/keyword-search-options";

type SubmissionType = "track" | "qa" | "kis";
type SubmitMode = "dres" | "cloud";
type View = "search" | "submissions";

export default function Home() {
  const { searchResult, queryCount, isVideoBrowse, hasSearched, isLoading, searchError, setSearchError, handleSearch, clearSearch } =
    useTemporalSearch();
  const dres = useDresSession();
  const { theme, toggle: toggleTheme } = useTheme();

  const [selectedFrame, setSelectedFrame] = useState<FrameResult | null>(null);
  const [showDresSettings, setShowDresSettings] = useState(false);
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [showKeyboardHelp, setShowKeyboardHelp] = useState(false);
  const [videoSeekStepSeconds, setVideoSeekStepSeconds] = useSessionStorageState<number>(
    "videoSeekStepSeconds",
    0.2,
  );
  const [ocrSearchConfig, setOcrSearchConfig] = useSessionStorageState<KeywordSearchConfig>(
    "ocrSearchConfig",
    DEFAULT_OCR_SEARCH_CONFIG,
  );
  const [asrSearchConfig, setAsrSearchConfig] = useSessionStorageState<KeywordSearchConfig>(
    "asrSearchConfig",
    DEFAULT_ASR_SEARCH_CONFIG,
  );
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false);
  const [viewMode, setViewMode] = useState<"grouped" | "continuous">("grouped");
  const [gridCols, setGridCols] = useState(6);
  const [temporalWindowSeconds, setTemporalWindowSeconds] = useState(90);
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
    submittedFrameIndex: number;
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

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && showKeyboardHelp) {
        event.preventDefault();
        setShowKeyboardHelp(false);
        return;
      }
      if (event.altKey && !event.ctrlKey && !event.shiftKey && !event.metaKey && event.key.toLowerCase() === "i") {
        event.preventDefault();
        setShowModelSettings(true);
        return;
      }
      if (event.altKey && !event.ctrlKey && !event.shiftKey && !event.metaKey && event.key === "/") {
        event.preventDefault();
        setShowKeyboardHelp((open) => !open);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [showKeyboardHelp]);

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
        temporalWindowSeconds={temporalWindowSeconds}
        ocrSearchConfig={ocrSearchConfig}
        asrSearchConfig={asrSearchConfig}
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
              Setting
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
            <button
              onClick={toggleTheme}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              className="flex items-center justify-center w-9 h-9 rounded border border-outline-variant bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-on-surface-variant"
            >
              <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} size={18} />
            </button>
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
          isVideoBrowse={isVideoBrowse}
          viewMode={viewMode}
          onFrameSelect={handleFrameSelect}
          onFrameDetail={handleFrameDetail}
          isLoading={isLoading}
          submissionType={submissionType}
          dresSessionId={dres.sessionId}
          dresEvaluationId={dres.evaluationId}
          dresUrl={dres.dresUrl}
          gridCols={gridCols}
          hasSearched={hasSearched}
          trakeFocusedLabel={trake.focusedEvent?.displayLabel}
          onAddToTrake={
            submissionType === "track"
              ? (frame) => addFrameToFocusedEvent(frame)
              : undefined
          }
          submitMode={submitMode}
          isInteractionDisabled={Boolean(selectedFrame)}
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
          seekStepSeconds={videoSeekStepSeconds}
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
            setShowSubmitConfirm(true);
          }}
        />
      )}

      {showDresSettings && (
        <DresSettingsDialog
          sessionId={dres.sessionId}
          username={dres.username}
          evaluationId={dres.evaluationId}
          dresUrl={dres.dresUrl}
          onClose={() => setShowDresSettings(false)}
          onLoginSuccess={dres.login}
          onEvaluationSelect={dres.selectEvaluation}
          onServerChange={dres.switchServer}
        />
      )}

      {showModelSettings && (
        <ModelSettingsDialog
          onClose={() => setShowModelSettings(false)}
          seekStepSeconds={videoSeekStepSeconds}
          onSeekStepSecondsChange={setVideoSeekStepSeconds}
          temporalWindowSeconds={temporalWindowSeconds}
          onTemporalWindowSecondsChange={setTemporalWindowSeconds}
          ocrSearchConfig={ocrSearchConfig}
          onOcrSearchConfigChange={setOcrSearchConfig}
          asrSearchConfig={asrSearchConfig}
          onAsrSearchConfigChange={setAsrSearchConfig}
        />
      )}

      {showKeyboardHelp && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-on-surface/60 p-4" onClick={() => setShowKeyboardHelp(false)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
            className="w-full max-w-lg rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-headline-sm font-bold">Keyboard shortcuts</h2>
              <button onClick={() => setShowKeyboardHelp(false)} aria-label="Close keyboard shortcuts" className="rounded p-1 hover:bg-surface-container">
                <Icon name="close" size={20} />
              </button>
            </div>
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-body-sm">
              <kbd>Ctrl + Enter</kbd><span>Search</span>
              <kbd>Alt + Q / V</kbd><span>Focus query / Video ID</span>
              <kbd>Alt + 1…9</kbd><span>Focus query 1–9</span>
              <kbd>Alt + O / S</kbd><span>Focus OCR / ASR keyword input</span>
              <kbd>Alt + N</kbd><span>Add a query</span>
              <kbd>Enter</kbd><span>Add the typed keyword while an OCR/ASR input is focused</span>
              <kbd>Backspace</kbd><span>Remove the last keyword when the focused keyword input is empty</span>
              <kbd>Alt + E</kbd><span>Toggle AI Enhance for the active query</span>
              <kbd>Alt + ↑ / ↓</kbd><span>Move active query</span>
              <kbd>Alt + [ / ]</kbd><span>Decrease / increase grid columns</span>
              <kbd>Alt + ← / →</kbd><span>Move between frames in Frame Detail</span>
              <kbd>Alt + Shift + ← / →</kbd><span>Seek video backward / forward by {videoSeekStepSeconds}s</span>
              <kbd>Enter / Z</kbd><span>Open detail / zoom selected result</span>
              <kbd>Alt + Enter</kbd><span>Quick submit selected result</span>
              <kbd>Alt + A</kbd><span>Add selected result to focused TRAKE Event</span>
              <kbd>Alt + /</kbd><span>Show this shortcut list</span>
              <kbd>Alt + I</kbd><span>Open Setting</span>
              <kbd>Esc</kbd><span>Close the active dialog</span>
            </div>
          </section>
        </div>
      )}

      {showSubmitConfirm && canSubmit && (
        <SubmissionConfirmationDialog
          frameId={frameId.trim()}
          videoId={videoId.trim()}
          timestamp={Number.parseFloat(timeSec) || 0}
          submissionType={submissionType}
          sessionId={dres.sessionId}
          evaluationId={dres.evaluationId}
          dresUrl={dres.dresUrl}
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

      {/* Query Detail Dialog */}
      {showQueryDetail && selectedQuery && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
          <div className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col border border-outline-variant">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-outline-variant shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-label-sm font-bold text-on-surface-variant bg-surface-container px-2 py-0.5 rounded">
                  {selectedQuery.queryType.toUpperCase()}
                </span>
                <span className="text-headline-sm font-bold">{selectedQuery.name}</span>
              </div>
              <button
                onClick={() => {
                  setShowQueryDetail(false);
                  setQuerySubmissions([]);
                  setQueryKeyframes({});
                }}
                className="text-on-surface-variant hover:text-on-surface p-1 rounded hover:bg-surface-container transition-colors"
              >
                <Icon name="close" size={20} />
              </button>
            </div>

            {/* Question - always visible */}
            {selectedQuery.content && (
              <div className="px-6 pt-4 shrink-0">
                <div className="p-3 rounded-lg bg-surface-container-low border border-outline-variant">
                  <div className="text-label-sm font-bold text-on-surface-variant mb-1">Question</div>
                  <div className="text-body-md text-on-surface whitespace-pre-wrap leading-relaxed">
                    {selectedQuery.content}
                  </div>
                </div>
              </div>
            )}

            {/* Submissions - scrollable */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <div className="text-label-md font-bold text-on-surface-variant mb-2">
                Submissions ({querySubmissions.length})
              </div>
              {querySubmissions.length === 0 ? (
                <div className="text-center py-8 text-on-surface-variant text-body-md">
                  No submissions for this query yet.
                </div>
              ) : (
                <div className="space-y-2">
                  {querySubmissions
                    .sort((a, b) => {
                      const order: Record<string, number> = { confirmed: 0, review: 1, pending: 2 };
                      return (order[a.status] ?? 2) - (order[b.status] ?? 2) || a.sortOrder - b.sortOrder;
                    })
                    .map((sub) => (
                      <div
                        key={sub.id}
                        className="rounded-lg bg-surface-container-low border border-outline-variant px-4 py-3"
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`w-3 h-3 rounded-full shrink-0 ${
                              sub.status === "confirmed"
                                ? "bg-green-500"
                                : sub.status === "review"
                                  ? "bg-yellow-500"
                                  : "bg-gray-400"
                            }`}
                          />
                          <span className="text-body-md font-mono">{sub.videoId}</span>
                          <span className="text-body-sm text-on-surface-variant">
                            Frame {sub.frameIds.join(", ")}
                          </span>
                          {sub.submittedBy && (
                            <span className="text-body-sm text-on-surface-variant">
                              · by {sub.submittedBy}
                            </span>
                          )}
                        </div>
                        {sub.answer && (
                          <div className="text-body-sm text-on-surface-variant mt-1">
                            <span className="font-bold">Answer:</span> {sub.answer}
                          </div>
                        )}
                        <div className="flex flex-wrap gap-2 mt-2">
                          {sub.frameIds.map((fi) => {
                            const kf = queryKeyframes[`${sub.videoId}-${fi}`];
                            if (!kf?.thumbnail_url) return null;
                            return (
                              <button
                                key={fi}
                                onClick={() => setQueryVideoDialog({ submission: sub, keyframe: kf, submittedFrameIndex: fi })}
                                className="relative shrink-0 group"
                                title="View in video player"
                              >
                                <img
                                  src={kf.thumbnail_url}
                                  alt={`Frame ${fi}`}
                                  className="w-20 h-12 object-cover rounded border border-outline-variant group-hover:opacity-80 group-hover:ring-2 group-hover:ring-primary transition"
                                  loading="lazy"
                                />
                                {!kf.is_exact && (
                                  <span className="absolute -top-1 -right-1 bg-yellow-500 text-white text-label-xs px-1 rounded">
                                    ~{kf.frame_index}
                                  </span>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Video Player Dialog for Query Detail */}
      {queryVideoDialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/90 backdrop-blur-sm">
          <div className="relative w-full max-w-6xl h-[80vh] bg-black rounded-lg overflow-hidden">
            <button
              onClick={() => setQueryVideoDialog(null)}
              className="absolute top-4 right-4 z-10 text-white hover:bg-white/10 rounded-full p-2 transition-colors"
            >
              <Icon name="close" size={24} />
            </button>

            <div className="absolute top-4 left-4 z-10 bg-black/70 rounded px-3 py-2 text-white">
              <div className="text-label-sm font-bold">{queryVideoDialog.submission.queryName}</div>
              <div className="text-body-xs text-gray-300">
                {queryVideoDialog.submission.videoId} · Frame {queryVideoDialog.submittedFrameIndex}
                {!queryVideoDialog.keyframe.is_exact && (
                  <span className="text-yellow-400 ml-2">(nearest: {queryVideoDialog.keyframe.frame_index})</span>
                )}
              </div>
              {queryVideoDialog.submission.answer && (
                <div className="text-body-xs text-gray-300 mt-1">Answer: {queryVideoDialog.submission.answer}</div>
              )}
            </div>

            <VideoPlayer
              ref={queryVideoRef}
              src={queryVideoDialog.keyframe.video_url}
              poster={queryVideoDialog.keyframe.thumbnail_url}
              initialTime={
                queryVideoDialog.submission.queryType === "trake" && queryVideoDialog.keyframe.fps
                  ? queryVideoDialog.submittedFrameIndex / queryVideoDialog.keyframe.fps
                  : queryVideoDialog.keyframe.timestamp
              }
            />
          </div>
        </div>
      )}
    </div>
  );
}
