"use client";

import { useCallback, useEffect, useState } from "react";

/** DRES login/evaluation state, mirrored into sessionStorage. */
export function useDresSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [evaluationId, setEvaluationId] = useState<string | null>(null);

  useEffect(() => {
    setSessionId(sessionStorage.getItem("dresSessionId"));
    setUsername(sessionStorage.getItem("dresUsername"));
    setEvaluationId(sessionStorage.getItem("dresEvaluationId"));
  }, []);

  const login = useCallback((newSessionId: string, newUsername: string) => {
    sessionStorage.setItem("dresSessionId", newSessionId);
    sessionStorage.setItem("dresUsername", newUsername);
    setSessionId(newSessionId);
    setUsername(newUsername);
  }, []);

  const selectEvaluation = useCallback((newEvaluationId: string) => {
    sessionStorage.setItem("dresEvaluationId", newEvaluationId);
    setEvaluationId(newEvaluationId);
  }, []);

  const logout = useCallback(() => {
    const endedSessionId = sessionId;
    sessionStorage.removeItem("dresSessionId");
    sessionStorage.removeItem("dresUsername");
    sessionStorage.removeItem("dresEvaluationId");
    setSessionId(null);
    setUsername(null);
    setEvaluationId(null);
    if (endedSessionId) {
      fetch("/api/dres/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: endedSessionId }),
      }).catch(() => {});
    }
  }, [sessionId]);

  return { sessionId, username, evaluationId, login, selectEvaluation, logout };
}
