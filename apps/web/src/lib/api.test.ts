import { describe, expect, it } from "vitest";

import { classifyDresSubmit, type DresSubmitResult } from "./api";

// The exact body DRES returned when the team submitted past its correct-answer
// quota: HTTP 404, `status: false`, and no `submission` field.
const filterRejected: DresSubmitResult = {
  code: "DRES_REJECTED",
  status: false,
  description:
    "Submission 9910a5d6-6d72-4747-8411-27c8e5233431 was rejected by filter: " +
    "Maximum number of correct submissions (1) exceeded for the team.",
};

describe("classifyDresSubmit", () => {
  it("reads the verdict code the API attaches", () => {
    expect(classifyDresSubmit({ code: "DRES_CORRECT", submission: "CORRECT" })).toBe("correct");
    expect(classifyDresSubmit({ code: "DRES_WRONG", submission: "WRONG" })).toBe("wrong");
    expect(classifyDresSubmit({ code: "DRES_DUPLICATE", status: false })).toBe("duplicate");
  });

  it("reports a filter rejection as rejected, not duplicate", () => {
    expect(classifyDresSubmit(filterRejected)).toBe("rejected");
  });

  it("falls back to the raw body when the code is missing", () => {
    expect(classifyDresSubmit({ submission: "CORRECT", status: true })).toBe("correct");
    expect(classifyDresSubmit({ submission: "WRONG" })).toBe("wrong");
    expect(classifyDresSubmit({ status: false, description: "Already submitted." })).toBe(
      "duplicate",
    );
  });

  it("treats an unrecognised body as an error", () => {
    expect(classifyDresSubmit({})).toBe("error");
  });
});
