"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import videojs from "video.js";

export interface VideoPlayerHandle {
  seekTo(seconds: number): void;
  getCurrentTime(): number;
  play(): void;
  pause(): void;
}

interface VideoPlayerProps {
  src: string;
  initialTime?: number;
  onTimeUpdate?: (currentTime: number) => void;
  onReady?: () => void;
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, initialTime, onTimeUpdate, onReady }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const playerRef = useRef<ReturnType<typeof videojs> | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    const cbs = useRef({ onTimeUpdate, onReady, initialTime });
    cbs.current = { onTimeUpdate, onReady, initialTime };

    useEffect(() => {
      if (!src || !containerRef.current) return;

      setLoading(true);
      setError(null);

      // video.js's dispose() mutates/removes the DOM node it's given, which
      // crashes React's own unmount diffing if that node is React-rendered.
      // So we create the <video> imperatively, outside React's tree, and let
      // video.js own it end-to-end.
      const videoEl = document.createElement("video");
      videoEl.className = "video-js vjs-big-play-centered";
      videoEl.setAttribute("playsinline", "true");
      containerRef.current.appendChild(videoEl);

      const player = videojs(videoEl, {
        controls: true,
        preload: "auto",
        fill: true,
        sources: [{ src, type: "video/mp4" }],
        controlBar: {
          pictureInPictureToggle: false,
          fullscreenToggle: true,
        },
      });

      player.on("loadedmetadata", () => {
        setLoading(false);
        const t = cbs.current.initialTime;
        // Unlike the old YouTube iframe API, setting currentTime here never
        // auto-resumes playback, so no pause-after-seek workaround is needed.
        if (t !== undefined) player.currentTime(t);
        cbs.current.onReady?.();
      });

      player.on("timeupdate", () => {
        cbs.current.onTimeUpdate?.(player.currentTime() ?? 0);
      });

      player.on("error", () => {
        setError("Failed to load video");
        setLoading(false);
      });

      playerRef.current = player;

      return () => {
        player.dispose();
        videoEl.remove();
        playerRef.current = null;
      };
    }, [src]);

    useImperativeHandle(
      ref,
      () => ({
        seekTo(seconds: number) {
          playerRef.current?.currentTime(seconds);
        },
        getCurrentTime() {
          return playerRef.current?.currentTime() ?? 0;
        },
        play() {
          playerRef.current?.play();
        },
        pause() {
          playerRef.current?.pause();
        },
      }),
      [],
    );

    if (!src) {
      return (
        <div className="flex h-full w-full items-center justify-center bg-black font-mono text-mono-sm text-gray-400">
          Invalid video URL
        </div>
      );
    }

    if (error) {
      return (
        <div className="flex h-full w-full items-center justify-center bg-black font-mono text-mono-sm text-gray-400">
          {error}
        </div>
      );
    }

    return (
      <div className="relative h-full w-full overflow-hidden bg-black">
        <div ref={containerRef} className="h-full w-full" />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-600 border-t-white" />
              <span className="font-mono text-mono-sm text-gray-400">
                Loading player...
              </span>
            </div>
          </div>
        )}
      </div>
    );
  },
);

VideoPlayer.displayName = "VideoPlayer";
