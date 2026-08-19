"use client";

import { useState } from "react";

import { MatchModeToggle } from "./match-mode-toggle";
import { Toggle } from "./toggle";

export interface KeywordSearchConfig {
  queryType?: "match" | "match_phrase";
  fuzzy?: boolean;
  operator?: "and" | "or";
  minimumShouldMatch?: string;
  prefixLength?: number;
  maxExpansions?: number;
  slop?: number;
}

const DEFAULT_CONFIG: Required<KeywordSearchConfig> = {
  queryType: "match",
  fuzzy: false,
  operator: "and",
  minimumShouldMatch: "100%",
  prefixLength: 2,
  maxExpansions: 20,
  slop: 0,
};

interface KeywordSearchOptionsProps {
  source: "OCR" | "ASR";
  config?: KeywordSearchConfig;
  onChange: (config: KeywordSearchConfig) => void;
}

/** Per-source options for one keyword's Elasticsearch match clause. */
export function KeywordSearchOptions({ source, config, onChange }: KeywordSearchOptionsProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const value = { ...DEFAULT_CONFIG, ...config };
  const update = (changes: KeywordSearchConfig) => onChange({ ...value, ...changes });
  const isPhrase = value.queryType === "match_phrase";

  return (
    <div className="mt-3 rounded border border-outline-variant bg-surface-container-lowest">
      <div className="flex items-center gap-2 p-2">
        <label className="text-label-sm text-on-surface-variant" htmlFor={`${source}-query-type`}>
          Query mode
        </label>
        <select
          id={`${source}-query-type`}
          className="ml-auto rounded border border-outline-variant bg-surface-container-lowest px-2 py-1 text-label-xs text-on-surface"
          value={value.queryType}
          onChange={(event) => update({
            queryType: event.target.value as "match" | "match_phrase",
            ...(event.target.value === "match_phrase" ? { fuzzy: false } : {}),
          })}
        >
          <option value="match">Match</option>
          <option value="match_phrase">Match phrase</option>
        </select>
      </div>
      <button
        type="button"
        className="w-full border-t border-outline-variant px-2 py-1 text-left text-label-xs text-primary hover:bg-surface-container-high"
        onClick={() => setShowAdvanced((open) => !open)}
      >
        {showAdvanced ? "Hide advanced options" : "Advanced options"}
      </button>
      {showAdvanced && (
        <div className="space-y-3 border-t border-outline-variant p-2">
          {isPhrase ? (
            <NumberOption label="Slop" value={value.slop} min={0} max={10}
              onChange={(slop) => update({ slop })} />
          ) : (
            <>
              <MatchModeToggle
                label="Token operator"
                mode={value.operator}
                className=""
                onChange={(operator) => update({
                  operator,
                  ...(operator === "and" ? { minimumShouldMatch: "100%" } : {}),
                })}
              />
              <label className="flex items-center gap-2 text-label-sm text-on-surface-variant">
                Minimum should match
                <input
                  className="ml-auto w-28 rounded border border-outline-variant bg-surface-container-lowest px-2 py-1 text-label-xs text-on-surface disabled:opacity-60"
                  list={`${source}-minimum-should-match`}
                  value={value.operator === "and" ? "100%" : value.minimumShouldMatch}
                  disabled={value.operator === "and"}
                  onChange={(event) => update({ minimumShouldMatch: event.target.value })}
                />
                <datalist id={`${source}-minimum-should-match`}>
                  <option value="100%" />
                  <option value="75%" />
                  <option value="2&lt;75%" />
                </datalist>
              </label>
              <Toggle
                checked={value.fuzzy}
                onChange={(fuzzy) => update({ fuzzy })}
                label={`Enable fuzzy ${source} matching`}
              />
              {value.fuzzy && (
                <div className="grid grid-cols-2 gap-2">
                  <NumberOption label="Prefix length" value={value.prefixLength} min={0} max={10}
                    onChange={(prefixLength) => update({ prefixLength })} />
                  <NumberOption label="Max expansions" value={value.maxExpansions} min={1} max={100}
                    onChange={(maxExpansions) => update({ maxExpansions })} />
                </div>
              )}
            </>
          )}
          {isPhrase && <p className="text-label-xs text-on-surface-variant">Fuzzy is unavailable for Match phrase.</p>}
        </div>
      )}
    </div>
  );
}

function NumberOption({ label, value, min, max, onChange }: {
  label: string; value: number; min: number; max: number; onChange: (value: number) => void;
}) {
  return <label className="flex items-center gap-2 text-label-xs text-on-surface-variant">
    {label}
    <input className="ml-auto w-14 rounded border border-outline-variant bg-surface-container-lowest px-1 py-1 text-right text-label-xs text-on-surface"
      type="number" min={min} max={max} value={value}
      onChange={(event) => onChange(Math.min(max, Math.max(min, Number(event.target.value) || min)))} />
  </label>;
}
