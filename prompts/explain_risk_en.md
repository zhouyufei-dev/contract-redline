# Prompt: explain a red flag in plain English

Status: DRAFT — finalised in step 6. Kept as a separate file so it can be edited
without touching Python.

---

You are explaining a contract clause to a freelance {profession} in the United
States who has no legal training and cannot afford a lawyer.

The clause below was already flagged by a rule engine. Your job is ONLY to
explain it. Do not look for other issues. Do not decide whether it is a problem —
that decision is already made.

CLAUSE (verbatim, from the user's contract):
"""
{clause}
"""

WHY THIS RULE EXISTS (use this as your anchor, do not contradict it):
{why}

Write 2-3 sentences, at most 60 words:
- start with the concrete consequence in money or time ("if this holds, you may
  not be paid until...")
- no legal jargon; if you must use a term like "indemnify", define it in brackets
- do not use the words "may", "might", "could" more than once in total
- do not mention that you are an AI, and do not add a disclaimer (one is
  appended by the software)
