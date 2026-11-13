import { expect, test } from "vitest";
import { toIsbn13 } from "../src/isbn";

test("converts an ISBN-10", () => {
  expect(toIsbn13("0306406152")).toBe("9780306406157");
});

test("ignores hyphens and spaces", () => {
  expect(toIsbn13("978-0-306 40615-7")).toBe("9780306406157");
});

test("rejects a wrong check digit", () => {
  expect(() => toIsbn13("9780306406158")).toThrow("wrong check digit");
});
