"""Field types the wire contracts share.

One type, because the defect it prevents was found in three domains at
once: `min_length` counts characters, so a title, a name or a question made
entirely of spaces passed every bound the schemas declared. In the worst of
them a message of whitespace queued a research run, titled the thread
"   ", and spent two model calls and the thread's one run slot on nothing
anybody had asked. Found by QA against the live stack, 2026-09-06.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

# Trimmed at the ends; empty after trimming is not a value.
#
# Trimming happens before the length check, so padding cannot smuggle a
# value past a ceiling either. Deliberately not applied to passwords: a
# password may legitimately begin or end with a space, and silently
# trimming one changes the credential the user typed.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
