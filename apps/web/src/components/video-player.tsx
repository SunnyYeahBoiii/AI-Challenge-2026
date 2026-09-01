"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import Hls from "hls.js";

export interface VideoPlayerHandle {
  seekTo(seconds: number): void;
  getCurrentTime(): number;
  play(): void;
  pause(): void;
}

interface VideoPlayerProps {
  src: string;
  /** MinIO playlist used only when automatic CloudFront recovery is enabled. */
  fallbackSrc?: string;
  sourcePreference?: "auto" | "cloudfront" | "minio";
  poster?: string;
  initialTime?: number;
  onTimeUpdate?: (currentTime: number) => void;
  onReady?: () => void;
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, fallbackSrc, sourcePreference = "auto", poster, initialTime, onTimeUpdate, onReady }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const hlsRef = useRef<Hls | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeSrc, setActiveSrc] = useState(src);
    const fallbackStartTimeRef = useRef<number | null>(null);
    const hasUsedFallbackRef = useRef(false);

    const cbs = useRef({ onTimeUpdate, onReady });
    cbs.current = { onTimeUpdate, onReady };

    useEffect(() => {
      hasUsedFallbackRef.current = false;
      fallbackStartTimeRef.current = null;
      setActiveSrc(sourcePreference === "minio" && fallbackSrc ? fallbackSrc : src);
    }, [fallbackSrc, sourcePreference, src]);

    useEffect(() => {
      const videoEl = videoRef.current;
      if (!activeSrc || !videoEl) return;

      setLoading(true);
      setError(null);

      const ready = () => {
        setLoading(false);
        cbs.current.onReady?.();
      };
      const onTimeUpdateEvent = () => {
        cbs.current.onTimeUpdate?.(videoEl.currentTime ?? 0);
      };
      const onSeeked = () => {
        cbs.current.onTimeUpdate?.(videoEl.currentTime ?? 0);
      };
      const useFallback = () => {
        if (sourcePreference !== "auto" || !fallbackSrc || hasUsedFallbackRef.current) {
          return false;
        }
        hasUsedFallbackRef.current = true;
        fallbackStartTimeRef.current = videoEl.currentTime || initialTime || 0;
        setActiveSrc(fallbackSrc);
        return true;
      };
      const onError = () => {
        if (useFallback()) return;
        setError("Failed to load video");
        setLoading(false);
      };

      videoEl.addEventListener("loadedmetadata", ready);
      videoEl.addEventListener("timeupdate", onTimeUpdateEvent);
      videoEl.addEventListener("seeked", onSeeked);

      if (Hls.isSupported()) {
        // startPosition tells hls.js which fragment to request first, so it
        // never loads/appends fragment 0 when we actually want to start
        // elsewhere — unlike seeking after the fact, which races the
        // "startup" fragment into the SourceBuffer and can leave two
        // disjoint buffered ranges that the browser's decoder rejects.
        const hls = new Hls({
          startPosition: fallbackStartTimeRef.current ?? initialTime ?? -1,
        });
        hlsRef.current = hls;
        hls.on(Hls.Events.ERROR, (_evt, data) => {
          if (data.fatal) onError();
        });
        hls.loadSource(activeSrc);
        hls.attachMedia(videoEl);
      } else if (videoEl.canPlayType("application/vnd.apple.mpegurl")) {
        // Safari: native HLS, no startPosition equivalent — seek once
        // metadata is available.
        videoEl.src = activeSrc;
        const startTime = fallbackStartTimeRef.current ?? initialTime;
        if (startTime !== undefined) {
          videoEl.addEventListener(
            "loadedmetadata",
            () => {
              videoEl.currentTime = startTime;
            },
            { once: true },
          );
        }
        videoEl.addEventListener("error", onError);
      } else {
        onError();
      }

      return () => {
        videoEl.removeEventListener("loadedmetadata", ready);
        videoEl.removeEventListener("timeupdate", onTimeUpdateEvent);
        videoEl.removeEventListener("seeked", onSeeked);
        videoEl.removeEventListener("error", onError);
        hlsRef.current?.destroy();
        hlsRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps -- poster/initialTime only apply when (re)mounting for a new source
    }, [activeSrc, fallbackSrc, sourcePreference]);

    useImperativeHandle(
      ref,
      () => ({
        seekTo(seconds: number) {
          if (videoRef.current) videoRef.current.currentTime = seconds;
        },
        getCurrentTime() {
          return videoRef.current?.currentTime ?? 0;
        },
        play() {
          videoRef.current?.play();
        },
        pause() {
          videoRef.current?.pause();
        },
      }),
      [],
    );

    if (!activeSrc) {
      return (
        <div className="flex h-full w-full items-center justify-center bg-black font-mono text-mono-sm text-gray-400">
          Invalid video URL
        </div>
      );
    }

    return (
      <div className="relative h-full w-full overflow-hidden bg-black">
        <video
          ref={videoRef}
          className="h-full w-full object-contain"
          controls
          playsInline
          poster={poster}
          style={{ display: error ? "none" : undefined }}
        />
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-black font-mono text-mono-sm text-gray-400">
            {error}
          </div>
        )}
        {loading && !error && (
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
