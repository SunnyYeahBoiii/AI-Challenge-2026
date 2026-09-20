"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";
import { cloudApiHttpBase } from "@/lib/cloud-api";
import { pinKey, type PinInput, type PinSnapshot } from "@/lib/pin-types";

/**
 * The shared pin wall over cloud-api's PinGateway.
 *
 * There is no auth and no room to join (ADR 0005: tailnet only) — every
 * connected teammate sees the same wall, and anyone may unpin or clear it.
 * State is server-owned: every mutation is fire-and-forget and the truth
 * arrives back on `pins:changed`.
 */
export function usePins() {
  const socketRef = useRef<Socket | null>(null);
  const [pins, setPins] = useState<PinSnapshot[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const socket = io(cloudApiHttpBase(), {
      transports: ["websocket", "polling"],
    });
    socketRef.current = socket;
    socket.on("connect", () => {
      setConnected(true);
      socket.emit("pin:list");
    });
    socket.on("pins:changed", (next: PinSnapshot[]) => setPins(next));
    socket.on("disconnect", () => setConnected(false));
    socket.on("connect_error", () => setConnected(false));
    return () => {
      socket.disconnect();
      socketRef.current = null;
    };
  }, []);

  const pinnedKeys = useMemo(
    () => new Set(pins.map((p) => pinKey(p.videoId, p.frameIndex))),
    [pins],
  );

  const add = useCallback((input: PinInput) => {
    socketRef.current?.emit("pin:add", input);
  }, []);

  const remove = useCallback((videoId: string, frameIndex: number) => {
    socketRef.current?.emit("pin:remove", { videoId, frameIndex });
  }, []);

  const toggle = useCallback(
    (input: PinInput) => {
      if (pinnedKeys.has(pinKey(input.videoId, input.frameIndex))) {
        socketRef.current?.emit("pin:remove", {
          videoId: input.videoId,
          frameIndex: input.frameIndex,
        });
        return;
      }
      socketRef.current?.emit("pin:add", input);
    },
    [pinnedKeys],
  );

  const clear = useCallback(() => {
    socketRef.current?.emit("pin:clear");
  }, []);

  return { pins, pinnedKeys, connected, add, remove, toggle, clear };
}

export type PinsApi = ReturnType<typeof usePins>;
