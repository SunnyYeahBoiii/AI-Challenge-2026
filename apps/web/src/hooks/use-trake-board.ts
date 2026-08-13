"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";
import {
  createTrakeBoard,
  fetchTrakeBoard,
  trakeColabHttpBase,
} from "@/lib/trake-colab";
import type {
  TrakeBoardSnapshot,
  TrakeCandidatePayload,
} from "@/lib/trake-types";
import {
  TRAKE_BOARD_ID_KEY,
  TRAKE_DISPLAY_NAME_KEY,
} from "@/lib/trake-types";

export function useTrakeBoard(enabled: boolean) {
  const socketRef = useRef<Socket | null>(null);
  const [board, setBoard] = useState<TrakeBoardSnapshot | null>(null);
  const [boardId, setBoardId] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("teammate");
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
    if (storedName) setDisplayName(storedName);
    const storedBoard =
      typeof window !== "undefined"
        ? localStorage.getItem(TRAKE_BOARD_ID_KEY)
        : null;
    if (storedBoard) setBoardId(storedBoard);
  }, []);

  const applyBoard = useCallback((snapshot: TrakeBoardSnapshot) => {
    setBoard(snapshot);
    setBoardId(snapshot.id);
    localStorage.setItem(TRAKE_BOARD_ID_KEY, snapshot.id);
    setFocusedEventId((prev) => {
      if (prev && snapshot.events.some((e) => e.id === prev)) return prev;
      return snapshot.events[0]?.id ?? null;
    });
  }, []);

  const connect = useCallback(
    (id: string, name: string) => {
      setStatus("connecting");
      setError(null);
      socketRef.current?.disconnect();
      const socket = io(trakeColabHttpBase(), {
        transports: ["websocket", "polling"],
        autoConnect: true,
      });
      socketRef.current = socket;
      socket.on("connect", () => {
        setStatus("connected");
        socket.emit("board:join", { boardId: id, displayName: name });
      });
      socket.on("board:state", (snapshot: TrakeBoardSnapshot) => {
        applyBoard(snapshot);
      });
      socket.on("connect_error", (err) => {
        setStatus("error");
        setError(err.message || "Failed to connect to trake-colab");
      });
      socket.on("disconnect", () => {
        setStatus((s) => (s === "error" ? s : "idle"));
      });
    },
    [applyBoard],
  );

  useEffect(() => {
    if (!enabled || !boardId) return;
    connect(boardId, displayName);
    return () => {
      socketRef.current?.disconnect();
      socketRef.current = null;
    };
  }, [enabled, boardId, displayName, connect]);

  const createAndJoin = useCallback(async () => {
    try {
      const snapshot = await createTrakeBoard();
      localStorage.setItem(TRAKE_BOARD_ID_KEY, snapshot.id);
      localStorage.setItem(TRAKE_DISPLAY_NAME_KEY, displayName);
      setBoardId(snapshot.id);
      applyBoard(snapshot);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
      setStatus("error");
    }
  }, [applyBoard, displayName]);

  const joinBoard = useCallback(
    async (id: string) => {
      const trimmed = id.trim().toUpperCase();
      if (!/^[A-Z0-9]{6}$/.test(trimmed)) {
        setError("Board id must be exactly 6 characters");
        setStatus("error");
        return;
      }
      try {
        const snapshot = await fetchTrakeBoard(trimmed);
        localStorage.setItem(TRAKE_BOARD_ID_KEY, snapshot.id);
        localStorage.setItem(TRAKE_DISPLAY_NAME_KEY, displayName);
        setBoardId(snapshot.id);
        applyBoard(snapshot);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Join failed");
        setStatus("error");
      }
    },
    [applyBoard, displayName],
  );

  const saveDisplayName = useCallback((name: string) => {
    const n = name.trim() || "teammate";
    setDisplayName(n);
    localStorage.setItem(TRAKE_DISPLAY_NAME_KEY, n);
  }, []);

  const emit = useCallback((event: string, payload: unknown) => {
    socketRef.current?.emit(event, payload);
  }, []);

  const addEvent = useCallback(
    (labelText = "") => {
      if (!boardId) return;
      emit("event:add", { boardId, labelText });
    },
    [boardId, emit],
  );

  const removeEvent = useCallback(
    (eventId: string) => {
      if (!boardId) return;
      emit("event:remove", { boardId, eventId });
    },
    [boardId, emit],
  );

  const reorderEvents = useCallback(
    (orderedEventIds: string[]) => {
      if (!boardId) return;
      emit("event:reorder", { boardId, orderedEventIds });
    },
    [boardId, emit],
  );

  const updateEventText = useCallback(
    (eventId: string, labelText: string) => {
      if (!boardId) return;
      emit("event:updateText", { boardId, eventId, labelText });
    },
    [boardId, emit],
  );

  const addCandidate = useCallback(
    (payload: TrakeCandidatePayload) => {
      if (!boardId) return;
      emit("candidate:add", {
        boardId,
        ...payload,
        addedBy: payload.addedBy ?? displayName,
      });
    },
    [boardId, displayName, emit],
  );

  const removeCandidate = useCallback(
    (candidateId: string) => {
      if (!boardId) return;
      emit("candidate:remove", { boardId, candidateId });
    },
    [boardId, emit],
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
      if (!boardId) return;
      emit("selection:set", {
        boardId,
        ...input,
        updatedBy: displayName,
      });
    },
    [boardId, displayName, emit],
  );

  const clearSelection = useCallback(
    (eventId: string) => {
      if (!boardId) return;
      emit("selection:clear", { boardId, eventId });
    },
    [boardId, emit],
  );

  const focusedEvent =
    board?.events.find((e) => e.id === focusedEventId) ?? null;

  return {
    board,
    boardId,
    displayName,
    focusedEventId,
    focusedEvent,
    status,
    error,
    setFocusedEventId,
    saveDisplayName,
    createAndJoin,
    joinBoard,
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
