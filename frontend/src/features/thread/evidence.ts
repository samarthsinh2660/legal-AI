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

/** A short, human label for a citation marker. Ids are opaque, so this
 *  shows the part a lawyer can act on and keeps the whole id in the
 *  title attribute. */
export function shortLabel(id: string): string {
  const section = /^act:\d+:sec-(.+)$/.exec(id);
  if (section) return `s. ${section[1]}`;
  if (id.startsWith("case-file:")) {
    return id.split(":").slice(2).join(":") || "document";
  }
  if (id.startsWith("judgment:")) return "judgment";
  return id;
}
