"use client";

import { useEffect, useMemo, useState } from "react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Icon } from "./icon";
import type { TrakeBoardApi } from "@/hooks/use-trake-board";
import type { TrakeCandidate, TrakeEvent } from "@/lib/trake-types";
import { TRAKE_FRAME_MIME } from "@/lib/trake-types";
import {
  buildTrakeSubmitText,
  selectionFrameId,
} from "@/lib/cloud-api";
import {
  getNearestKeyframe,
  type FrameResult,
  type KeyframeInfo,
} from "@/lib/api";
import { VideoPlayer } from "./video-player";
import { SubmitStatusBadge } from "./submit-status";
import type { DresSubmitState } from "@/hooks/use-dres-submit";

interface TrakeBoardPanelProps {
  trake: TrakeBoardApi;
  onSubmitTrake: (payload: {
    videoId: string;
    frameIds: number[];
    previewText: string;
  }) => void;
  /** Verdict of the last board submit; the confirm dialog is gone. */
  submitState?: DresSubmitState;
}

function SortableEventCard({
  event,
  focused,
  onFocus,
  onRemove,
  onUpdateText,
  onRemoveCandidate,
  onSetSelection,
  onClearSelection,
  onDropFrame,
  onPlayVideo,
}: {
  event: TrakeEvent;
  focused: boolean;
  onFocus: () => void;
  onRemove: () => void;
  onUpdateText: (text: string) => void;
  onRemoveCandidate: (id: string) => void;
  onSetSelection: (c: TrakeCandidate) => void;
  onClearSelection: () => void;
  onDropFrame: (frame: FrameResult) => void;
  onPlayVideo: (c: TrakeCandidate) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: event.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      onClick={onFocus}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(TRAKE_FRAME_MIME)) {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        const raw = e.dataTransfer.getData(TRAKE_FRAME_MIME);
        if (!raw) return;
        try {
          onDropFrame(JSON.parse(raw) as FrameResult);
        } catch {
          /* ignore */
        }
      }}
      className={`rounded-lg border p-2 space-y-2 cursor-pointer ${
        focused
          ? "border-primary-container bg-primary-container/10"
          : "border-outline-variant bg-surface-container-low"
      }`}
    >
      <div className="flex items-center gap-1">
        <button
          type="button"
          className="p-0.5 text-on-surface-variant hover:text-on-surface cursor-grab"
          aria-label="Drag to reorder event"
          {...attributes}
          {...listeners}
          onClick={(e) => e.stopPropagation()}
        >
          <Icon name="drag_indicator" size={16} />
        </button>
        <span className="text-label-md font-bold">{event.displayLabel}</span>
        <input
          className="flex-1 min-w-0 bg-transparent border-b border-transparent focus:border-outline-variant text-label-sm px-1"
          value={event.labelText}
          placeholder="Event description…"
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onUpdateText(e.target.value)}
        />
        <button
          type="button"
          className="p-0.5 text-on-surface-variant hover:text-red-500"
          aria-label="Remove event"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
        >
          <Icon name="close" size={14} />
        </button>
      </div>

      <div className="rounded border border-dashed border-outline-variant p-1.5">
        <div className="text-label-sm text-on-surface-variant mb-1">
          Selection
        </div>
        {event.selection ? (
          <div className="flex items-center gap-2">
            {event.selection.previewFrameId && (
              <span className="text-mono-sm">
                t={event.selection.ptsTime.toFixed(2)}s · fid=
                {selectionFrameId(
                  event.selection.ptsTime,
                  event.selection.fps,
                )}
              </span>
            )}
            <button
              type="button"
              className="ml-auto text-label-sm text-on-surface-variant hover:text-on-surface"
              onClick={(e) => {
                e.stopPropagation();
                onClearSelection();
              }}
            >
              Clear
            </button>
          </div>
        ) : (
          <p className="text-label-sm text-on-surface-variant italic">
            Drop a frame or promote a candidate
          </p>
        )}
      </div>

      <div className="space-y-1 max-h-40 overflow-y-auto">
        <div className="text-label-sm text-on-surface-variant">
          Candidates ({event.candidates.length})
        </div>
        {event.candidates.map((c) => (
          <div
            key={c.id}
            className="flex items-center gap-2 rounded bg-surface-container-lowest p-1"
          >
            <button
              type="button"
              className="shrink-0"
              aria-label="Play video"
              title="Play video"
              onClick={(e) => {
                e.stopPropagation();
                onPlayVideo(c);
              }}
            >
              {c.thumbnailUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={c.thumbnailUrl}
                  alt=""
                  className="w-12 h-8 object-cover rounded"
                />
              ) : (
                <div className="w-12 h-8 bg-surface-container rounded" />
              )}
            </button>
            <div className="flex-1 min-w-0 text-mono-sm truncate">
              {c.videoId} · {c.ptsTime.toFixed(2)}s
            </div>
            <button
              type="button"
              className="text-label-sm px-1.5 py-0.5 rounded bg-primary-container text-on-primary-container"
              onClick={(e) => {
                e.stopPropagation();
                onSetSelection(c);
              }}
            >
              Select
            </button>
            <button
              type="button"
              className="p-0.5 text-on-surface-variant hover:text-red-500"
              aria-label="Remove candidate"
              onClick={(e) => {
                e.stopPropagation();
                onRemoveCandidate(c.id);
              }}
            >
              <Icon name="delete" size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TrakeBoardPanel({ trake, onSubmitTrake, submitState }: TrakeBoardPanelProps) {
  const [nameDraft, setNameDraft] = useState(trake.displayName);
  useEffect(() => setNameDraft(trake.displayName), [trake.displayName]);
  const [videoCandidate, setVideoCandidate] = useState<TrakeCandidate | null>(
    null,
  );
  const [candidateVideo, setCandidateVideo] = useState<KeyframeInfo | null>(
    null,
  );
  const [videoError, setVideoError] = useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  useEffect(() => {
    let cancelled = false;
    setCandidateVideo(null);
    setVideoError(false);
    if (!videoCandidate) return;
    getNearestKeyframe(videoCandidate.videoId, videoCandidate.frameIdx).then(
      (kf) => {
        if (cancelled) return;
        if (kf) setCandidateVideo(kf);
        else setVideoError(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [videoCandidate]);

  const readyPayload = useMemo(() => {
    const { board } = trake;
    if (!board || board.events.length === 0) return null;
    if (!board.events.every((e) => e.selection)) return null;
    const videoId = board.targetVideoId;
    if (!videoId) return null;
    if (board.events.some((e) => e.selection!.videoId !== videoId)) return null;
    const frameIds = board.events.map((e) =>
      selectionFrameId(e.selection!.ptsTime, e.selection!.fps),
    );
    return {
      videoId,
      frameIds,
      previewText: buildTrakeSubmitText(videoId, frameIds),
    };
  }, [trake]);

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || !trake.board || active.id === over.id) return;
    const ids = trake.board.events.map((e) => e.id);
    const oldIndex = ids.indexOf(String(active.id));
    const newIndex = ids.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    trake.reorderEvents(arrayMove(ids, oldIndex, newIndex));
  };

  return (
    <>
      <aside className="w-80 flex-shrink-0 border-l border-outline-variant bg-surface-container-lowest flex flex-col overflow-hidden">
      <div className="px-3 py-2 border-b border-outline-variant space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-label-md font-semibold">TRAKE Board</h2>
          <span className="text-label-sm text-on-surface-variant">
            {trake.status}
          </span>
        </div>
        <input
          className="w-full rounded border border-outline-variant bg-surface px-2 py-1 text-label-sm"
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={() => trake.saveDisplayName(nameDraft)}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
          placeholder="Display name"
          aria-label="Display name"
        />
        {trake.error && (
          <p className="text-label-sm text-red-500">{trake.error}</p>
        )}
        {trake.board && (
          <p className="text-label-sm text-on-surface-variant">
            Online: {trake.board.members.join(", ") || "—"}
            {trake.board.targetVideoId
              ? ` · Target: ${trake.board.targetVideoId}`
              : ""}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {!trake.board ? (
          <p className="text-label-sm text-on-surface-variant p-2">
            {trake.error
              ? "Shared TRAKE board unavailable."
              : "Connecting to the shared TRAKE board…"}
          </p>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={onDragEnd}
          >
            <SortableContext
              items={trake.board.events.map((e) => e.id)}
              strategy={verticalListSortingStrategy}
            >
              {trake.board.events.map((event) => (
                <SortableEventCard
                  key={event.id}
                  event={event}
                  focused={trake.focusedEventId === event.id}
                  onFocus={() => trake.setFocusedEventId(event.id)}
                  onRemove={() => trake.removeEvent(event.id)}
                  onUpdateText={(text) =>
                    trake.updateEventText(event.id, text)
                  }
                  onRemoveCandidate={(id) => trake.removeCandidate(id)}
                  onSetSelection={(c) =>
                    trake.setSelection({
                      eventId: event.id,
                      videoId: c.videoId,
                      ptsTime: c.ptsTime,
                      previewFrameId: c.previewFrameId,
                      fps: c.fps,
                      candidateId: c.id,
                    })
                  }
                  onClearSelection={() => trake.clearSelection(event.id)}
                  onPlayVideo={setVideoCandidate}
                  onDropFrame={(frame) => {
                    trake.setFocusedEventId(event.id);
                    trake.addCandidate({
                      eventId: event.id,
                      videoId: frame.video_id,
                      ptsTime: frame.timestamp,
                      previewFrameId: String(frame.frame_idx),
                      fps: frame.fps,
                      frameIdx: frame.frame_idx,
                      thumbnailUrl: frame.thumbnail_url,
                    });
                  }}
                />
              ))}
            </SortableContext>
          </DndContext>
        )}
      </div>

      <div className="border-t border-outline-variant p-2 space-y-2">
        <button
          type="button"
          disabled={!trake.board}
          onClick={() => trake.addEvent()}
          className="w-full rounded border border-outline-variant py-1.5 text-label-sm disabled:opacity-50"
        >
          + Add Event
        </button>
        <button
          type="button"
          disabled={!readyPayload}
          onClick={() => readyPayload && onSubmitTrake(readyPayload)}
          className="w-full rounded bg-primary-container text-on-primary-container py-2 text-label-md font-bold disabled:opacity-40"
        >
          Submit TRAKE
        </button>
        {submitState && (
          <div className="flex justify-center">
            <SubmitStatusBadge state={submitState} />
          </div>
        )}
        {readyPayload && (
          <p className="text-mono-sm text-on-surface-variant break-all">
            {readyPayload.previewText}
          </p>
        )}
      </div>
      </aside>

      {videoCandidate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm"
          onClick={() => setVideoCandidate(null)}
        >
          <div
            className="relative w-full max-w-6xl h-[80vh] bg-black rounded-lg overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setVideoCandidate(null)}
              className="absolute top-4 right-4 z-10 text-white hover:bg-white/10 rounded-full p-2 transition-colors"
              aria-label="Close video"
            >
              <Icon name="close" size={24} />
            </button>
            <div className="absolute top-4 left-4 z-10 bg-black/70 rounded px-3 py-2 text-white">
              <div className="text-body-xs text-gray-300">
                {videoCandidate.videoId} · t=
                {videoCandidate.ptsTime.toFixed(2)}s
              </div>
            </div>
            {candidateVideo ? (
              <VideoPlayer
                src={candidateVideo.video_url}
                poster={videoCandidate.thumbnailUrl || undefined}
                initialTime={videoCandidate.ptsTime}
              />
            ) : (
              <div className="flex h-full items-center justify-center overflow-hidden bg-black font-mono text-mono-sm text-gray-400">
                {videoError ? "Failed to load video" : "Loading video…"}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
