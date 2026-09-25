"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";
import { cloudApiHttpBase } from "@/lib/cloud-api";
import type {
  TrakeBoardSnapshot,
  TrakeCandidatePayload,
} from "@/lib/trake-types";
import { TRAKE_DISPLAY_NAME_KEY } from "@/lib/trake-types";

export function useTrakeBoard(enabled: boolean) {
  const socketRef = useRef<Socket | null>(null);
  const [board, setBoard] = useState<TrakeBoardSnapshot | null>(null);
  const [displayName, setDisplayName] = useState("teammate");
  const displayNameRef = useRef(displayName);
  const [focusedEventId, setFocusedEventId] = useState<string | null>(null);
  const [status, setStatus] = useState<
    "idle" | "connecting" | "connected" | "error"
  >("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const storedName =
      typeof window !== "undefined"
        ? localStorage.getItem(TRAKE_DISPLAY_NAME_KEY)
        : null;
    if (storedName) {
      setDisplayName(storedName);
      displayNameRef.current = storedName;
    }
  }, []);

  const applyBoard = useCallback((snapshot: TrakeBoardSnapshot) => {
    setBoard(snapshot);
    setFocusedEventId((prev) => {
      if (prev && snapshot.events.some((e) => e.id === prev)) return prev;
      return snapshot.events[0]?.id ?? null;
    });
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const socket = io(cloudApiHttpBase(), {
      transports: ["websocket", "polling"],
    });
    socketRef.current = socket;
    setStatus("connecting");
    setError(null);
    setBoard(null);
    socket.on("connect", () => {
      setStatus("connecting");
      socket.emit("board:join", { displayName: displayNameRef.current });
    });
    socket.on("board:state", (snapshot: TrakeBoardSnapshot) => {
      applyBoard(snapshot);
      setStatus("connected");
      setError(null);
    });
    socket.on("exception", (response: { message?: string }) => {
      setStatus("error");
      setError(response.message || "Board operation failed");
    });
    socket.on("connect_error", (err) => {
      setStatus("error");
      setError(err.message || "Failed to connect to cloud-api");
      setBoard(null);
    });
    socket.on("disconnect", () => {
      setStatus((s) => (s === "error" ? s : "idle"));
      setBoard(null);
    });
    return () => {
      socket.disconnect();
      socketRef.current = null;
    };
  }, [enabled, applyBoard]);

  const saveDisplayName = useCallback((name: string) => {
    const n = name.trim() || "teammate";
    setDisplayName(n);
    displayNameRef.current = n;
    localStorage.setItem(TRAKE_DISPLAY_NAME_KEY, n);
    socketRef.current?.emit("board:rename", { displayName: n });
  }, []);

  const emit = useCallback((event: string, payload: unknown) => {
    socketRef.current?.emit(event, payload);
  }, []);

  const addEvent = useCallback(
    (labelText = "") => {
      if (!board) return;
      emit("event:add", { labelText });
    },
    [board, emit],
  );

  const removeEvent = useCallback(
    (eventId: string) => {
      if (!board) return;
      emit("event:remove", { eventId });
    },
    [board, emit],
  );

  const reorderEvents = useCallback(
    (orderedEventIds: string[]) => {
      if (!board) return;
      emit("event:reorder", { orderedEventIds });
    },
    [board, emit],
  );

  const updateEventText = useCallback(
    (eventId: string, labelText: string) => {
      if (!board) return;
      emit("event:updateText", { eventId, labelText });
    },
    [board, emit],
  );

  const addCandidate = useCallback(
    (payload: TrakeCandidatePayload) => {
      if (!board) return;
      emit("candidate:add", {
        ...payload,
        addedBy: payload.addedBy ?? displayName,
      });
    },
    [board, displayName, emit],
  );

  const removeCandidate = useCallback(
    (candidateId: string) => {
      if (!board) return;
      emit("candidate:remove", { candidateId });
    },
    [board, emit],
  );

  const setSelection = useCallback(
    (input: {
      eventId: string;
      videoId: string;
      ptsTime: number;
      previewFrameId: string;
      fps: number;
      candidateId?: string | null;
    }) => {
      if (!board) return;
      emit("selection:set", {
        ...input,
        updatedBy: displayName,
      });
    },
    [board, displayName, emit],
  );

  const clearSelection = useCallback(
    (eventId: string) => {
      if (!board) return;
      emit("selection:clear", { eventId });
    },
    [board, emit],
  );

  const focusedEvent =
    board?.events.find((e) => e.id === focusedEventId) ?? null;

  return {
    board,
    displayName,
    focusedEventId,
    focusedEvent,
    status,
    error,
    setFocusedEventId,
    saveDisplayName,
    addEvent,
    removeEvent,
    reorderEvents,
    updateEventText,
    addCandidate,
    removeCandidate,
    setSelection,
    clearSelection,
  };
}

export type TrakeBoardApi = ReturnType<typeof useTrakeBoard>;
