/**
 * What an evidence id is, read from its prefix.
 *
 * The corpus uses exactly three (`act:`, `judgment:`, `case-file:`), so
 * this is a lookup and not a guess. Anything else is reported as unknown
 * rather than assumed into one of them -- mislabelling a source is the
 * one thing this screen must not do.
 */

import { Provenance } from "@/types/common";

export type SourceKind = "statute" | "judgment" | "document" | "unknown";

export function sourceKind(id: string): SourceKind {
  if (id.startsWith("act:")) return "statute";
  if (id.startsWith("judgment:")) return "judgment";
  if (id.startsWith("case-file:")) return "document";
  return "unknown";
}

/**
 * Where the reader should understand this came from.
 *
 * Only two of the three provenance badges can occur here. STATIC
 * KNOWLEDGE covers the curated corpus -- India Code and the Supreme Court
 * reports -- and YOUR DOCUMENT covers a case upload. DYNAMIC RESEARCH
 * describes material retrieved live for one question, and nothing in an
 * answer is marked that way today, so this never claims it.
 */
export function provenanceOf(id: string): Provenance | null {
  const kind = sourceKind(id);
  if (kind === "document") return Provenance.Document;
  if (kind === "statute" || kind === "judgment") return Provenance.Static;
  return null;
}

/** A pinpoint joined to the label it narrows.
 *
 *  A statutory marker is written against its section with no space --
 *  "s. 18(1)" is how it is cited and "s. 18 (1)" is not. A paragraph
 *  reads as its own word after the citation. The marker's own leading
 *  bracket is what tells the two apart, which is why the backend sends it
 *  raw rather than pre-joined.
 */
function withPinpoint(label: string, pinpoint?: string | null): string {
  if (!pinpoint) return label;
  return pinpoint.startsWith("(") ? `${label}${pinpoint}` : `${label} ${pinpoint}`;
}

/** A short, human label for a citation marker. Ids are opaque, so this
 *  shows the part a lawyer can act on and keeps the whole id in the
 *  title attribute.
 *
 *  The pinpoint is appended when the source carried one. Most short
 *  statute sections carry none -- they are retrieved whole -- so this must
 *  read correctly without it rather than treating its absence as a gap. */
export function shortLabel(
  id: string,
  citation?: string | null,
  pinpoint?: string | null,
): string {
  // Act ids are not all numeric -- the codes ingested in September are
  // named (`act:crpc-1973`, `act:ipc-1860`), and the old `\d+` pattern
  // missed them, so "s. 438" rendered as the raw `act:crpc-1973:sec-438`.
  const section = /^act:[^:]+:sec-(.+)$/.exec(id);
  if (section) return withPinpoint(`s. ${section[1]}`, pinpoint);
  if (id.startsWith("case-file:")) {
    return id.split(":").slice(2).join(":") || "document";
  }
  // Every judgment used to read "judgment", so three cited authorities
  // rendered as three identical chips. The reporter citation is what tells
  // them apart, and what a reader would look up.
  if (id.startsWith("judgment:")) {
    return withPinpoint(citation?.trim() || "judgment", pinpoint);
  }
  return id;
}
