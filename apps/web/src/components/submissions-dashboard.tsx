"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { io } from "socket.io-client";
import { Icon } from "@/components/icon";
import { VideoPlayer, type VideoPlayerHandle } from "@/components/video-player";
import {
  listSubmissions,
  updateSubmission,
  deleteSubmission,
  getExportUrl,
  getExportAllUrl,
  downloadExport,
  listQueries,
  createQuery,
  deleteQuery,
  type Submission,
  type QueryType,
  type SubmissionStatus,
  type Query,
} from "@/lib/submissions";
import { cloudApiHttpBase } from "@/lib/cloud-api";
import { getNearestKeyframes, type KeyframeInfo } from "@/lib/api";

const STATUS_ORDER: Record<SubmissionStatus, number> = {
  confirmed: 0,
  review: 1,
  pending: 2,
};

const STATUS_COLORS: Record<SubmissionStatus, string> = {
  confirmed: "bg-green-500",
  review: "bg-yellow-500",
  pending: "bg-gray-400",
};

const STATUS_LABELS: Record<SubmissionStatus, string> = {
  confirmed: "Sure",
  review: "Maybe",
  pending: "Check",
};

export function SubmissionsDashboard({ onBack }: { onBack: () => void }) {
  const [queries, setQueries] = useState<Query[]>([]);
  const [selectedQueryId, setSelectedQueryId] = useState<string | null>(null);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [showQueryForm, setShowQueryForm] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkQueryType, setBulkQueryType] = useState<QueryType>("kis");
  const [exporting, setExporting] = useState<string | null>(null);
  const [keyframes, setKeyframes] = useState<Record<string, KeyframeInfo | null>>({});
  const [videoDialog, setVideoDialog] = useState<{
    submission: Submission;
    keyframe: KeyframeInfo;
  } | null>(null);
  const videoPlayerRef = useRef<VideoPlayerHandle>(null);

  const [queryFormData, setQueryFormData] = useState({
    name: "",
    content: "",
    queryType: "kis" as QueryType,
  });

  const fetchQueries = useCallback(async () => {
    try {
      const data = await listQueries();
      setQueries(data);
    } catch (err) {
      console.error("Failed to fetch queries:", err);
    }
  }, []);

  const fetchSubmissions = useCallback(async () => {
    try {
      const data = await listSubmissions();
      setSubmissions(data);
    } catch (err) {
      console.error("Failed to fetch submissions:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueries();
    fetchSubmissions();

    const s = io(cloudApiHttpBase(), {
      transports: ["websocket", "polling"],
    });
    s.on("connect", () => console.log("Connected to cloud-api"));
    s.on("submissions:changed", (data: Submission[]) => {
      setSubmissions(data);
    });

    return () => {
      s.disconnect();
    };
  }, [fetchSubmissions]);

  useEffect(() => {
    const fetchKeyframes = async () => {
      const seen = new Set<string>();
      const items = submissions.flatMap((sub) =>
        sub.frameIds.map((frameIndex) => {
          const key = `${sub.videoId}-${frameIndex}`;
          if (seen.has(key)) return null;
          seen.add(key);
          return { video_id: sub.videoId, frame_index: frameIndex, key };
        })
      ).filter((item): item is { video_id: string; frame_index: number; key: string } => item !== null);
      const result = await getNearestKeyframes(items);
      setKeyframes((prev) => ({ ...prev, ...result }));
    };
    if (submissions.length > 0) {
      fetchKeyframes();
    }
  }, [submissions]);

  const handleQuerySubmit = async () => {
    if (!queryFormData.name) return;

    try {
      await createQuery({
        name: queryFormData.name,
        content: queryFormData.content,
        queryType: queryFormData.queryType,
      });
      resetQueryForm();
      await fetchQueries();
    } catch (err) {
      console.error("Failed to create query:", err);
    }
  };

  const handleBulkLoad = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setBulkLoading(true);
    const failed: string[] = [];
    try {
      for (const file of Array.from(files)) {
        if (!file.name.endsWith(".txt")) continue;

        const content = await file.text();
        const name = file.name.replace(".txt", "");

        let queryType: QueryType = bulkQueryType;
        if (name.includes("-qa")) queryType = "qa";
        else if (name.includes("-trake")) queryType = "trake";
        else if (name.includes("-kis")) queryType = "kis";

        try {
          await createQuery({
            name,
            content: content.trim(),
            queryType,
          });
        } catch (err) {
          console.error(`Failed to create query "${name}":`, err);
          failed.push(name);
        }
      }
      await fetchQueries();
      if (failed.length) {
        alert(`Failed: ${failed.join(", ")}`);
      }
    } finally {
      setBulkLoading(false);
    }
  };

  const handleQueryDelete = async (id: string) => {
    const query = queries.find((q) => q.id === id);
    const submissionCount = submissions.filter(
      (s) => s.queryName === query?.name,
    ).length;
    const message = submissionCount
      ? `Delete query "${query?.name}"? ${submissionCount} submission(s) with this query name will remain and should be reviewed before export.`
      : `Delete query "${query?.name}"?`;
    if (!confirm(message)) return;
    try {
      await deleteQuery(id);
      if (selectedQueryId === id) setSelectedQueryId(null);
      await fetchQueries();
    } catch (err) {
      console.error("Failed to delete query:", err);
      alert("Failed to delete query — see console.");
    }
  };

  const handleStatusChange = async (id: string, status: SubmissionStatus) => {
    try {
      await updateSubmission(id, { status });
      await fetchSubmissions();
    } catch (err) {
      console.error("Failed to update status:", err);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this submission?")) return;
    try {
      await deleteSubmission(id);
      await fetchSubmissions();
    } catch (err) {
      console.error("Failed to delete submission:", err);
    }
  };

  const handleExport = async (label: string, url: string, filename: string) => {
    setExporting(label);
    try {
      await downloadExport(url, filename);
    } catch (err) {
      console.error("Export failed:", err);
      alert("Export failed — see console.");
    } finally {
      setExporting(null);
    }
  };

  const resetQueryForm = () => {
    setShowQueryForm(false);
    setQueryFormData({
      name: "",
      content: "",
      queryType: "kis",
    });
  };

  const selectedQuery = queries.find((q) => q.id === selectedQueryId);

  const filtered = selectedQueryId
    ? submissions.filter((s) => s.queryName === selectedQuery?.name)
    : submissions;

  const sorted = [...filtered].sort((a, b) => {
    const statusDiff = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
    if (statusDiff !== 0) return statusDiff;
    return a.queryName.localeCompare(b.queryName);
  });

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-background">
      <header className="bg-surface-container-lowest border-b border-outline-variant flex justify-between items-center px-container-padding w-full h-topbar-height shrink-0 z-20">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="text-on-surface-variant hover:text-on-surface"
          >
            <Icon name="arrow_back" size={24} />
          </button>
          <h1 className="text-headline-sm font-bold">Submissions</h1>
        </div>
        <div className="flex gap-2">
          <select
            className="rounded border border-outline-variant bg-surface-container-lowest px-3 py-2 text-label-md"
            value={bulkQueryType}
            onChange={(e) => setBulkQueryType(e.target.value as QueryType)}
            disabled={bulkLoading}
            title="Default type for bulk-loaded files without a -kis/-qa/-trake suffix"
          >
            <option value="kis">KIS</option>
            <option value="qa">Q&A</option>
            <option value="trake">TRAKE</option>
          </select>
          <label className="flex items-center gap-2 px-4 py-2 rounded border border-outline-variant text-label-md cursor-pointer hover:bg-surface-container-low transition-colors">
            <Icon name="upload_file" size={18} />
            {bulkLoading ? "Loading..." : "Bulk Load"}
            <input
              type="file"
              multiple
              accept=".txt"
              className="hidden"
              onChange={(e) => handleBulkLoad(e.target.files)}
              disabled={bulkLoading}
            />
          </label>
          <button
            onClick={() => setShowQueryForm(true)}
            className="flex items-center gap-2 px-4 py-2 rounded border border-outline-variant text-label-md"
          >
            <Icon name="post_add" size={18} />
            Add Query
          </button>
          <button
            onClick={() => handleExport("all", getExportAllUrl(), "submission.zip")}
            disabled={exporting !== null}
            className="flex items-center gap-2 px-4 py-2 rounded border border-outline-variant text-label-md disabled:opacity-50"
          >
            <Icon name="download" size={18} />
            {exporting === "all" ? "Exporting..." : "Export All (zip)"}
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <div className="mb-4">
            <select
              className="w-full rounded border border-outline-variant bg-surface-container-lowest px-4 py-3 text-body-md"
              value={selectedQueryId ?? ""}
              onChange={(e) => setSelectedQueryId(e.target.value || null)}
            >
              <option value="">All Queries</option>
              {queries.map((q) => (
                <option key={q.id} value={q.id}>
                  {q.name} ({q.queryType.toUpperCase()})
                </option>
              ))}
            </select>
          </div>

          {selectedQuery && (
            <div className="mb-6 p-4 rounded-lg bg-surface-container-lowest border border-outline-variant">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-label-sm font-bold text-on-surface-variant bg-surface-container px-2 py-0.5 rounded">
                  {selectedQuery.queryType.toUpperCase()}
                </span>
                <span className="text-body-md font-bold">{selectedQuery.name}</span>
                <button
                  onClick={() =>
                    handleExport(
                      selectedQuery.name,
                      getExportUrl(selectedQuery.name),
                      `${selectedQuery.name}.csv`,
                    )
                  }
                  disabled={exporting !== null}
                  className="ml-auto flex items-center gap-1 px-3 py-1.5 rounded border border-outline-variant text-label-md hover:bg-surface-container transition-colors disabled:opacity-50"
                >
                  <Icon name="download" size={16} />
                  {exporting === selectedQuery.name ? "Exporting..." : "Export CSV"}
                </button>
                <button
                  onClick={() => handleQueryDelete(selectedQuery.id)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded border border-outline-variant text-label-md hover:bg-surface-container hover:text-red-500 transition-colors"
                  title="Delete query"
                >
                  <Icon name="delete" size={16} />
                  Delete
                </button>
              </div>
              {selectedQuery.content && (
                <div className="text-body-md text-on-surface whitespace-pre-wrap leading-relaxed">
                  {selectedQuery.content}
                </div>
              )}
            </div>
          )}

          {showQueryForm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
              <div className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-lg p-6 space-y-4 border border-outline-variant">
                <h2 className="text-headline-sm font-bold">Add Query</h2>

                <div className="space-y-3">
                  <div>
                    <label className="text-label-sm text-on-surface-variant">Query Name</label>
                    <input
                      className="w-full rounded border border-outline-variant bg-surface px-3 py-2 text-body-md"
                      value={queryFormData.name}
                      onChange={(e) => setQueryFormData({ ...queryFormData, name: e.target.value })}
                      placeholder="query-1-kis"
                    />
                  </div>

                  <div>
                    <label className="text-label-sm text-on-surface-variant">Query Type</label>
                    <select
                      className="w-full rounded border border-outline-variant bg-surface px-3 py-2 text-body-md"
                      value={queryFormData.queryType}
                      onChange={(e) => setQueryFormData({ ...queryFormData, queryType: e.target.value as QueryType })}
                    >
                      <option value="kis">KIS</option>
                      <option value="qa">Q&A</option>
                      <option value="trake">TRAKE</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-label-sm text-on-surface-variant">Query Content</label>
                    <textarea
                      className="w-full rounded border border-outline-variant bg-surface px-3 py-2 text-body-md"
                      value={queryFormData.content}
                      onChange={(e) => setQueryFormData({ ...queryFormData, content: e.target.value })}
                      placeholder="Describe the query..."
                      rows={4}
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={resetQueryForm}
                    className="px-4 py-2 rounded border border-outline-variant text-label-md"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleQuerySubmit}
                    className="px-6 py-2 rounded bg-primary-container text-on-primary-container text-label-md font-bold"
                  >
                    Add
                  </button>
                </div>
              </div>
            </div>
          )}

          {loading ? (
            <div className="text-center py-12 text-on-surface-variant">Loading...</div>
          ) : sorted.length === 0 ? (
            <div className="text-center py-12 text-on-surface-variant">
              {selectedQueryId ? "No submissions for this query." : "No submissions yet. Click \"Bulk Load\" or \"Add Query\" to start."}
            </div>
          ) : (
            <div className="space-y-1">
              {sorted.map((sub) => {
                const firstKeyframe = keyframes[`${sub.videoId}-${sub.frameIds[0]}`];
                return (
                  <div
                    key={sub.id}
                    className="rounded-lg bg-surface-container-lowest border border-outline-variant hover:bg-surface-container-low transition-colors"
                  >
                    <div className="flex items-center gap-3 px-4 py-3">
                      <button
                        onClick={() => {
                          const nextStatus: SubmissionStatus =
                            sub.status === "confirmed" ? "pending" : "confirmed";
                          handleStatusChange(sub.id, nextStatus);
                        }}
                        className={`w-4 h-4 rounded-full ${STATUS_COLORS[sub.status]} hover:opacity-80 shrink-0`}
                        title={STATUS_LABELS[sub.status]}
                      />

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-label-sm font-bold text-on-surface-variant bg-surface-container px-2 py-0.5 rounded">
                            {sub.queryName || "unnamed"}
                          </span>
                          <span className="text-body-md font-mono">{sub.videoId}</span>
                          <span className="text-body-sm text-on-surface-variant">
                            {sub.frameIds.join(", ")}
                            {firstKeyframe && !firstKeyframe.is_exact && (
                              <span className="text-yellow-600 ml-1">
                                (nearest: {firstKeyframe.frame_index})
                              </span>
                            )}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-label-sm text-on-surface-variant mt-0.5">
                          <span className="uppercase">{sub.queryType}</span>
                          {sub.submittedBy && <span>· by {sub.submittedBy}</span>}
                        </div>
                        {sub.answer && (
                          <div className="text-body-sm text-on-surface-variant mt-0.5">
                            <span className="font-bold">Answer:</span> {sub.answer}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => handleStatusChange(sub.id, "pending")}
                          className={`p-1.5 rounded ${sub.status === "pending" ? "bg-gray-400/20 text-gray-600" : "hover:bg-surface-container text-on-surface-variant"}`}
                          title="Check"
                        >
                          <Icon name="help" size={16} />
                        </button>
                        <button
                          onClick={() => handleStatusChange(sub.id, "review")}
                          className={`p-1.5 rounded ${sub.status === "review" ? "bg-yellow-500/20 text-yellow-600" : "hover:bg-surface-container text-on-surface-variant"}`}
                          title="Maybe"
                        >
                          <Icon name="question_mark" size={16} />
                        </button>
                        <button
                          onClick={() => handleStatusChange(sub.id, "confirmed")}
                          className={`p-1.5 rounded ${sub.status === "confirmed" ? "bg-green-500/20 text-green-600" : "hover:bg-surface-container text-on-surface-variant"}`}
                          title="Sure"
                        >
                          <Icon name="check" size={16} />
                        </button>
                        <button
                          onClick={() => handleDelete(sub.id)}
                          className="p-1.5 rounded hover:bg-surface-container text-on-surface-variant hover:text-red-500"
                          title="Delete"
                        >
                          <Icon name="delete" size={16} />
                        </button>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 px-4 pb-3">
                      {sub.frameIds.map((frameIndex) => {
                        const keyframe = keyframes[`${sub.videoId}-${frameIndex}`];
                        const isNearest = keyframe && !keyframe.is_exact;
                        if (!keyframe?.thumbnail_url) return null;
                        return (
                          <button
                            key={frameIndex}
                            onClick={() => setVideoDialog({ submission: sub, keyframe })}
                            className="relative shrink-0 group"
                            title="View in video player"
                          >
                            <img
                              src={keyframe.thumbnail_url}
                              alt={`Frame ${keyframe.frame_index}`}
                              className="w-20 h-12 object-cover rounded border border-outline-variant group-hover:opacity-80 group-hover:ring-2 group-hover:ring-primary transition"
                              loading="lazy"
                            />
                            {isNearest && (
                              <span className="absolute -top-1 -right-1 bg-yellow-500 text-white text-label-xs px-1 rounded">
                                ~{keyframe.frame_index}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>

      {videoDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm">
          <div className="relative w-full max-w-6xl h-[80vh] bg-black rounded-lg overflow-hidden">
            <button
              onClick={() => setVideoDialog(null)}
              className="absolute top-4 right-4 z-10 text-white hover:bg-white/10 rounded-full p-2 transition-colors"
            >
              <Icon name="close" size={24} />
            </button>

            <div className="absolute top-4 left-4 z-10 bg-black/70 rounded px-3 py-2 text-white">
              <div className="text-label-sm font-bold">{videoDialog.submission.queryName}</div>
              <div className="text-body-xs text-gray-300">
                {videoDialog.submission.videoId} · Frame {videoDialog.keyframe.frame_index}
                {!videoDialog.keyframe.is_exact && (
                  <span className="text-yellow-400 ml-2">(nearest: {videoDialog.keyframe.frame_index})</span>
                )}
              </div>
              {videoDialog.submission.answer && (
                <div className="text-body-xs text-gray-300 mt-1">Answer: {videoDialog.submission.answer}</div>
              )}
            </div>

            <VideoPlayer
              ref={videoPlayerRef}
              src={videoDialog.keyframe.video_url}
              poster={videoDialog.keyframe.thumbnail_url}
              initialTime={videoDialog.keyframe.timestamp}
            />
          </div>
        </div>
      )}
    </div>
  );
}
