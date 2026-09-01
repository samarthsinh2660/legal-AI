/**
 * How an answer is rendered.
 *
 * This is the file that guards the product's central claim. The backend
 * keeps four distinct verdicts about a claim -- supported, supported in
 * part, contradicted, and never examined -- and the whole point of that
 * effort is lost if the screen renders any two of them the same way.
 *
 * `docs/API.md` puts it directly: collapsing `unchecked` and
 * `needs_verification` "presents an unexamined claim as a refuted one, or
 * worse, the reverse".
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerView } from "@/features/thread/component/answer-view";
import { AnswerSchema, type Answer } from "@/features/thread/types";
import recorded from "./fixtures/reply.json";

function answer(overrides: Partial<Answer> = {}): Answer {
  return {
    question: "q",
    lede: "",
    key_elements: [],
    applicable_law: [],
    key_judgments: [],
    needs_verification: [],
    unchecked: [],
    partially_supported: [],
    support_not_checked: false,
    citations: [],
    disclaimer: "",
    ...overrides,
  };
}

describe("the four verdicts", () => {
  it("renders a checked claim under a heading that says so", () => {
    render(
      <AnswerView
        answer={answer({
          key_elements: [{ text: "Section 18 gives a refund.", evidence_ids: [] }],
        })}
      />,
    );
    expect(screen.getByText(/checked against the source/i)).toBeInTheDocument();
    expect(screen.getByText("Section 18 gives a refund.")).toBeInTheDocument();
  });

  it("does not describe an unchecked claim as unsupported", () => {
    render(<AnswerView answer={answer({ unchecked: ["A claim nobody examined."] })} />);

    expect(screen.getByText(/not checked/i)).toBeInTheDocument();
    expect(screen.getByText("A claim nobody examined.")).toBeInTheDocument();
    // The words reserved for a claim the evidence contradicts must not
    // appear anywhere near it.
    expect(screen.queryByText(/evidence against/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/unsupported/i)).not.toBeInTheDocument();
  });

  it("does not describe a contradicted claim as merely unchecked", () => {
    render(
      <AnswerView answer={answer({ needs_verification: ["The source says otherwise."] })} />,
    );
    expect(screen.getByText(/evidence against this/i)).toBeInTheDocument();
    expect(screen.queryByText(/^not checked$/i)).not.toBeInTheDocument();
  });

  it("keeps all three qualified verdicts apart when they occur together", () => {
    render(
      <AnswerView
        answer={answer({
          partially_supported: ["Narrower than claimed."],
          needs_verification: ["Contradicted."],
          unchecked: ["Never examined."],
        })}
      />,
    );

    // Three separate headings, three separate claims -- never merged into
    // one "problems" list.
    expect(screen.getByText(/supported in part/i)).toBeInTheDocument();
    expect(screen.getByText(/evidence against this/i)).toBeInTheDocument();
    expect(screen.getByText(/not checked/i)).toBeInTheDocument();
    expect(screen.getByText("Narrower than claimed.")).toBeInTheDocument();
    expect(screen.getByText("Contradicted.")).toBeInTheDocument();
    expect(screen.getByText("Never examined.")).toBeInTheDocument();
  });

  it("shows no qualifying block at all when every claim passed", () => {
    render(
      <AnswerView
        answer={answer({ key_elements: [{ text: "Clean.", evidence_ids: [] }] })}
      />,
    );
    expect(screen.queryByText(/supported in part/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/evidence against/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not checked/i)).not.toBeInTheDocument();
  });
});

describe("quick mode", () => {
  it("says once that support was not verified", () => {
    render(<AnswerView answer={answer({ support_not_checked: true })} />);
    expect(screen.getByText(/quick mode/i)).toBeInTheDocument();
  });

  it("stays silent when verification did run", () => {
    render(<AnswerView answer={answer({ support_not_checked: false })} />);
    expect(screen.queryByText(/quick mode/i)).not.toBeInTheDocument();
  });
});

describe("provenance", () => {
  it("marks corpus sources as static knowledge", () => {
    render(<AnswerView answer={answer({ citations: ["act:2158:sec-18"] })} />);
    expect(screen.getByText(/static knowledge/i)).toBeInTheDocument();
  });

  it("marks a case upload as the reader's own document", () => {
    render(<AnswerView answer={answer({ citations: ["case-file:c1:notice.pdf"] })} />);
    expect(screen.getByText(/your document/i)).toBeInTheDocument();
  });

  it("badges each provenance once, not once per citation", () => {
    render(
      <AnswerView
        answer={answer({ citations: ["act:1:sec-2", "judgment:x", "act:3:sec-4"] })}
      />,
    );
    expect(screen.getAllByText(/static knowledge/i)).toHaveLength(1);
  });

  it("claims no provenance for an id it cannot place", () => {
    render(<AnswerView answer={answer({ citations: ["mystery:1"] })} />);
    expect(screen.queryByText(/static knowledge/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/your document/i)).not.toBeInTheDocument();
  });
});

describe("citations", () => {
  it("links a statute to its neighbourhood so the reader can open it", () => {
    render(
      <AnswerView
        answer={answer({
          key_elements: [{ text: "Claim.", evidence_ids: ["act:2158:sec-18"] }],
        })}
      />,
    );
    const link = screen.getByTitle("act:2158:sec-18");
    expect(link).toHaveAttribute(
      "href",
      "/graph?anchor=act%3A2158%3Asec-18",
    );
  });
});

describe("a real recorded answer", () => {
  it("parses the payload the API actually returned", () => {
    const parsed = AnswerSchema.safeParse(recorded.answer);
    expect(parsed.success).toBe(true);
  });

  it("renders it with its lede, its claims and its disclaimer", () => {
    const parsed = AnswerSchema.parse(recorded.answer);
    render(<AnswerView answer={parsed} />);

    // The phrase occurs in both the lede and the first checked claim,
    // which is why this asserts presence rather than uniqueness.
    expect(
      screen.getAllByText(/unqualified right to seek a refund/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/not legal advice/i)).toBeInTheDocument();
    // This run was quick mode, and must say so.
    expect(screen.getByText(/quick mode/i)).toBeInTheDocument();
  });
});
