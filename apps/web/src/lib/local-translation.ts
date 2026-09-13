"use client";

interface LocalTranslator {
  translate(text: string): Promise<string>;
}

interface TranslatorApi {
  availability(options: {
    sourceLanguage: string;
    targetLanguage: string;
  }): Promise<string>;
  create(options: {
    sourceLanguage: string;
    targetLanguage: string;
  }): Promise<LocalTranslator>;
}

interface TranslatorGlobal {
  Translator?: TranslatorApi;
}

let translatorPromise: Promise<LocalTranslator | null> | null = null;

async function getLocalTranslator(): Promise<LocalTranslator | null> {
  if (typeof window === "undefined") return null;

  const translatorApi = (globalThis as TranslatorGlobal).Translator;
  if (!translatorApi) return null;

  if (!translatorPromise) {
    translatorPromise = (async () => {
      const options = { sourceLanguage: "vi", targetLanguage: "en" };
      const availability = await translatorApi.availability(options);
      if (availability === "unavailable") return null;
      return translatorApi.create(options);
    })().catch(() => {
      translatorPromise = null;
      return null;
    });
  }

  return translatorPromise;
}

/** Translate a Vietnamese search query in Chrome without sending it to a server. */
export async function translateVietnameseToEnglish(text: string): Promise<string | null> {
  const translator = await getLocalTranslator();
  if (!translator) return null;

  try {
    const translated = (await translator.translate(text)).trim();
    return translated || null;
  } catch {
    return null;
  }
}

/** Prepare a text search, falling back to the backend enhancer when needed. */
export async function prepareSearchText(
  text: string,
  enhance: boolean,
): Promise<{ text: string; enhance: boolean }> {
  if (!enhance || !text.trim()) {
    return { text, enhance: false };
  }

  const translated = await translateVietnameseToEnglish(text);
  return translated
    ? { text: translated, enhance: false }
    : { text, enhance: true };
}
