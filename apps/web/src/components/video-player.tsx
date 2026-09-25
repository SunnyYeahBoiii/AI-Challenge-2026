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
  setPlaybackRate(rate: number): void;
  getPlaybackRate(): number;
  play(): void;
  pause(): void;
}

interface VideoPlayerProps {
  src: string;
  poster?: string;
  initialTime?: number;
  onTimeUpdate?: (currentTime: number) => void;
  onReady?: () => void;
  playbackRate?: number;
  onPlaybackRateChange?: (rate: number) => void;
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, poster, initialTime, onTimeUpdate, onReady, playbackRate = 1, onPlaybackRateChange }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const hlsRef = useRef<Hls | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    const cbs = useRef({ onTimeUpdate, onReady, onPlaybackRateChange });
    cbs.current = { onTimeUpdate, onReady, onPlaybackRateChange };

    // Mirror the controlled rate onto the element; `ratechange` reports the
    // element's own rate back, so native controls stay authoritative.
    useEffect(() => {
      const video = videoRef.current;
      if (video && Number.isFinite(playbackRate) && playbackRate > 0) {
        video.playbackRate = playbackRate;
      }
    }, [playbackRate]);

    useEffect(() => {
      const videoEl = videoRef.current;
      if (!src || !videoEl) return;

      setLoading(true);
      setError(null);

      const reportPlaybackRate = () => {
        cbs.current.onPlaybackRateChange?.(videoEl.playbackRate);
      };
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
      // `timeupdate` stops firing while paused, so a scrub or a pause would
      // otherwise leave the reported time stale.
      videoEl.addEventListener("pause", onTimeUpdateEvent);
      videoEl.addEventListener("seeked", onTimeUpdateEvent);
      videoEl.addEventListener("ratechange", reportPlaybackRate);

      if (!/\.m3u8(\?|$)/.test(src)) {
        // Plain mp4/mov over HTTP Range: the browser fetches only the byte
        // ranges it needs, so multi-GB files start and seek without a full
        // download. Seek to initialTime once the moov atom is parsed.
        videoEl.preload = "metadata";
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
      } else if (Hls.isSupported()) {
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
      } else if (videoEl.canPlayType("application/vnd.apple.mpegurl")) {
        // Safari: native HLS, no startPosition equivalent — seek once
        // metadata is available.
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
        videoEl.removeEventListener("pause", onTimeUpdateEvent);
        videoEl.removeEventListener("seeked", onTimeUpdateEvent);
        videoEl.removeEventListener("ratechange", reportPlaybackRate);
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
        setPlaybackRate(rate: number) {
          const video = videoRef.current;
          if (video && Number.isFinite(rate) && rate > 0) video.playbackRate = rate;
        },
        getPlaybackRate() {
          return videoRef.current?.playbackRate ?? 1;
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
