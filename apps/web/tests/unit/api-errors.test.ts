// @vitest-environment node
import { describe, expect, it } from "vitest";

import { ApiError, isProblemDetail } from "@/lib/api/errors";

describe("isProblemDetail", () => {
  it("accepts the API's problem details", () => {
    expect(isProblemDetail({ title: "Not found", status: 404, code: "NOT_FOUND" })).toBe(true);
  });

  it.each([null, "Not found", 404, {}, { title: "x", status: "404", code: "X" }, { title: "x" }])(
    "rejects %j",
    (value) => {
      expect(isProblemDetail(value)).toBe(false);
    },
  );
});

describe("ApiError", () => {
  it("carries the API's code, status, request id and field errors", () => {
    const response = new Response(null, { status: 422, headers: { "x-request-id": "header-id" } });
    const error = ApiError.fromResponse(response, {
      title: "Request is invalid",
      status: 422,
      code: "VALIDATION_ERROR",
      detail: "Correct the listed fields and try again.",
      errors: [{ detail: "Field required", code: "missing", pointer: "/moveIn" }],
      requestId: "body-id",
    });

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      name: "ApiError",
      message: "Correct the listed fields and try again.",
      status: 422,
      code: "VALIDATION_ERROR",
      requestId: "body-id",
    });
    expect(error.fieldErrors).toEqual([
      { detail: "Field required", code: "missing", pointer: "/moveIn" },
    ]);
  });

  it("reports an error response without problem details as unexpected", () => {
    const response = new Response("<html>Bad gateway</html>", {
      status: 502,
      headers: { "x-request-id": "edge-id" },
    });

    const error = ApiError.fromResponse(response, "<html>Bad gateway</html>");

    expect(error).toMatchObject({ status: 502, code: "UNEXPECTED_RESPONSE", requestId: "edge-id" });
    expect(error.problem).toBeUndefined();
    expect(error.fieldErrors).toEqual([]);
  });

  it("tells an unreachable API from a slow one", () => {
    const unreachable = ApiError.fromFailure(new TypeError("fetch failed"));
    const slow = ApiError.fromFailure(new DOMException("too slow", "TimeoutError"));

    expect(unreachable).toMatchObject({ status: 0, code: "API_UNREACHABLE" });
    expect(unreachable.cause).toBeInstanceOf(TypeError);
    expect(slow).toMatchObject({ status: 0, code: "API_TIMEOUT" });
  });
});
