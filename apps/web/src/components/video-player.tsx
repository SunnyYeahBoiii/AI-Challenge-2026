"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

// ponytail: minimal YT types, pull @types/youtube if full coverage needed
interface YTPlayer {
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  pauseVideo(): void;
  getCurrentTime(): number;
  getPlayerState(): number;
  destroy(): void;
}

declare global {
  interface Window {
    YT?: {
      Player: new (
        id: string | HTMLElement,
        opts: {
          videoId: string;
          playerVars?: Record<string, string | number>;
          events?: {
            onReady?: (e: { target: YTPlayer }) => void;
            onStateChange?: (e: { data: number }) => void;
            onError?: (e: { data: number }) => void;
          };
        },
      ) => YTPlayer;
      PlayerState: {
        PLAYING: number;
        PAUSED: number;
        BUFFERING: number;
        ENDED: number;
        UNSTARTED: number;
        CUED: number;
      };
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

export interface VideoPlayerHandle {
  seekTo(seconds: number): void;
  getCurrentTime(): number;
  play(): void;
  pause(): void;
}

interface VideoPlayerProps {
  watchUrl: string;
  initialTime?: number;
  onTimeUpdate?: (currentTime: number) => void;
  onReady?: () => void;
  onStateChange?: (state: number) => void;
}

function extractVideoId(url: string | undefined): string | null {
  if (!url) return null;
  const m = url.match(
    /(?:v=|youtu\.be\/|youtube\.com\/embed\/)([\w-]+)/,
  );
  return m?.[1] ?? null;
}

function useYouTubeApi(): boolean {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (window.YT?.Player) {
      setReady(true);
      return;
    }
    if (!document.querySelector('script[src*="iframe_api"]')) {
      const s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(s);
    }
    window.onYouTubeIframeAPIReady = () => setReady(true);
  }, []);

  return ready;
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ watchUrl, initialTime, onTimeUpdate, onReady, onStateChange }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const playerRef = useRef<YTPlayer | null>(null);
    const intervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
    const apiReady = useYouTubeApi();
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    const cbs = useRef({ onTimeUpdate, onReady, onStateChange, initialTime });
    cbs.current = { onTimeUpdate, onReady, onStateChange, initialTime };

    const videoId = extractVideoId(watchUrl);

    useEffect(() => {
      if (!apiReady || !videoId || !containerRef.current) return;

      setLoading(true);
      setError(null);

      // YT.Player replaces its target element with an <iframe>, which React doesn't know about.
      // Mount it on a plain node React never diffs, so unmount only ever removes containerRef's
      // whole subtree in one shot instead of trying to remove a child YT already swapped out.
      const mountNode = document.createElement("div");
      mountNode.className = "h-full w-full";
      containerRef.current.appendChild(mountNode);

      const player = new window.YT!.Player(mountNode, {
        videoId,
        playerVars: {
          autoplay: 0,
          controls: 1,
          rel: 0,
          modestbranding: 1,
          start: Math.floor(cbs.current.initialTime ?? 0),
        },
        events: {
          onReady: () => {
            setLoading(false);
            const t = cbs.current.initialTime;
            if (t !== undefined) {
              setTimeout(() => {
                player.seekTo(t, true);
              }, 0);
            }
            cbs.current.onReady?.();
          },
          onStateChange: (e) => {
            cbs.current.onStateChange?.(e.data);
            if (e.data === window.YT!.PlayerState.PLAYING) {
              if (!intervalRef.current) {
                intervalRef.current = setInterval(() => {
                  const t = playerRef.current?.getCurrentTime();
                  if (t !== undefined) cbs.current.onTimeUpdate?.(t);
                }, 250);
              }
            } else if (
              e.data === window.YT!.PlayerState.PAUSED ||
              e.data === window.YT!.PlayerState.ENDED
            ) {
              clearInterval(intervalRef.current);
              intervalRef.current = undefined;
            }
          },
          onError: () => {
            setError("Failed to load video");
            setLoading(false);
          },
        },
      });

      playerRef.current = player;

      return () => {
        clearInterval(intervalRef.current);
        intervalRef.current = undefined;
        playerRef.current = null;
        player.destroy();
        mountNode.remove();
      };
    }, [apiReady, videoId]);

    useImperativeHandle(
      ref,
      () => ({
        seekTo(seconds: number) {
          playerRef.current?.seekTo(seconds, true);
        },
        getCurrentTime() {
          return playerRef.current?.getCurrentTime() ?? 0;
        },
        play() {
          playerRef.current?.playVideo();
        },
        pause() {
          playerRef.current?.pauseVideo();
        },
      }),
      [],
    );

    if (!videoId) {
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
      <div className="relative h-full w-full bg-black">
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
