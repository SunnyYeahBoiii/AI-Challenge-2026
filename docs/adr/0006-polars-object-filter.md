# 0004: Polars Object Post-Filter

RF-DETR COCO detections are merged into `data/objects/object_detections.parquet` and queried with Polars only after Milvus has ranked Frame candidates. The public `tags` / `tag_mode` request fields remain unchanged, but their values are COCO class names from `data/objects/classname.json`.

**Context:** The existing `data_frames.tags` Milvus ARRAY field combines legacy object-detection and RAM tags. Its schema and collection are already deployed, while RF-DETR detections have a separate, explicit schema: `frame_id`, `class_id`, `class_name`, and `count`. Rebuilding the collection solely to replace a filter field is unnecessary.

**Decision:** Vector searches always call Milvus without a tag expression. `object_filter` builds `video_id/frame_index` keys for the ranked candidates, semi-joins them with the Parquet LazyFrame, and applies `and` / `or` COCO class filtering. It returns the original Milvus Frame objects in their original ranking order.

**Consequences:**

- Frontend request and backend response shapes do not change; Polars is an internal filter only.
- Different BoxQuery tags no longer split Milvus batch RPCs.
- A filter can leave fewer than `topk` results because it operates after ANN retrieval.
- Tag-only requests are invalid: tags refine text or image vector results and cannot create candidates themselves.
- The merged Parquet must be generated before deployment and made available to the API container.
