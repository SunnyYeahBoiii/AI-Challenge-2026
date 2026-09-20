"use client";

import { useState } from "react";
import { Icon } from "./icon";
import type { PinsApi } from "@/hooks/use-pins";
import type { PinSnapshot } from "@/lib/pin-types";

interface PinPanelProps {
  pins: PinsApi;
  onOpenPin: (pin: PinSnapshot) => void;
}

/**
 * The shared pin wall, hovering over the right edge of the results area.
 *
 * It floats rather than taking a column because results already compete with
 * the TRAKE board for width; collapsing leaves only a tab with the count, so
 * the wall never hides a row of keyframes while someone is scanning.
 */
export function PinPanel({ pins, onOpenPin }: PinPanelProps) {
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);

  if (hidden) {
    return (
      <button
        onClick={() => setHidden(false)}
        title="Show pinned keyframes"
        aria-label="Show pinned keyframes"
        className="fixed right-0 bottom-4 z-30 rounded-l bg-surface-container-high border border-r-0 border-outline-variant px-2 py-2 text-on-surface-variant hover:bg-surface-container-highest transition-colors"
      >
        <Icon name="keep" size={18} />
      </button>
    );
  }

  return (
    <div className="fixed right-0 top-1/2 -translate-y-1/2 z-30 flex items-stretch">
      <button
        onClick={() => setOpen((v) => !v)}
        title={open ? "Minimize pinned keyframes" : "Show pinned keyframes"}
        aria-expanded={open}
        className="self-center rounded-l-lg bg-surface-container-high border border-r-0 border-outline-variant px-1.5 py-4 text-on-surface-variant hover:bg-surface-container-highest transition-colors"
      >
        <div className="flex flex-col items-center gap-1">
          <Icon name={open ? "chevron_right" : "chevron_left"} size={16} />
          <span className="text-label-xs font-bold">{pins.pins.length}</span>
        </div>
      </button>

      {open && (
        <aside className="w-56 max-h-[70vh] flex flex-col bg-surface-container-lowest border border-outline-variant rounded-l-lg shadow-2xl">
          <header className="flex items-center gap-1 px-2 py-1.5 border-b border-outline-variant shrink-0">
            <Icon name="keep" size={16} />
            <span className="text-label-md font-bold">Pinned</span>
            <span
              title={pins.connected ? "Connected to cloud-api" : "Offline"}
              className={`h-2 w-2 rounded-full ${pins.connected ? "bg-green-500" : "bg-gray-400"}`}
            />
            <button
              onClick={pins.clear}
              disabled={pins.pins.length === 0}
              title="Unpin everything for everyone"
              className="ml-auto text-label-sm text-on-surface-variant hover:text-error disabled:opacity-40 transition-colors"
            >
              Clear all
            </button>
            <button
              onClick={() => setHidden(true)}
              title="Hide the pin panel"
              aria-label="Hide the pin panel"
              className="text-on-surface-variant hover:text-on-surface transition-colors"
            >
              <Icon name="close" size={16} />
            </button>
          </header>

          {pins.pins.length === 0 ? (
            <p className="px-3 py-6 text-center text-body-sm text-on-surface-variant">
              No pins yet. Pin a keyframe to share it with the team.
            </p>
          ) : (
            <div className="flex-1 overflow-y-auto p-2 space-y-2">
              {pins.pins.map((pin) => (
                <div key={pin.id} className="relative group">
                  <button
                    onClick={() => onOpenPin(pin)}
                    title={`${pin.videoId} · frame ${pin.frameIndex}`}
                    className="block w-full text-left"
                  >
                    {pin.thumbnailUrl ? (
                      <img
                        src={pin.thumbnailUrl}
                        alt={`${pin.videoId} frame ${pin.frameIndex}`}
                        loading="lazy"
                        className="w-full aspect-video object-cover rounded border border-outline-variant group-hover:ring-2 group-hover:ring-primary transition"
                      />
                    ) : (
                      <div className="w-full aspect-video rounded border border-outline-variant bg-surface-container" />
                    )}
                    <div className="mt-0.5 font-mono text-mono-sm text-on-surface-variant truncate">
                      {pin.videoId} #{pin.frameIndex}
                    </div>
                  </button>
                  <button
                    onClick={() => pins.remove(pin.videoId, pin.frameIndex)}
                    title="Unpin"
                    aria-label={`Unpin ${pin.videoId} frame ${pin.frameIndex}`}
                    className="absolute top-1 right-1 p-1 rounded bg-black/60 text-white opacity-0 group-hover:opacity-100 hover:bg-error transition-opacity"
                  >
                    <Icon name="close" size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </aside>
      )}
    </div>
  );
}
