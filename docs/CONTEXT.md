# AI-Challenge-2026

AI-powered video and image search application for the AI Challenge 2026 competition. Users input text or image queries, the system finds relevant video moments using vector similarity search, and results can be submitted to the competition platform (DRES).

## Language

**Frame**:
A single extracted keyframe from a video. The atomic unit of search results.
_Avoid_: keyframe, image, shot

**Video**:
A source video containing multiple frames. Identified by `video_path` (e.g., `keyframes/K02/K02_V001`).
_Avoid_: clip, media

**Query**:
A user-provided text string or image used to search for relevant frames.
_Avoid_: search, request
_Note_: the cloud-api service also has a "Query" resource — that is a competition **task/topic** (KIS/QA/TRAKE), not a search query.

**BoxQuery**:
A multi-modal search query with an id, type (text or image), content, and weight. Multiple BoxQueries can be combined for complex searches.
_Avoid_: multi-query, search box

**Tag Filter**:
An optional list of COCO object class names that refines Frames returned by vector search. Names match `data/objects/classname.json` exactly, including spaces (for example `traffic light`, not `traffic_light`). The filter is evaluated by Polars against RF-DETR detections after Milvus ranks candidates; it does not alter the Milvus query.
_Avoid_: using tags as a standalone query

**Query Mode**:
The retrieval strategy for multiple BoxQueries. `parallel` retrieves all boxes independently (bucketed into concurrent Milvus batches); `sequential` retrieves each later box only within videos reachable from the previous box. Both modes then keep frames on complete ordered paths and rank videos by their best path.
_Avoid_: search mode, execution mode

**Cosine Similarity**:
The relevance score between a query embedding and a frame embedding. Higher = more relevant. Used for ranking individual frames.
_Avoid_: score, distance, similarity score

**Video Score**:
An aggregated relevance score for all frames from the same video. Used when results are grouped by video.
_Avoid_: group score, aggregate

**DRES**:
Data Retrieval and Evaluation System — the competition platform for submitting search results. Supports KIS (Keyword In Scene), QA (Question Answering), and TRAKE (Tracking) task types. TRAKE answers are submitted as the text `TR-<VIDEO_ID>-<FRAME_ID1>,<FRAME_ID2>,...` where each FRAME_ID is derived from Selection `pts_time` and fps.
_Avoid_: submission system, evaluation

**Embedding**:
A vector representation of text or image content. Per ADR 0004, encoding uses a registry of three interchangeable encoders — BEiT-3 and MetaCLIP (1024-dim) and BGE-VL-large (768-dim) — with only one resident at a time, each paired with its own Milvus collection. Query-time encoding and the indexed vectors must come from the same encoder; mixing checkpoints silently degrades search (the 224px CLIP build only reaches cosine 0.92 against 384px vectors).
_Avoid_: vector, feature vector

**Milvus**:
Vector similarity search database. Stores frame embeddings and supports approximate nearest neighbor search.
_Avoid_: vector database, ANN

**Elasticsearch**:
Full-text search database. Stores OCR text, ASR text, and frame metadata. Used for keyword filtering and metadata enrichment.
_Avoid_: ES, search engine

**pts_time**:
The timestamp of a Frame within its Video, in **seconds** (float). Not milliseconds. Used for video seeking and DRES submission.
_Avoid_: treating as ms, dividing by 1000

**TrakeBoard**:
The team's single persistent collaborative board for TRAKE. Everyone connected to cloud-api joins it automatically; no board code is needed. Holds an ordered set of Events, each Event’s Candidate list, and the Selections that will be submitted to DRES.
_Avoid_: room, session, workspace, TRAKE board (spacing)

**Event**:
One required moment in a TRAKE task, described by query text. Has a stable identity for the life of the TrakeBoard; display labels such as E1, E2 are derived from the current order only. Owns its Candidate list and at most one Selection. Events may be added, removed, and reordered (including drag-and-drop) during collaboration.
_Avoid_: keyframe slot, step, milestone, task (when meaning an Event); treating E1/E2 as stable identifiers

**Candidate**:
A proposed moment for an Event (Video + pts_time). May come from any Video while searching; not yet the moment submitted for that Event.
_Avoid_: suggestion, pick, nomination

**Selection**:
The chosen moment for an Event on a TrakeBoard: an authoritative `pts_time` on the Target Video, plus a Frame id used only as the nearest-Frame preview. The preview Frame may change when `pts_time` moves; opening a Selection always seeks to the stored `pts_time`. All Selections on one TrakeBoard must share the same Target Video.
_Avoid_: locked frame, final pick, chosen keyframe

**Target Video**:
The Video that every Selection on a TrakeBoard must share. Chosen when the first Selection is made (or changed only by clearing Selections).
_Avoid_: board video, locked video

**Pin**:
A Frame shared on the team's realtime pin wall (Video + frame_index + timestamp + fps + thumbnail_url only — no note, no status, no pinner identity). Unauthenticated and shared by everyone connected to cloud-api, like TrakeBoard; anyone may unpin or clear the wall.
_Avoid_: bookmark, favorite, star, submission (a Pin is never sent to DRES)
