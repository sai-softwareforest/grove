import { describe, expect, it } from "vitest";
import { Catalogue } from "../src/catalogue";

describe("Catalogue", () => {
  it("counts a second copy instead of adding a second entry", () => {
    const catalogue = new Catalogue();
    catalogue.add("0306406152", "Advanced Engineering Mathematics", 45);
    const book = catalogue.add("978-0-306-40615-7", "Advanced Engineering Mathematics", 45);
    expect(book.copies).toBe(2);
    expect(catalogue.search("advanced")).toHaveLength(1);
  });

  it("finds a title whatever the case", () => {
    const catalogue = new Catalogue();
    catalogue.add("9780306406157", "Advanced Engineering Mathematics", 45);
    expect(catalogue.search("ENGINEERING")[0].isbn).toBe("9780306406157");
  });
});
