"use client";

import { useState } from "react";
import { Icon } from "@/components/icon";
import { createSubmission, type Query } from "@/lib/submissions";
import { searchText, type FrameResult } from "@/lib/api";

interface AutoSubmitDialogProps {
  selectedQuery: Query | null;
  open: boolean;
  onClose: () => void;
  onSubmitted: () => void;
}

const TEMPORAL_WINDOW_SECONDS = 90;

function parseTrakeEvents(content: string): string[] {
  const lines = content
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  // ponytail: line-split by default; drop preamble lines only when other
  // lines carry event markers (Cảnh N / E N / Event N / Scene N / N. / N)).
  const withMarker = lines.filter((l) =>
    /(cảnh|event|scene)\s*\d+|\be\s*\d+|^\d+\s*[.)}:：]/i.test(l)
  );
  return withMarker.length > 0 ? withMarker : lines;
}

function buildTrakeChains(
  eventResults: FrameResult[][],
  topN: number
): { videoId: string; frameIds: number[]; score: number }[] {
  if (eventResults.length === 0) return [];

  const K = eventResults.length;

  const byVideo: Map<string, FrameResult[]>[] = eventResults.map((frames) => {
    const map = new Map<string, FrameResult[]>();
    for (const f of frames) {
      const arr = map.get(f.video_id) ?? [];
      arr.push(f);
      map.set(f.video_id, arr);
    }
    for (const arr of map.values()) {
      arr.sort((a, b) => a.timestamp - b.timestamp);
    }
    return map;
  });

  const allVideoIds = new Set<string>();
  for (const m of byVideo) for (const v of m.keys()) allVideoIds.add(v);

  const chains: { videoId: string; frameIds: number[]; score: number }[] = [];

  for (const videoId of allVideoIds) {
    const eventFrames = byVideo.map((m) => m.get(videoId) ?? []);
    if (eventFrames.some((f) => f.length === 0)) continue;

    const candidates = eventFrames[0];
    for (let ci = 0; ci < Math.min(candidates.length, 30); ci++) {
      const chain: FrameResult[] = [candidates[ci]];
      let lastTs = candidates[ci].timestamp;

      let valid = true;
      for (let e = 1; e < K; e++) {
        const next = eventFrames[e].find(
          (f) =>
            f.timestamp > lastTs &&
            f.timestamp - lastTs <= TEMPORAL_WINDOW_SECONDS &&
            !chain.some((c) => c.frame_index === f.frame_index)
        );
        if (!next) {
          valid = false;
          break;
        }
        chain.push(next);
        lastTs = next.timestamp;
      }

      if (valid && chain.length === K) {
        chains.push({
          videoId,
          frameIds: chain.map((f) => f.frame_index),
          score: chain.reduce((s, f) => s + f.score, 0) / K,
        });
      }
    }
  }

  chains.sort((a, b) => b.score - a.score);

  const seen = new Set<string>();
  const unique: typeof chains = [];
  for (const c of chains) {
    const key = `${c.videoId}:${c.frameIds.join(",")}`;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(c);
    }
  }

  return unique.slice(0, topN);
}

export function AutoSubmitDialog({
  selectedQuery,
  open,
  onClose,
  onSubmitted,
}: AutoSubmitDialogProps) {
  const [topN, setTopN] = useState(10);
  const [answer, setAnswer] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  if (!open || !selectedQuery) return null;

  const addLog = (msg: string) => setLogs((prev) => [...prev, msg]);

  const searchSingle = async (text: string, topk: number): Promise<FrameResult[]> => {
    const data = await searchText(text, topk);
    return data.results ?? [];
  };

  const handleAutoSubmit = async () => {
    if (!selectedQuery) return;

    setIsProcessing(true);
    setLogs([]);
    addLog(`Starting auto-submit for ${selectedQuery.name} (${selectedQuery.queryType})...`);

    try {
      const queryType = selectedQuery.queryType;

      if (queryType === "kis" || queryType === "qa") {
        addLog(`Searching top ${topN} frames...`);
        const results = await searchSingle(selectedQuery.content, topN);
        addLog(`Found ${results.length} frames`);

        const toSubmit = results.slice(0, topN);
        for (let i = 0; i < toSubmit.length; i++) {
          const frame = toSubmit[i];
          await createSubmission({
            queryName: selectedQuery.name,
            queryType,
            videoId: frame.video_id,
            frameIds: [frame.frame_index],
            ...(queryType === "qa" && { answer }),
          });
          addLog(`[${i + 1}/${toSubmit.length}] ${frame.video_id}#${frame.frame_index} (score: ${frame.score.toFixed(3)})`);
        }
      } else if (queryType === "trake") {
        const events = parseTrakeEvents(selectedQuery.content);
        addLog(`Parsed ${events.length} events:`);
        events.forEach((e, i) => addLog(`  Event ${i + 1}: ${e}`));

        const eventResults: FrameResult[][] = [];
        for (let i = 0; i < events.length; i++) {
          addLog(`Searching event ${i + 1}/${events.length}...`);
          const results = await searchSingle(events[i], 1000);
          addLog(`  → ${results.length} results`);
          eventResults.push(results);
        }

        addLog(`Building temporal chains...`);
        const chains = buildTrakeChains(eventResults, topN);
        addLog(`Found ${chains.length} valid chains`);

        for (let i = 0; i < chains.length; i++) {
          const chain = chains[i];
          await createSubmission({
            queryName: selectedQuery.name,
            queryType: "trake",
            videoId: chain.videoId,
            frameIds: chain.frameIds,
          });
          addLog(`[${i + 1}/${chains.length}] ${chain.videoId} frames=[${chain.frameIds.join(",")}] avg_score=${chain.score.toFixed(3)}`);
        }
      }

      addLog(`Done!`);
      onSubmitted();
    } catch (error) {
      addLog(`Error: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-outline-variant">
          <h2 className="text-lg font-semibold text-on-surface">
            Auto-Submit: {selectedQuery.name}
          </h2>
          <button
            onClick={onClose}
            className="text-on-surface-variant hover:text-on-surface p-1"
          >
            <Icon name="close" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div className="text-sm text-on-surface-variant">
            <p className="font-medium text-on-surface mb-1">Query Content:</p>
            <p className="bg-surface-container p-3 rounded-lg text-sm whitespace-pre-wrap max-h-32 overflow-y-auto">
              {selectedQuery.content}
            </p>
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-on-surface mb-1">
                Top N Submissions
              </label>
              <input
                type="number"
                min={1}
                max={500}
                value={topN}
                onChange={(e) => setTopN(parseInt(e.target.value) || 10)}
                className="w-full px-3 py-2 bg-surface-container border border-outline-variant rounded-lg text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={isProcessing}
              />
            </div>

            {selectedQuery.queryType === "qa" && (
              <div className="flex-1">
                <label className="block text-sm font-medium text-on-surface mb-1">
                  Answer
                </label>
                <input
                  type="text"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  className="w-full px-3 py-2 bg-surface-container border border-outline-variant rounded-lg text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="Enter answer for QA"
                  disabled={isProcessing}
                />
              </div>
            )}
          </div>

          {selectedQuery.queryType === "trake" && (
            <p className="text-xs text-on-surface-variant">
              Searches each event separately, then chains results by temporal order within the same video.
            </p>
          )}
        </div>

        <div className="px-6 py-4 border-t border-outline-variant bg-surface-container">
          <div className="flex justify-between items-center">
            <span className="text-sm text-on-surface-variant">
              Type: <span className="font-semibold uppercase">{selectedQuery.queryType}</span>
            </span>
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-on-surface-variant hover:bg-surface-container-high rounded-lg transition-colors"
                disabled={isProcessing}
              >
                Cancel
              </button>
              <button
                onClick={handleAutoSubmit}
                disabled={isProcessing || (selectedQuery.queryType === "qa" && !answer)}
                className="px-4 py-2 bg-primary text-on-primary rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {isProcessing ? "Processing..." : `Submit Top ${topN}`}
              </button>
            </div>
          </div>
        </div>

        {logs.length > 0 && (
          <div className="px-6 py-4 border-t border-outline-variant max-h-48 overflow-y-auto bg-surface-container-low">
            <p className="text-xs font-medium text-on-surface-variant mb-2">Logs:</p>
            {logs.map((log, i) => (
              <p key={i} className="text-xs text-on-surface-variant font-mono whitespace-pre-wrap">
                {log}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
