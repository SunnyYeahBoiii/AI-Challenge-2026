"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface SpeechRecognitionAlternativeLike {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionEventLike {
  results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionErrorEventLike {
  error: string;
}

interface BrowserSpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onend: (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  start: () => void;
  stop: () => void;
}

interface BrowserSpeechRecognitionConstructor {
  new (): BrowserSpeechRecognition;
}

interface BrowserWindow extends Window {
  SpeechRecognition?: BrowserSpeechRecognitionConstructor;
  webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
}

export interface UseVoiceTypingOptions {
  keepListeningAcrossPauses: boolean;
  language: string;
  minimumConfidence: number;
  onTranscript: (transcript: string) => void;
}

export interface VoiceTypingConfig {
  keepListeningAcrossPauses: boolean;
  minimumConfidence: number;
}

export const DEFAULT_VOICE_TYPING_CONFIG: VoiceTypingConfig = {
  keepListeningAcrossPauses: true,
  minimumConfidence: 0.55,
};

export interface VoiceTypingControls {
  error: string | null;
  isListening: boolean;
  isSupported: boolean;
  startListening: () => void;
  stopListening: () => void;
}

function getSpeechRecognitionConstructor(): BrowserSpeechRecognitionConstructor | null {
  if (typeof window === "undefined") {
    return null;
  }

  const browserWindow = window as BrowserWindow;
  return browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition ?? null;
}

function getErrorMessage(error: string): string {
  switch (error) {
    case "audio-capture":
      return "Không tìm thấy microphone. Hãy kiểm tra thiết bị âm thanh.";
    case "network":
      return "Không thể kết nối dịch vụ nhận dạng giọng nói.";
    case "no-speech":
      return "Không nhận được giọng nói rõ ràng. Hãy nói gần microphone hơn.";
    case "not-allowed":
    case "service-not-allowed":
      return "Hãy cho phép trình duyệt sử dụng microphone.";
    default:
      return "Không thể nhận dạng giọng nói. Hãy thử lại hoặc nhập văn bản.";
  }
}

/**
 * Uses the browser's speech-recognition engine for short, user-initiated dictation.
 * The Web Speech API owns microphone capture, so audio constraints such as
 * noiseSuppression cannot be reliably applied here.
 */
export function useVoiceTyping({
  keepListeningAcrossPauses,
  language,
  minimumConfidence,
  onTranscript,
}: UseVoiceTypingOptions): VoiceTypingControls {
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  const keepListeningRef = useRef(false);
  const keepListeningAcrossPausesRef = useRef(keepListeningAcrossPauses);
  const minimumConfidenceRef = useRef(minimumConfidence);
  const [error, setError] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [isSupported, setIsSupported] = useState(false);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    minimumConfidenceRef.current = minimumConfidence;
  }, [minimumConfidence]);

  useEffect(() => {
    keepListeningAcrossPausesRef.current = keepListeningAcrossPauses;
  }, [keepListeningAcrossPauses]);

  useEffect(() => {
    setIsSupported(getSpeechRecognitionConstructor() !== null);

    return () => {
      keepListeningRef.current = false;
      if (restartTimerRef.current) {
        clearTimeout(restartTimerRef.current);
      }
      recognitionRef.current?.stop();
    };
  }, []);

  const stopListening = useCallback(() => {
    keepListeningRef.current = false;
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    recognitionRef.current?.stop();
  }, []);

  const startListening = useCallback(() => {
    const SpeechRecognition = getSpeechRecognitionConstructor();
    if (!SpeechRecognition) {
      setError("Trình duyệt này không hỗ trợ voice typing.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = language;
    recognition.continuous = keepListeningAcrossPauses;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      let transcript = "";
      let hasLowConfidenceResult = false;

      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        const alternative = result[0];
        const hasConfidence = alternative.confidence > 0;
        const isTooUncertain = hasConfidence && alternative.confidence < minimumConfidenceRef.current;

        if (!result.isFinal) {
          continue;
        }
        if (isTooUncertain) {
          hasLowConfidenceResult = true;
          continue;
        }

        transcript += alternative.transcript;
      }

      if (transcript.trim()) {
        onTranscriptRef.current(transcript.trim());
      }
      if (hasLowConfidenceResult) {
        setError("Âm thanh chưa đủ rõ. Hãy nói sát microphone hơn.");
      } else {
        setError(null);
      }
    };
    recognition.onerror = (event) => {
      setError(getErrorMessage(event.error));
    };
    recognition.onend = () => {
      if (keepListeningRef.current && keepListeningAcrossPausesRef.current) {
        restartTimerRef.current = setTimeout(() => {
          try {
            recognition.start();
            setIsListening(true);
          } catch {
            keepListeningRef.current = false;
            setIsListening(false);
            setError("Không thể tiếp tục voice typing. Hãy thử lại.");
          }
        }, 150);
        return;
      }
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    keepListeningRef.current = true;
    setError(null);
    setIsListening(true);

    try {
      recognition.start();
    } catch {
      setIsListening(false);
      setError("Không thể bắt đầu voice typing. Hãy thử lại.");
    }
  }, [keepListeningAcrossPauses, language]);

  return { error, isListening, isSupported, startListening, stopListening };
}
