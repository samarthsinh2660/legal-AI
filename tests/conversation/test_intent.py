"""What a message is, before any model sees it.

Measured 2026-09-01, before this gate existed: "hi" cost 65s, "thanks!" cost
80s and came back with the law on gratuity, and "what can you do?" cost 176s
and answered on the inherent powers of courts under s.151 CPC. The planner
had no way to say "not a legal question", so it invented an angle.
"""

from legal_ai.conversation.intent import Intent, classify, reply_for


def test_a_bare_greeting_is_not_a_legal_question():
    for message in ("hi", "Hi", "hello", "hey", "  hello  ", "hi there",
                    "good morning", "namaste", "hello, are you there?"):
        assert classify(message) is Intent.GREETING, message


def test_thanks_is_not_a_question_about_gratuity():
    for message in ("thanks", "thanks!", "thank you", "thx", "ok thanks",
                    "great, thank you"):
        assert classify(message) is Intent.THANKS, message


def test_asking_what_this_does_is_not_a_question_about_court_powers():
    for message in ("what can you do?", "who are you", "what is this",
                    "how does this work?", "help"):
        assert classify(message) is Intent.CAPABILITY, message


def test_a_legal_question_is_never_swallowed():
    for message in (
        "Can a homebuyer claim a refund for late possession?",
        "What does Section 138 require?",
        # Opens like a greeting and is not one. The gate must read the whole
        # message, not its first word.
        "hi, can I claim a refund for late possession?",
        "hello -- what is the limitation period for recovery of money?",
        "thanks, but what does Section 18 say about interest?",
        # "help" as a word inside a real question.
        "what help can a tenant get against illegal eviction?",
    ):
        assert classify(message) is Intent.LEGAL, message


def test_an_empty_message_is_not_a_greeting():
    for message in ("", "   ", None):
        assert classify(message) is Intent.LEGAL


def test_every_non_legal_intent_has_a_reply():
    for intent in (Intent.GREETING, Intent.THANKS, Intent.CAPABILITY):
        assert reply_for(intent)


def test_a_legal_intent_has_no_canned_reply():
    """It must go to the graph, never to a fixed string."""
    assert reply_for(Intent.LEGAL) is None


def test_the_greeting_reply_invites_a_question_rather_than_disclaiming():
    reply = reply_for(Intent.GREETING)
    assert "legal advice" not in reply.lower()


def test_the_capability_reply_says_what_the_corpus_actually_holds():
    reply = reply_for(Intent.CAPABILITY).lower()
    assert "judgment" in reply or "statute" in reply
    # It must not promise the whole of Indian law.
    assert "not a lawyer" in reply or "not legal advice" in reply
