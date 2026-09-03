/** Browser-only speech-recognition helpers used by text query boxes. */

export const VOICE_LANGUAGES = {
  vietnamese: "vi-VN",
  english: "en-US",
} as const;

export type VoiceLanguage = (typeof VOICE_LANGUAGES)[keyof typeof VOICE_LANGUAGES];

export interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

export interface SpeechRecognitionResultLike {
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternativeLike;
}

export interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}

export interface BrowserSpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onspeechend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export interface SpeechRecognitionConstructor {
  new (): BrowserSpeechRecognition;
}

export interface SpeechRecognitionWindow {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
}

/** Returns Chrome's standard or prefixed recognition constructor, if available. */
export function getSpeechRecognitionConstructor(
  browserWindow: SpeechRecognitionWindow | undefined =
    typeof window === "undefined" ? undefined : (window as unknown as SpeechRecognitionWindow),
): SpeechRecognitionConstructor | null {
  return browserWindow?.SpeechRecognition ?? browserWindow?.webkitSpeechRecognition ?? null;
}

/** Apply the stable short-query configuration before calling recognition.start(). */
export function configureSpeechRecognition(
  recognition: BrowserSpeechRecognition,
  language: VoiceLanguage,
): void {
  recognition.lang = language;
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
}

/** Extract final and in-progress text from one browser recognition result event. */
export function collectRecognitionText(event: SpeechRecognitionEventLike): {
  finalText: string;
  interimText: string;
} {
  const finalParts: string[] = [];
  const interimParts: string[] = [];
  for (let index = event.resultIndex; index < event.results.length; index += 1) {
    const result = event.results[index];
    const transcript = result[0]?.transcript?.trim();
    if (!transcript) continue;
    (result.isFinal ? finalParts : interimParts).push(transcript);
  }
  return { finalText: finalParts.join(" "), interimText: interimParts.join(" ") };
}

/** Map vendor error codes to concise, actionable UI text. */
export function speechRecognitionErrorMessage(error: string): string {
  switch (error) {
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone permission was denied.";
    case "audio-capture":
      return "No microphone is available.";
    case "network":
      return "Speech recognition needs an internet connection.";
    case "no-speech":
      return "No speech was detected.";
    case "language-not-supported":
      return "This browser does not support the selected language.";
    default:
      return "Voice recognition failed. Try again in Google Chrome.";
  }
}
