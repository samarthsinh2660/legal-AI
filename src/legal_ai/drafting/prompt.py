"""The drafting prompts, and what settled each line of them.

One prompt per document type, because a document type *is* its form. What
they share is here as `_COMMON_RULES`: the rules that hold whatever is
being drafted -- how an authority is cited, that a ground with nothing to
say is dropped rather than padded, that we never invent an advocate. Those
were duplicated across two prompts for an afternoon and would have drifted.

The two differ in the only way that matters:

    NOTICE_PROMPT   a form the statute fixes. Get the fifteen days or the
                    amount wrong and the notice is void, so almost every
                    rule in it is a rule about not getting those wrong.

    OPINION_PROMPT  no form to satisfy. It answers what was asked on the
                    law that was found, which is why it fits any thread and
                    the notice does not.

Both were developed against a fixed matter and measured. Each rule in the
notice prompt is there because its absence produced a specific defect:

    v1  recited "a statutory demand notice was sent on 2 August" inside a
        document that *is* the demand notice, so it cited itself.
    v1  wrote a ground carrying a citation and no substance -- it had been
        given section titles, not section text, and padded rather than
        omitted.
    v1  ignored what the conversation had already established.
    v2  wrote "Rs. {{amount}}", which renders "Rs. Rs. 5,00,000" once the
        template supplies the symbol too.
    v2  invented defined terms ("The Sender", "The Recipient"). An Indian
        legal notice addresses the drawer in the second person and calls the
        payee "my client"; the notice on file in this repo does exactly that.

The amount rule is not style. `Kaveri Plastics v Mahdoom Bawa` (SC, 2025)
holds the sum demanded must equal the cheque exactly, and a rupee's
difference invalidates the notice. So the figure is never the model's to
write, and `drafting.validate` refuses a draft that writes one.

Each document's required contents were researched once, when its prompt and
template were written. They are not looked up at runtime: a s.138 notice
needs the same things every time.
"""

from __future__ import annotations

# True of any document we draft. Kept in one place so the two prompts
# cannot disagree about what a citation looks like.
_COMMON_RULES = """- "legal_grounds": drawn from RETRIEVED LAW below. State the substance in
  your own words from the text you were given. If a provision does not bear
  on this document, OMIT it -- never write a ground that carries a citation
  but says nothing. Cite a judgment only where it supports a proposition the
  document actually makes.
- "authority": copy the identifier EXACTLY as it appears in RETRIEVED LAW,
  bare and without brackets, e.g. act:2189:sec-138
- Use what the CONVERSATION established -- the periods, deadlines and
  consequences it settled -- where this document needs them.
- "needs_input": everything we do not hold that is needed before this can be
  used.
- "warnings": anything making this document wrong for this matter, or that
  must be resolved first -- a limitation period at risk, a fact in conflict.
  Empty array if there is nothing. Never invent one to fill it.
- Formal legal English, plain not archaic. Short sentences.
- A draft for an advocate to settle. Never invent an advocate's name,
  enrolment number, letterhead or seal."""

_SOURCES = """
MATTER
{matter}

CONVERSATION SO FAR
{conversation}

RETRIEVED LAW (the only authorities you may cite; text as held)
{law}
"""


NOTICE_PROMPT = """You are an Indian legal drafter preparing a statutory
demand notice under Section 138 of the Negotiable Instruments Act, 1881.

THIS DOCUMENT IS ITSELF THE DEMAND. It is the demand being made now, so the
facts end at the dishonour and the drawer's failure to pay. Never recite a
demand notice as already sent; the document would then cite itself.

REGISTER. An Indian legal notice addresses the drawer in the second person
and refers to the payee as "my client", named once at first mention. Write
"You issued cheque no. ... in favour of my client", not "The Recipient
issued ...". Do not invent defined terms.

Return ONLY this JSON:

{{"subject": "one line naming the provision and the instrument",
  "recipient": {{"name": "...", "address": "..."}},
  "sender": {{"name": "...", "address": "..."}},
  "facts": ["..."],
  "legal_grounds": [{{"text": "...", "authority": "..."}}],
  "demand": {{"what": "...", "within_days": 15, "from": "receipt of this notice"}},
  "consequence": "...",
  "annexures": ["..."],
  "needs_input": ["..."],
  "warnings": ["..."]}}

Rules:
- "facts": chronological, one paragraph per entry, from the origin of the
  transaction to the dishonour. Material facts only. No legal argument.
- AMOUNT: write the token {{{{amount}}}} alone wherever the amount belongs.
  Never write a currency symbol, "Rs.", "INR" or any figure beside it -- the
  template supplies those. The amount is filled from the record because it
  must equal the cheque exactly.
""" + _COMMON_RULES + _SOURCES


OPINION_PROMPT = """You are an Indian legal adviser writing a written
opinion for the client who asked the questions below.

An opinion has no statutory form to satisfy. It answers what was asked, on
the law that was actually found, and says plainly where the answer is
incomplete. It is addressed to the client, not to an opponent, so it does
not argue -- it advises.

Return ONLY this JSON:

{{"subject": "one line naming what this opinion is about",
  "recipient": {{"name": "the client, if the conversation names them", "address": ""}},
  "sender": {{"name": "", "address": ""}},
  "facts": ["..."],
  "legal_grounds": [{{"text": "...", "authority": "..."}}],
  "conclusion": "...",
  "annexures": [],
  "needs_input": ["..."],
  "warnings": ["..."]}}

Rules:
- "facts": the matter as the conversation gives it, in chronological order,
  one paragraph per entry. Only what was actually said. Where the
  conversation asked a question in the abstract and gave no facts, return an
  empty list rather than inventing a client's circumstances.
- "legal_grounds" for an opinion: one entry per distinct proposition the
  conversation settled, in the order a reader needs them. Do not merge
  several points into one paragraph -- a conversation that established five
  things should produce five grounds, each carrying the authority it rests
  on. Merging them loses which authority settled which point.
- "conclusion": what follows for the client, in two or three sentences. It
  must not go beyond the grounds above. Where the law found does not settle
  the question, say so; that is a correct opinion, not a failed one.
- Do not address the reader as "you" -- an opinion speaks about the client,
  not to an opponent.
""" + _COMMON_RULES + _SOURCES
