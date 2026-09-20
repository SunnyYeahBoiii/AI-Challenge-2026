"use client";

import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Icon } from "./icon";
import { TagInput } from "./tag-input";
import { Toggle } from "./toggle";
import { MatchModeToggle } from "./match-mode-toggle";
import { COCO_CLASS_NAMES } from "@/lib/coco-classes";
import {
  VOICE_LANGUAGES,
  collectRecognitionText,
  configureSpeechRecognition,
  getSpeechRecognitionConstructor,
  speechRecognitionErrorMessage,
  type BrowserSpeechRecognition,
  type VoiceLanguage,
} from "@/lib/web-speech";

export interface BoxQuery {
  id: string;
  type: "text" | "image";
  content: string;
  enabled: boolean;
  tags?: string[];
  tagMatchMode?: "and" | "or";
  keywordFieldMode?: "asr" | "ocr" | "or" | "and";
  ocrKeywords?: string[];
  ocrMatchMode?: "and" | "or";
  ocrSearchMode?: "fuzzy" | "exact";
  asrKeywords?: string[];
  asrMatchMode?: "and" | "or";
  asrSearchMode?: "fuzzy" | "exact";
  /** Words the transcript may drift from the typed ASR phrase; exact mode only. */
  asrPhraseSlop?: number;
  topK?: number;
  enhance?: boolean;
}

interface QueryBoxProps {
  query: BoxQuery;
  index: number;
  onUpdate: (updates: Partial<BoxQuery>) => void;
  onRemove: () => void;
  canRemove: boolean;
}

type SortableBindings = ReturnType<typeof useSortable> | null;
const MAX_IMAGE_FILE_BYTES = 10 * 1024 * 1024;
function KeywordSearchModeToggle({
  label,
  mode,
  onChange,
  disabled = false,
}: {
  label: "OCR" | "ASR";
  mode: "fuzzy" | "exact";
  onChange: (mode: "fuzzy" | "exact") => void;
  disabled?: boolean;
}) {
  return (
    <div
      className="flex overflow-hidden rounded border border-outline-variant"
      aria-label={`${label} search mode`}
    >
      {(["fuzzy", "exact"] as const).map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          disabled={disabled}
          title={
            option === "fuzzy"
              ? "Unordered terms with automatic spelling tolerance"
              : "Adjacent words in the entered order"
          }
          className={`px-2 py-0.5 text-label-xs capitalize transition-colors ${
            mode === option
              ? "bg-primary text-on-primary"
              : "text-on-surface-variant hover:bg-surface-container-high"
          } disabled:cursor-not-allowed disabled:opacity-45`}
          aria-pressed={mode === option}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function KeywordFieldModeToggle({
  mode,
  onChange,
}: {
  mode: "asr" | "ocr" | "or" | "and";
  onChange: (mode: "asr" | "ocr" | "or" | "and") => void;
}) {
  return (
    <div className="flex items-center gap-2" aria-label="Keyword field mode">
      <span className="text-label-sm text-on-surface-variant">MODE</span>
      <div className="flex overflow-hidden rounded border border-outline-variant">
        {(["asr", "ocr", "or", "and"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            title={
              option === "asr"
                ? "Match ASR text only"
                : option === "ocr"
                  ? "Match OCR text only"
                  : option === "or"
                    ? "Match OCR or ASR text"
                    : "Match both OCR and ASR text"
            }
            className={`px-2 py-1 text-label-xs uppercase transition-colors ${
              mode === option
                ? "bg-primary text-on-primary"
                : "text-on-surface-variant hover:bg-surface-container-high"
            }`}
            aria-pressed={mode === option}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Static box for SSR / pre-hydrate — same markup, no dnd-kit IDs. */
export function QueryBoxStatic(props: QueryBoxProps) {
  return <QueryBoxInner {...props} sortable={null} />;
}

/** Sortable box — must render inside DndContext + SortableContext. */
export function QueryBox(props: QueryBoxProps) {
  const sortable = useSortable({ id: props.query.id });
  return <QueryBoxInner {...props} sortable={sortable} />;
}

function QueryBoxInner({
  query,
  index,
  onUpdate,
  onRemove,
  canRemove,
  sortable,
}: QueryBoxProps & { sortable: SortableBindings }) {
  const style = sortable
    ? {
        transform: CSS.Transform.toString(sortable.transform),
        transition: sortable.transition,
        opacity: sortable.isDragging ? 0.5 : 1,
      }
    : undefined;
  const [showTags, setShowTags] = useState(false);
  const [showKeywords, setShowKeywords] = useState(false);
  const [isFileDragging, setIsFileDragging] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguage>(VOICE_LANGUAGES.vietnamese);
  const [voiceState, setVoiceState] = useState<"idle" | "listening" | "finishing">("idle");
  const [voicePreview, setVoicePreview] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileDragDepthRef = useRef(0);
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const finalTranscriptRef = useRef("");
  const hasVectorQuery = Boolean(query.content.trim());
  const keywordFieldMode = query.keywordFieldMode ?? "or";
  const keywordCount = (query.ocrKeywords?.length ?? 0) + (query.asrKeywords?.length ?? 0);
  const ocrDisabled = keywordFieldMode === "asr";
  const asrDisabled = keywordFieldMode === "ocr";

  useEffect(() => () => recognitionRef.current?.abort(), []);

  const stopVoiceRecognition = () => {
    if (!recognitionRef.current) return;
    setVoiceState("finishing");
    recognitionRef.current.stop();
  };

  const startVoiceRecognition = () => {
    const Recognition = getSpeechRecognitionConstructor();
    if (!Recognition) {
      setVoiceError("Voice input is available in Google Chrome.");
      return;
    }
    setVoiceError(null);
    setVoicePreview("");
    finalTranscriptRef.current = "";
    const recognition = new Recognition();
    recognitionRef.current = recognition;
    configureSpeechRecognition(recognition, voiceLanguage);
    recognition.onstart = () => setVoiceState("listening");
    recognition.onresult = (event) => {
      const { finalText, interimText } = collectRecognitionText(event);
      if (finalText) {
        finalTranscriptRef.current = [finalTranscriptRef.current, finalText]
          .filter(Boolean)
          .join(" ");
      }
      setVoicePreview([finalTranscriptRef.current, interimText].filter(Boolean).join(" "));
    };
    recognition.onspeechend = () => stopVoiceRecognition();
    recognition.onerror = (event) => {
      setVoiceError(speechRecognitionErrorMessage(event.error));
    };
    recognition.onend = () => {
      if (recognitionRef.current !== recognition) return;
      recognitionRef.current = null;
      setVoiceState("idle");
      const transcript = finalTranscriptRef.current.trim();
      if (transcript) onUpdate({ content: transcript, type: "text" });
      setVoicePreview("");
    };
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setVoiceState("idle");
      setVoiceError("Could not start voice recognition. Try again.");
    }
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        onUpdate({ type: "image", content: ev.target?.result as string });
      };
      reader.readAsDataURL(file);
    }
  };

  const nodeRef = sortable?.setNodeRef;

  return (
    <div
      ref={nodeRef}
      style={style}
      className="bg-surface-container-lowest border border-outline-variant rounded-lg shadow-sm overflow-hidden flex flex-col shrink-0 relative"
    >
      {/* Index badge */}
      <div className="absolute top-1 left-1 z-10 w-5 h-5 rounded bg-primary text-on-primary flex items-center justify-center text-label-xs">
        {index + 1}
      </div>
      {/* Header */}
      <div className="flex justify-between items-center p-2 pl-7 border-b border-surface-variant bg-surface-bright rounded-t-lg">
        {/* Toggle */}
        <Toggle
          checked={query.enabled}
          onChange={(enabled) => onUpdate({ enabled })}
          label={`Query ${index + 1} enabled`}
        />
        {/* Actions */}
        <div className="flex items-center gap-1">
          {query.type === "text" && (
            <>
              <div className="flex overflow-hidden rounded border border-outline-variant" aria-label="Voice language">
                {([
                  [VOICE_LANGUAGES.vietnamese, "VI"],
                  [VOICE_LANGUAGES.english, "EN"],
                ] as const).map(([language, label]) => (
                  <button
                    key={language}
                    type="button"
                    onClick={() => setVoiceLanguage(language)}
                    aria-pressed={voiceLanguage === language}
                    title={`Recognize ${language === VOICE_LANGUAGES.vietnamese ? "Vietnamese" : "English"}`}
                    className={`px-1.5 py-0.5 text-label-xs transition-colors ${
                      voiceLanguage === language
                        ? "bg-primary text-on-primary"
                        : "text-outline hover:bg-surface-container-high"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => voiceState === "idle" ? startVoiceRecognition() : stopVoiceRecognition()}
                aria-label={voiceState === "idle" ? "Start voice input" : "Stop voice input"}
                title={voiceState === "idle" ? "Start voice input" : "Stop voice input"}
                className={`p-1 transition-colors ${
                  voiceState === "listening" ? "text-error animate-pulse" : "text-outline hover:text-on-surface"
                }`}
              >
                <Icon name={voiceState === "idle" ? "mic" : "stop_circle"} size={16} />
              </button>
            </>
          )}
          <button
            aria-label="Drag to reorder"
            className="text-outline hover:text-on-surface transition-colors p-1 cursor-grab active:cursor-grabbing"
            {...(sortable?.attributes ?? {})}
            {...(sortable?.listeners ?? {})}
          >
            <Icon name="drag_indicator" size={16} />
          </button>
          <button
            onClick={() => {
              if (query.type === "text") {
                onUpdate({ type: "image", content: "" });
                fileInputRef.current?.click();
              } else {
                onUpdate({ type: "text", content: "" });
              }
            }}
            aria-label={query.type === "text" ? "Switch to image query" : "Switch to text query"}
            className="text-outline hover:text-on-surface transition-colors p-1"
          >
            <Icon name={query.type === "text" ? "image" : "text_fields"} size={16} />
          </button>
          {canRemove && (
            <button
              onClick={onRemove}
              aria-label="Remove query"
              className="text-error opacity-70 hover:opacity-100 transition-colors p-1"
            >
              <Icon name="delete" size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="p-3 bg-surface-container-lowest">
        {query.type === "text" ? (
          <textarea
            className="w-full h-20 resize-none bg-transparent border-none focus:ring-0 p-0 text-body-sm outline-none"
            placeholder="Enter query text..."
            value={query.content}
            onChange={(e) => onUpdate({ content: e.target.value })}
          />
        ) : (
          <div className="relative">
            {query.content ? (
              <div className="relative">
                <img
                  src={query.content}
                  alt="Query"
                  className="w-full h-20 object-cover rounded"
                />
                <button
                  onClick={() => onUpdate({ content: "" })}
                  className="absolute top-1 right-1 bg-black/50 rounded-full p-0.5"
                >
                  <Icon name="close" size={14} className="text-white" />
                </button>
              </div>
            ) : (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="w-full h-20 border-2 border-dashed border-outline-variant rounded flex items-center justify-center cursor-pointer hover:bg-surface-container-high transition-colors"
              >
                <Icon name="image" size={24} className="text-outline" />
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleImageUpload}
            />
          </div>
        )}
        {isFileDragging && (
          <div className="mt-2 text-center text-label-xs font-semibold text-red-600">
            Drop to use this image
          </div>
        )}
        {imageError && (
          <div className="mt-2 text-label-xs text-error" role="alert">
            {imageError}
          </div>
        )}
        {query.type === "text" && voiceState !== "idle" && (
          <div className="mt-2 text-label-xs text-primary" role="status">
            {voiceState === "listening" ? "Listening…" : "Finishing transcription…"}
            {voicePreview ? ` ${voicePreview}` : ""}
          </div>
        )}
        {query.type === "text" && voiceError && (
          <div className="mt-2 text-label-xs text-error" role="alert">
            {voiceError}
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleImageUpload}
        />
      </div>

      {/* Top K & AI Enhance */}
      <div className="flex justify-between items-center px-3 py-2 border-t border-surface-variant">
        <div className="flex items-center gap-2">
          <span className="text-label-sm text-on-surface-variant">Top K</span>
          <input
            className="w-16 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1 font-mono text-mono-sm outline-none focus:border-primary text-right"
            type="number"
            min={1}
            max={10000}
            aria-label={hasVectorQuery ? "Raw Milvus Top K candidates" : "Maximum filter matches"}
            title={
              hasVectorQuery
                ? "Raw Milvus candidates before object and OCR/ASR post-filters (1–10000)"
                : "Maximum matching frames returned by this filter-only box (1–10000)"
            }
            value={query.topK ?? 1000}
            onChange={(e) =>
              onUpdate({ topK: Math.min(10000, Math.max(1, Number(e.target.value) || 1)) })
            }
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-label-sm text-on-surface-variant">AI Enhance</span>
          <Toggle
            checked={query.enhance ?? true}
            onChange={(enhance) => onUpdate({ enhance })}
            label="AI Enhance"
          />
        </div>
      </div>

      {/* Footer - Expandable Tags/Keywords */}
      <div className="bg-surface-bright rounded-b-lg border-t border-surface-variant">
        <button
          onClick={() => setShowTags(!showTags)}
          className="w-full px-3 py-2 flex items-center gap-2 border-b border-surface-variant cursor-pointer hover:bg-surface-container-high transition-colors"
        >
          <Icon name="sell" size={14} className="text-outline" />
          <span className="text-label-sm text-on-surface-variant">
            Tags {query.tags && query.tags.length > 0 && `(${query.tags.length})`}
          </span>
          <Icon
            name={showTags ? "expand_less" : "expand_more"}
            size={16}
            className="text-outline ml-auto"
          />
        </button>
        {showTags && (
          <div className="p-3 border-b border-surface-variant">
            <TagInput
              tags={query.tags || []}
              onChange={(tags) => onUpdate({ tags })}
              placeholder="Search COCO class..."
              suggestions={COCO_CLASS_NAMES}
              allowCustomValues={false}
            />
            <MatchModeToggle
              label="Match tags"
              mode={query.tagMatchMode ?? "and"}
              onChange={(tagMatchMode) => onUpdate({ tagMatchMode })}
            />
          </div>
        )}
        <button
          onClick={() => setShowKeywords(!showKeywords)}
          className="w-full px-3 py-2 flex items-center gap-2 cursor-pointer hover:bg-surface-container-high transition-colors rounded-b-lg"
        >
          <Icon name="key" size={14} className="text-outline" />
          <span className="text-label-sm text-on-surface-variant">
            Keywords
            {keywordCount > 0 && ` (${keywordCount})`}
          </span>
          <Icon
            name={showKeywords ? "expand_less" : "expand_more"}
            size={16}
            className="text-outline ml-auto"
          />
        </button>
        {showKeywords && (
          <div className="p-3 space-y-3">
            <KeywordFieldModeToggle
              mode={keywordFieldMode}
              onChange={(keywordFieldMode) => onUpdate({ keywordFieldMode })}
            />
            <div>
              <span className="text-label-sm text-on-surface-variant">OCR</span>
              <TagInput
                tags={query.ocrKeywords || []}
                onChange={(ocrKeywords) => onUpdate({ ocrKeywords })}
                placeholder="Add OCR keyword..."
              />
              <div className="mt-3 flex items-center justify-between gap-2">
                <MatchModeToggle
                  label="Match OCR"
                  mode={query.ocrMatchMode ?? "and"}
                  onChange={(ocrMatchMode) => onUpdate({ ocrMatchMode })}
                  className=""
                  disabled={ocrDisabled}
                />
                <KeywordSearchModeToggle
                  label="OCR"
                  mode={query.ocrSearchMode ?? "exact"}
                  onChange={(ocrSearchMode) => onUpdate({ ocrSearchMode })}
                  disabled={ocrDisabled}
                />
              </div>
            </div>
            <div>
              <span className="text-label-sm text-on-surface-variant">ASR</span>
              <TagInput
                tags={query.asrKeywords || []}
                onChange={(asrKeywords) => onUpdate({ asrKeywords })}
                placeholder="Add ASR keyword..."
              />
              <div className="mt-3 flex items-center justify-between gap-2">
                <MatchModeToggle
                  label="Match ASR"
                  mode={query.asrMatchMode ?? "and"}
                  onChange={(asrMatchMode) => onUpdate({ asrMatchMode })}
                  className=""
                  disabled={asrDisabled}
                />
                <KeywordSearchModeToggle
                  label="ASR"
                  mode={query.asrSearchMode ?? "exact"}
                  onChange={(asrSearchMode) => onUpdate({ asrSearchMode })}
                  disabled={asrDisabled}
                />
              </div>
              {(query.asrSearchMode ?? "exact") === "exact" && (
                <div className="mt-2 flex items-center justify-between gap-2">
                  <label
                    htmlFor={`asr-slop-${query.id}`}
                    className="text-label-xs text-on-surface-variant"
                    title="Words the transcript may drift from the phrase. Order is never loosened."
                  >
                    Phrase slop
                  </label>
                  <input
                    id={`asr-slop-${query.id}`}
                    type="number"
                    min={0}
                    max={10}
                    step={1}
                    value={query.asrPhraseSlop ?? 0}
                    disabled={asrDisabled}
                    onChange={(event) => {
                      const parsed = Number.parseInt(event.target.value, 10);
                      onUpdate({
                        asrPhraseSlop: Number.isNaN(parsed)
                          ? 0
                          : Math.max(0, Math.min(10, parsed)),
                      });
                    }}
                    className="w-16 rounded border border-outline-variant bg-surface-container px-2 py-0.5 text-right font-mono text-label-xs text-on-surface disabled:cursor-not-allowed disabled:opacity-45"
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
