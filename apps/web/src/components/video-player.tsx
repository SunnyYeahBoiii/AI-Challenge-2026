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
  poster?: string;
  initialTime?: number;
  onTimeUpdate?: (currentTime: number) => void;
  onReady?: () => void;
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, poster, initialTime, onTimeUpdate, onReady }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const hlsRef = useRef<Hls | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    const cbs = useRef({ onTimeUpdate, onReady });
    cbs.current = { onTimeUpdate, onReady };

    useEffect(() => {
      const videoEl = videoRef.current;
      if (!src || !videoEl) return;

      setLoading(true);
      setError(null);

      const ready = () => {
        setLoading(false);
        cbs.current.onReady?.();
      };
      const onTimeUpdateEvent = () => {
        cbs.current.onTimeUpdate?.(videoEl.currentTime ?? 0);
      };
      const onError = () => {
        setError("Failed to load video");
        setLoading(false);
      };

      videoEl.addEventListener("loadedmetadata", ready);
      videoEl.addEventListener("timeupdate", onTimeUpdateEvent);

      const isHlsSource = /\.m3u8(?:$|\?)/i.test(src);

      if (isHlsSource && Hls.isSupported()) {
        // startPosition tells hls.js which fragment to request first, so it
        // never loads/appends fragment 0 when we actually want to start
        // elsewhere — unlike seeking after the fact, which races the
        // "startup" fragment into the SourceBuffer and can leave two
        // disjoint buffered ranges that the browser's decoder rejects.
        const hls = new Hls({
          startPosition: initialTime ?? -1,
        });
        hlsRef.current = hls;
        hls.on(Hls.Events.ERROR, (_evt, data) => {
          if (data.fatal) onError();
        });
        hls.loadSource(src);
        hls.attachMedia(videoEl);
      } else if (!isHlsSource || videoEl.canPlayType("application/vnd.apple.mpegurl")) {
        // MP4 is loaded directly. Safari also reaches this branch for native HLS.
        videoEl.src = src;
        if (initialTime !== undefined) {
          videoEl.addEventListener(
            "loadedmetadata",
            () => {
              videoEl.currentTime = initialTime;
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
        videoEl.removeEventListener("error", onError);
        hlsRef.current?.destroy();
        hlsRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps -- poster/initialTime only apply when (re)mounting for a new src
    }, [src]);

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

    if (!src) {
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
