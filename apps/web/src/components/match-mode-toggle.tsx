"use client";

interface MatchModeToggleProps {
  label: string;
  mode: "and" | "or";
  onChange: (mode: "and" | "or") => void;
  className?: string;
  disabled?: boolean;
}

/** AND/OR switch shared by tag, OCR, and ASR keyword filters. */
export function MatchModeToggle({
  label,
  mode,
  onChange,
  className = "mt-3",
  disabled = false,
}: MatchModeToggleProps) {
  return (
    <div className={`${className} flex items-center gap-2`}>
      <span className="text-label-sm text-on-surface-variant">{label}</span>
      <div className="flex overflow-hidden rounded border border-outline-variant">
        {(["and", "or"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            disabled={disabled}
            className={`px-2 py-1 text-label-xs uppercase transition-colors ${
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
    </div>
  );
}
