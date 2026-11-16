import { parseFilters, toggle, toSearch } from "./anomalyFilters";

test("valid filters round-trip through the URL", () => {
  const q = parseFilters(new URLSearchParams("severity=HIGH&severity=CRITICAL&status=OPEN&icao24=ABC1&min_confidence=0.5&sort=confidence&order=asc&offset=50"));
  expect(q).toMatchObject({ severity: ["HIGH", "CRITICAL"], status: ["OPEN"], icao24: "abc1", min_confidence: 0.5, sort: "confidence", order: "asc", offset: 50 });
  expect(parseFilters(toSearch(q))).toEqual(q);
});

test("malformed or hostile values are dropped, never forwarded to the API", () => {
  const q = parseFilters(new URLSearchParams("severity=SEVERE&status=DONE&icao24=%25&detection_type=x'%20OR%201=1&rule_id=DET-1&min_confidence=5&sort=id;--&order=sideways&offset=-3"));
  expect(q).toEqual({ sort: "severity", order: "desc", offset: 0 });
});

test("toggle adds and removes", () => {
  expect(toggle(undefined, "HIGH")).toEqual(["HIGH"]);
  expect(toggle(["HIGH", "LOW"], "HIGH")).toEqual(["LOW"]);
});
