import { describe, expect, it } from "vitest";

import { developmentSeedError } from "../../src/lib/seeds";

describe("development seed selection", () => {
  it("accepts only an explicit development seed", () => {
    expect(developmentSeedError("12000")).toBeNull();
    expect(developmentSeedError("12999")).toBeNull();
    for (const value of ["", " ", "42", "46", "13000", "900000", "12000.5", "abc"])
      expect(developmentSeedError(value)).toContain("development seed");
  });
});
