/**
 * The application trail speaks the interface's language.
 *
 * The engine writes `message` in English — it is a server log line — and the
 * trail was printing it verbatim under a Portuguese heading: "Job found",
 * "Cover letter generated", and three identical rows reading "The user edited
 * the application before approval."
 *
 * What is pinned here is the rule the rest of the codebase already follows:
 * sentences are composed in the frontend, and the two cases where the server's
 * own words must survive — an error, and an event this build does not know —
 * still do.
 */

import { describe, expect, it } from "vitest";

import { applicationEventDetail } from "@/lib/format";

function event(overrides: Partial<Parameters<typeof applicationEventDetail>[0]> = {}) {
  return {
    event_type: "job_found",
    message: "Found via search: Senior Backend Engineer",
    payload: {},
    is_error: false,
    ...overrides,
  };
}

describe("applicationEventDetail", () => {
  it("answers in Portuguese instead of echoing the server's English", () => {
    expect(applicationEventDetail(event())).toBe("Encontrada por uma busca sua.");
    expect(
      applicationEventDetail(
        event({ event_type: "cover_letter_generated", message: "Generated a cover letter (en)." }),
      ),
    ).toBe("Rascunho gerado para você revisar e editar.");
  });

  it("names what an edit actually changed", () => {
    // Three of these in a row all said "the user edited the application", while
    // the payload had known which fields moved the whole time.
    const detail = applicationEventDetail(
      event({
        event_type: "user_edited",
        message: "The user edited the application before approval.",
        payload: { fields: ["cover_letter", "screening_answers"] },
      }),
    );

    expect(detail).toBe("Você alterou a carta de apresentação e as respostas de triagem.");
  });

  it("says nothing rather than something English when an edit names no fields", () => {
    const detail = applicationEventDetail(
      event({
        event_type: "user_edited",
        message: "The user edited the application before approval.",
        payload: {},
      }),
    );

    expect(detail).toBeNull();
  });

  it("keeps an error's own words, where the text is the information", () => {
    const message = "Form changed between review and submission.";

    expect(applicationEventDetail(event({ event_type: "error", message }))).toBe(message);
    expect(
      applicationEventDetail(event({ event_type: "submitted", message, is_error: true })),
    ).toBe(message);
  });

  it("falls back to the message for an event this build does not know", () => {
    // A backend that grows a new event type must not render a blank line.
    const detail = applicationEventDetail(
      event({ event_type: "some_future_event", message: "Something happened." }),
    );

    expect(detail).toBe("Something happened.");
  });
});
