"use client";

import { isAxiosError } from "axios";
import { useRef, useState, type ChangeEvent, type ClipboardEvent, type FormEvent } from "react";

import { fetchRemoteImage } from "@/lib/api";

import { Icon } from "./icon";

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const SUPPORTED_IMAGE_TYPES = new Set([
  "image/bmp",
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/webp",
]);

interface ImageQueryInputProps {
  content: string;
  onChange: (content: string) => void;
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Could not read the image"));
    reader.readAsDataURL(file);
  });
}

function verifyBrowserImage(dataUrl: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve();
    image.onerror = () => reject(new Error("The selected file is not a valid image"));
    image.src = dataUrl;
  });
}

function remoteImageError(error: unknown): string {
  if (!isAxiosError(error)) return "Could not download the image URL";
  return (
    (error.response?.data as { error?: { message?: string } } | undefined)?.error?.message ??
    error.message
  );
}

export function ImageQueryInput({ content, onChange }: ImageQueryInputProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState(false);

  const applyFile = async (file: File) => {
    if (!SUPPORTED_IMAGE_TYPES.has(file.type)) {
      setError("Use a PNG, JPEG, WebP, GIF, or BMP image");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError("Image must be 8 MiB or smaller");
      return;
    }

    try {
      const dataUrl = await readFileAsDataUrl(file);
      await verifyBrowserImage(dataUrl);
      setError(null);
      setImageUrl("");
      onChange(dataUrl);
    } catch (fileError) {
      setError(fileError instanceof Error ? fileError.message : "Could not read the image");
    }
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void applyFile(file);
  };

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    const imageItem = Array.from(event.clipboardData.items).find((item) =>
      item.type.startsWith("image/"),
    );
    const file = imageItem?.getAsFile();
    if (!file) return;

    event.preventDefault();
    void applyFile(file);
  };

  const handleUrlSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedUrl = imageUrl.trim();
    try {
      const parsed = new URL(trimmedUrl);
      if (!(["http:", "https:"] as string[]).includes(parsed.protocol)) throw new Error();
    } catch {
      setError("Enter a valid http or https image URL");
      return;
    }

    setIsFetching(true);
    setError(null);
    try {
      const remoteImage = await fetchRemoteImage(trimmedUrl);
      onChange(remoteImage.dataUrl);
    } catch (fetchError) {
      setError(remoteImageError(fetchError));
    } finally {
      setIsFetching(false);
    }
  };

  const clearImage = () => {
    setError(null);
    setImageUrl("");
    onChange("");
  };

  return (
    <div
      tabIndex={0}
      onPaste={handlePaste}
      aria-label="Image query input. Paste an image with Command or Control V."
      className="relative outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
    >
      {content ? (
        <div className="relative">
          <img src={content} alt="Query" className="w-full h-20 object-cover rounded" />
          <button
            type="button"
            onClick={clearImage}
            aria-label="Remove query image"
            className="absolute top-1 right-1 bg-black/50 rounded-full p-0.5"
          >
            <Icon name="close" size={14} className="text-white" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="w-full h-20 border-2 border-dashed border-outline-variant rounded flex flex-col items-center justify-center cursor-pointer hover:bg-surface-container-high transition-colors"
        >
          <Icon name="image" size={24} className="text-outline" />
          <span className="text-label-xs text-on-surface-variant mt-1">
            Paste image (Cmd/Ctrl+V) or choose file
          </span>
        </button>
      )}

      <form onSubmit={handleUrlSubmit} className="flex gap-1.5 mt-2">
        <input
          type="url"
          value={imageUrl}
          onChange={(event) => setImageUrl(event.target.value)}
          placeholder="Paste public image URL..."
          aria-label="Public image URL"
          disabled={isFetching}
          className="min-w-0 flex-1 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1 text-body-xs outline-none focus:border-primary disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={isFetching || !imageUrl.trim()}
          className="shrink-0 bg-surface-container hover:bg-surface-variant border border-outline-variant text-on-surface text-label-xs px-2 py-1 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isFetching ? "Loading..." : "Use URL"}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-1.5 text-label-xs text-error">
          {error}
        </p>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,image/bmp"
        className="hidden"
        onChange={handleFileChange}
      />
    </div>
  );
}
