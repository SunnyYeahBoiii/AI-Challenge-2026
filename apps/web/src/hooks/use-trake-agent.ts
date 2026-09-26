"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getTrakeAgentJob, runTrakeAgent, type AgentJob } from "@/lib/api";

const POLL_MS = 2000;

export interface TrakeAgentApi {
  job: AgentJob | null;
  running: boolean;
  error: string | null;
  run: (instruction: string) => Promise<void>;
}

/** Start the agent and poll its job; new Candidates arrive via the board socket. */
export function useTrakeAgent(): TrakeAgentApi {
  const [job, setJob] = useState<AgentJob | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const run = useCallback(async (instruction: string) => {
    setRunning(true);
    setError(null);
    setJob(null);
    try {
      const jobId = await runTrakeAgent(instruction);
      const poll = async () => {
        try {
          const next = await getTrakeAgentJob(jobId);
          setJob(next);
          if (next.status === "running") {
            timer.current = setTimeout(poll, POLL_MS);
            return;
          }
          if (next.status === "error") setError(next.error);
        } catch (e) {
          setError(e instanceof Error ? e.message : "poll failed");
        }
        setRunning(false);
      };
      await poll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "agent failed to start");
      setRunning(false);
    }
  }, []);

  return { job, running, error, run };
}
