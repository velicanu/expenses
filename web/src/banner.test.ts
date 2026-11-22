import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { friendly } from "./banner";

describe("friendly", () => {
  it("tells the user what to do when there is no data yet", () => {
    expect(friendly(new ApiError(409, "no data yet: upload a CSV first"))).toMatch(/Upload a CSV first/);
  });
  it("shows other API messages as they are, including a busy pipeline", () => {
    expect(friendly(new ApiError(409, "the pipeline is already running"))).toBe("the pipeline is already running");
    expect(friendly(new ApiError(503, "Plaid is unavailable: cannot read the keys"))).toBe("Plaid is unavailable: cannot read the keys");
  });
  it("handles non-API errors", () => {
    expect(friendly(new Error("network down"))).toBe("network down");
    expect(friendly("odd")).toBe("Something went wrong.");
  });
});
