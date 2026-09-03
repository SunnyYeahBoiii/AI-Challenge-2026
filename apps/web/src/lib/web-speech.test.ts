import { describe, expect, it } from "vitest";

import {
  VOICE_LANGUAGES,
  collectRecognitionText,
  configureSpeechRecognition,
  getSpeechRecognitionConstructor,
  speechRecognitionErrorMessage,
  type BrowserSpeechRecognition,
} from "./web-speech";

function recognition(): BrowserSpeechRecognition {
  return {
    continuous: false,
    interimResults: false,
    lang: "",
    maxAlternatives: 0,
    onstart: null,
    onend: null,
    onspeechend: null,
    onerror: null,
    onresult: null,
    start() {},
    stop() {},
    abort() {},
  };
}

describe("web speech helpers", () => {
  it("accepts standard and Chrome-prefixed recognition constructors", () => {
    class StandardRecognition {}
    class PrefixedRecognition {}

    expect(getSpeechRecognitionConstructor({ SpeechRecognition: StandardRecognition as never }))
      .toBe(StandardRecognition);
    expect(getSpeechRecognitionConstructor({ webkitSpeechRecognition: PrefixedRecognition as never }))
      .toBe(PrefixedRecognition);
    expect(getSpeechRecognitionConstructor({})).toBeNull();
  });

  it("configures Vietnamese recognition for live query feedback", () => {
    const instance = recognition();
    configureSpeechRecognition(instance, VOICE_LANGUAGES.vietnamese);

    expect(instance).toMatchObject({
      lang: "vi-VN",
      continuous: true,
      interimResults: true,
      maxAlternatives: 1,
    });
  });

  it("separates final transcript text from interim text", () => {
    expect(collectRecognitionText({
      resultIndex: 0,
      results: [
        { isFinal: true, 0: { transcript: "  chào Việt Nam " } },
        { isFinal: false, 0: { transcript: " hôm nay" } },
      ],
    })).toEqual({ finalText: "chào Việt Nam", interimText: "hôm nay" });
  });

  it("returns useful microphone and network errors", () => {
    expect(speechRecognitionErrorMessage("not-allowed")).toContain("permission");
    expect(speechRecognitionErrorMessage("network")).toContain("internet");
  });
});
