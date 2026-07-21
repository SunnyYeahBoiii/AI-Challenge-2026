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

**BoxQuery**:
A multi-modal search query with an id, type (text or image), content, and weight. Multiple BoxQueries can be combined for complex searches.
_Avoid_: multi-query, search box

**Cosine Similarity**:
The relevance score between a query embedding and a frame embedding. Higher = more relevant. Used for ranking individual frames.
_Avoid_: score, distance, similarity score

**Video Score**:
An aggregated relevance score for all frames from the same video. Used when results are grouped by video.
_Avoid_: group score, aggregate

**DRES**:
Distributed Retrieval Evaluation Server — the competition platform for submitting search results. Supports KIS, QA, and tracking task types.
_Avoid_: submission system, evaluation

**Embedding**:
A model-specific vector representation of text or image content. Dimension, preprocessing,
checkpoint and collection are fixed by a ModelSpec. Embeddings from different models are
never compared directly.
_Avoid_: vector, feature vector

**frame_uid**:
A stable identity shared by the same Frame across every model collection. Derived from
`video_id` and extracted `frame_index`; never use a Milvus auto-id for rank fusion.
_Avoid_: database id, original frame index

**ModelSpec**:
Versioned configuration for one image-text encoder: adapter, checkpoint, dimension,
collection, enabled state and RRF weight.
_Avoid_: model name without preprocessing/version metadata

**RRF**:
Reciprocal Rank Fusion. Combines independent model rankings using
`weight / (rrf_k + rank)` without assuming their raw similarity scores are calibrated.
_Avoid_: averaging raw scores from unrelated models

**Milvus**:
Vector similarity search database. Stores frame embeddings and supports approximate nearest neighbor search.
_Avoid_: vector database, ANN

**Elasticsearch**:
Full-text search database. Stores OCR text, ASR text, and frame metadata. Used for keyword filtering and metadata enrichment.
_Avoid_: ES, search engine

**pts_time**:
The timestamp of a Frame within its Video, in **seconds** (float). The DRES v2 adapter converts
it to integer milliseconds only at the external submission boundary.
_Avoid_: treating the stored value as milliseconds
