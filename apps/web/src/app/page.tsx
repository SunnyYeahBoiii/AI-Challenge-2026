"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { FilterPanel } from "@/components/filter-panel";
import { ResultsPanel } from "@/components/results-panel";
import { FrameDetailDialog } from "@/components/frame-detail-dialog";
import { DresSettingsDialog } from "@/components/dres-settings-dialog";
import { ModelSettingsDialog } from "@/components/model-settings-dialog";
import { TrakeBoardPanel } from "@/components/trake-board-panel";
import { TrakeSingleSearch } from "@/components/trake-single-search";
import { TrakeChainList, type ChainEditTarget } from "@/components/trake-chain-list";
import { Icon } from "@/components/icon";
import { searchVideoFrames } from "@/lib/api";
import type { FrameResult } from "@/lib/api";
import { useDresSession } from "@/hooks/use-dres-session";
import { useSessionStorageState } from "@/hooks/use-session-storage";
import { useTemporalSearch } from "@/hooks/use-temporal-search";
import { useTheme } from "@/hooks/use-theme";
import { useTrakeBoard } from "@/hooks/use-trake-board";
import { useDresSubmit } from "@/hooks/use-dres-submit";
import { SubmitStatusBadge } from "@/components/submit-status";
import { usePins } from "@/hooks/use-pins";
import { PinPanel } from "@/components/pin-panel";
import { pinKey } from "@/lib/pin-types";
import type { FrameToTrake } from "@/lib/trake-types";

type SubmissionType = "track" | "trake" | "qa" | "kis";

/** One submit button each, so one verdict slot each. */
const FRAME_DETAIL_SUBMIT_KEY = "frame-detail";
const TRAKE_BOARD_SUBMIT_KEY = "trake-board";

export default function Home() {
  const { searchResult, queryCount, hasSearched, isLoading, searchError, setSearchError, handleSearch, clearSearch } =
    useTemporalSearch();
  const dres = useDresSession();
  const { theme, toggle: toggleTheme } = useTheme();

  const [selectedFrame, setSelectedFrame] = useState<FrameResult | null>(null);
  const [showDresSettings, setShowDresSettings] = useState(false);
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [viewMode, setViewMode] = useState<"grouped" | "continuous">("grouped");
  const [gridCols, setGridCols] = useState(6);
  const [submissionType, setSubmissionType] = useSessionStorageState<SubmissionType>(
    "submissionType",
    "kis",
  );

  // Submission state
  const [frameId, setFrameId] = useState("");
  const [videoId, setVideoId] = useState("");
  const [timeSec, setTimeSec] = useState("");
  const [qaAnswer, setQaAnswer] = useState("");
  const [trakeFrameIds, setTrakeFrameIds] = useState<number[] | null>(null);

  const trake = useTrakeBoard(submissionType === "track");
  const dresSubmit = useDresSubmit(dres.sessionId, dres.evaluationId);
  const pins = usePins();

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
    setChainEdits({});
    setEditingChain(null);
  }, [clearSearch]);

  const handleFrameSelect = useCallback((frame: FrameResult) => {
    setFrameId(String(frame.frame_idx));
    setVideoId(frame.video_id);
    setTimeSec(frame.timestamp.toFixed(1));
  }, []);

  const [chainEdits, setChainEdits] = useState<Record<string, number[]>>({});
  const [editingChain, setEditingChain] = useState<ChainEditTarget | null>(null);

  const handleTrakeSingleSearch = useCallback(
    (lines: string[]) => {
      setChainEdits({});
      setEditingChain(null);
      handleSearch({
        queries: lines.map((content, i) => ({
          id: `trake-${i}`,
          type: "text" as const,
          content,
          enabled: true,
          topK: 1000,
          enhance: true,
        })),
        mode: "sequential",
        temporalWindowSeconds: 90,
      });
    },
    [handleSearch],
  );

  const handleChainFrameEdit = useCallback((target: ChainEditTarget) => {
    setEditingChain(target);
    setSelectedFrame(target.frame);
  }, []);

  const handleSaveChainFrame = useCallback(
    (frameIdx: number) => {
      if (!editingChain) return;
      setChainEdits((prev) => {
        const next = [...editingChain.frameIds];
        next[editingChain.eventIndex] = frameIdx;
        return { ...prev, [editingChain.sequenceId]: next };
      });
      setEditingChain(null);
      setSelectedFrame(null);
    },
    [editingChain],
  );

  const handleChainSubmit = useCallback(
    (chainVideoId: string, frameIds: number[], sequenceId: string) => {
      setVideoId(chainVideoId);
      setTrakeFrameIds(frameIds);
      setFrameId(String(frameIds[0] ?? ""));
      setTimeSec("0");
      void dresSubmit.submit(`chain:${sequenceId}`, {
        kind: "trake",
        videoId: chainVideoId,
        frameIds,
      });
    },
    [dresSubmit],
  );

  const handleFrameDetail = useCallback((frame: FrameResult) => {
    setSelectedFrame(frame);
  }, []);

  // Pins carry only frame-level fields; fetch the real FrameResult (with
  // video_url, ocr/asr text, etc.) so the pin can open the same detail dialog.
  const handleOpenPin = useCallback(async (pin: { videoId: string; frameIndex: number }) => {
    try {
      const res = await searchVideoFrames(pin.videoId, pin.frameIndex, 1);
      const match =
        res.results.find((f) => f.frame_index === pin.frameIndex) ?? res.results[0];
      if (match) {
        setSelectedFrame(match);
        handleFrameSelect(match);
      }
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Failed to open pinned frame");
    }
  }, [handleFrameSelect, setSearchError]);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      {submissionType === "trake" ? (
        <TrakeSingleSearch
          onSearch={handleTrakeSingleSearch}
          onClear={handleClear}
          onValidationError={setSearchError}
          isLoading={isLoading}
        />
      ) : (
        <FilterPanel
          onSearch={handleSearch}
          onClear={handleClear}
          onValidationError={setSearchError}
          isLoading={isLoading}
          gridCols={gridCols}
          onGridColsChange={setGridCols}
        />
      )}

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
              {(
                [
                  { value: "track", label: "TRAKE Colab" },
                  { value: "trake", label: "TRAKE" },
                  { value: "kis", label: "KIS" },
                  { value: "qa", label: "QA" },
                ] as const
              ).map(({ value, label }) => (
                <label key={value} className="flex items-center gap-1 px-2 cursor-pointer">
                  <input
                    type="radio"
                    name="search_type"
                    checked={submissionType === value}
                    onChange={() => setSubmissionType(value)}
                    className="text-primary focus:ring-primary h-3 w-3"
                  />
                  <span className="text-label-sm text-on-surface-variant">
                    {label}
                  </span>
                </label>
              ))}
            </div>

          </div>

          <div className="flex items-center gap-3 shrink-0 whitespace-nowrap ml-auto">
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
            <button
              onClick={() => setShowModelSettings(true)}
              className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors text-label-md text-on-surface-variant"
            >
              <Icon name="model_training" size={18} />
              Model Settings
            </button>
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
        {submissionType === "trake" ? (
          <TrakeChainList
            result={searchResult}
            isLoading={isLoading}
            hasSearched={hasSearched}
            edits={chainEdits}
            onSubmitChain={handleChainSubmit}
            submitStates={dresSubmit.states}
            onEditFrame={handleChainFrameEdit}
          />
        ) : (
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
          pinnedKeys={pins.pinnedKeys}
          onTogglePin={(frame) =>
            pins.toggle({
              videoId: frame.video_id,
              frameIndex: frame.frame_index,
              timestamp: frame.timestamp,
              fps: frame.fps,
              thumbnailUrl: frame.thumbnail_url,
            })
          }
        />
        )}
      </div>

      {submissionType === "track" && (
        <TrakeBoardPanel
          trake={trake}
          submitState={dresSubmit.states[TRAKE_BOARD_SUBMIT_KEY]}
          onSubmitTrake={({ videoId: v, frameIds }) => {
            setVideoId(v);
            setTrakeFrameIds(frameIds);
            setFrameId(String(frameIds[0] ?? ""));
            setTimeSec("0");
            void dresSubmit.submit(TRAKE_BOARD_SUBMIT_KEY, {
              kind: "trake",
              videoId: v,
              frameIds,
            });
          }}
        />
      )}

      {/* Dialogs */}
      {selectedFrame && (
        <FrameDetailDialog
          frame={selectedFrame}
          submissionType={submissionType === "trake" ? "kis" : submissionType}
          onClose={() => {
            setSelectedFrame(null);
            setEditingChain(null);
          }}
          onSaveChainFrame={editingChain ? handleSaveChainFrame : undefined}
          chainEventLabel={
            editingChain
              ? `Event ${editingChain.eventIndex + 1}/${editingChain.frameIds.length}`
              : undefined
          }
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
          submitState={dresSubmit.states[FRAME_DETAIL_SUBMIT_KEY]}
          pinned={pins.pinnedKeys.has(pinKey(selectedFrame.video_id, selectedFrame.frame_index))}
          onTogglePin={() =>
            pins.toggle({
              videoId: selectedFrame.video_id,
              frameIndex: selectedFrame.frame_index,
              timestamp: selectedFrame.timestamp,
              fps: selectedFrame.fps,
              thumbnailUrl: selectedFrame.thumbnail_url,
            })
          }
          onSubmit={(submission) => {
            setFrameId(submission.frameId);
            setVideoId(submission.videoId);
            setTimeSec(submission.timeSec);
            setQaAnswer(submission.answer ?? "");
            setTrakeFrameIds(null);
            void dresSubmit.submit(FRAME_DETAIL_SUBMIT_KEY, {
              kind: "frame",
              frameId: submission.frameId,
              videoId: submission.videoId,
              timestamp: Number.parseFloat(submission.timeSec) || 0,
              submissionType: submissionType === "trake" ? "kis" : submissionType,
              answer: submission.answer,
            });
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

      <PinPanel
        pins={pins}
        onOpenPin={handleOpenPin}
        submissionType={submissionType === "trake" ? "kis" : submissionType}
        dresSessionId={dres.sessionId}
        dresEvaluationId={dres.evaluationId}
      />
    </div>
  );
}
