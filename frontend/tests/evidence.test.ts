/**
 * Reading an evidence id.
 *
 * These are the functions that decide what badge a source wears. A wrong
 * answer here tells a lawyer that their own uploaded pleading is settled
 * law, or the reverse -- so the unknown case must stay unknown rather
 * than fall into whichever bucket is nearest.
 */

import { describe, expect, it } from "vitest";

import { provenanceOf, shortLabel, sourceKind } from "@/features/thread/evidence";
import { Provenance } from "@/types/common";

describe("sourceKind", () => {
  it("reads the three prefixes the corpus actually uses", () => {
    expect(sourceKind("act:2158:sec-18")).toBe("statute");
    expect(sourceKind("judgment:escr010000722020")).toBe("judgment");
    expect(sourceKind("case-file:abc:notice.pdf")).toBe("document");
  });

  it("reports an unrecognised id as unknown, not as a guess", () => {
    expect(sourceKind("something:else")).toBe("unknown");
    expect(sourceKind("")).toBe("unknown");
  });
});

describe("provenanceOf", () => {
  it("marks the curated corpus as static knowledge", () => {
    expect(provenanceOf("act:2158:sec-18")).toBe(Provenance.Static);
    expect(provenanceOf("judgment:x")).toBe(Provenance.Static);
  });

  it("marks a case upload as the reader's own document", () => {
    expect(provenanceOf("case-file:c1:contract.pdf")).toBe(Provenance.Document);
  });

  it("never claims dynamic research, which nothing marks today", () => {
    const ids = ["act:1:sec-2", "judgment:y", "case-file:c:z", "mystery:1"];
    expect(ids.map(provenanceOf)).not.toContain(Provenance.Dynamic);
  });

  it("returns null rather than badging an id it cannot place", () => {
    expect(provenanceOf("mystery:1")).toBeNull();
  });
});

describe("shortLabel", () => {
  it("shows the section number, which is the part a lawyer acts on", () => {
    expect(shortLabel("act:2158:sec-18")).toBe("s. 18");
    expect(shortLabel("act:11:sec-18(1)")).toBe("s. 18(1)");
  });

  it("shows a case file by its filename", () => {
    expect(shortLabel("case-file:c1:notice.pdf")).toBe("notice.pdf");
  });

  it("falls back to the whole id rather than inventing a label", () => {
    expect(shortLabel("mystery:1")).toBe("mystery:1");
  });
});
