/**
 * Choosing between the structured answer and the prose.
 *
 * Not every assistant turn carries an answer: a clarification and an
 * ANSWER-routed reply are plain text, and older rows predate the field.
 * Falling back to the prose is right; rendering an error, or nothing,
 * would lose the reply.
 */

import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { MessageBubble } from "@/features/thread/component/message-bubble";
import type { Message } from "@/features/thread/types";
import recorded from "./fixtures/reply.json";

function message(overrides: Partial<Message> = {}): Message {
  return {
    message_id: 1,
    role: "assistant",
    content: "The prose form.",
    created_at: "2026-09-01T10:00:00Z",
    ...overrides,
  };
}

it("renders the structured answer when the turn carries one", () => {
  render(<MessageBubble message={message({ answer: recorded.answer })} />);
  expect(screen.getByText(/checked against the source/i)).toBeInTheDocument();
});

it("falls back to the prose when there is no answer", () => {
  render(<MessageBubble message={message()} />);
  expect(screen.getByText("The prose form.")).toBeInTheDocument();
});

it("falls back rather than throwing when the answer does not parse", () => {
  render(
    <MessageBubble message={message({ answer: { nonsense: true } })} />,
  );
  expect(screen.getByText("The prose form.")).toBeInTheDocument();
});

it("shows a clarification as the question it is", () => {
  render(
    <MessageBubble
      message={message({ content: "Which state is this in?" })}
    />,
  );
  expect(screen.getByText("Which state is this in?")).toBeInTheDocument();
});

it("never renders a user turn as a verified answer", () => {
  render(
    <MessageBubble
      message={message({ role: "user", content: "My question", answer: recorded.answer })}
    />,
  );
  expect(screen.queryByText(/checked against the source/i)).not.toBeInTheDocument();
  expect(screen.getByText("My question")).toBeInTheDocument();
});
