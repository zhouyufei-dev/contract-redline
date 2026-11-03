"""Offline tests for the LLM layer. No API key, no network, no tokens spent.

The point: the expensive half of the product must still be testable on a laptop
with the wifi off and the .env deleted. Everything here runs against fakes.

Run:  .\\.venv\\Scripts\\python.exe tools\\test_llm.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as cfg  # noqa: E402
from app.engine.matcher import scan  # noqa: E402
from app.engine.textnorm import prepare  # noqa: E402
from app.llm import deepseek_client as ds  # noqa: E402
from app.llm.guards import ContractFacts, check_card  # noqa: E402
from app.rules.redlines_us import RULES  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED += 1
        print(f"  [FAIL] {name}" + (f"  <- {detail}" if detail else ""))


CLAUSE = (
    "Client shall pay each undisputed invoice within sixty (60) days of the "
    "invoice date."
)

GOOD = {
    "why": "You wait two months to be paid for work you have already finished, "
           "so you are lending the client your time for free.",
    "fix": "Ask for payment within 30 days of the invoice date.",
    "ask": "Could we change the payment window to 30 days from the invoice date?",
    "fallback": "Accept 45 days only if 30% is paid up front.",
    "walk_away": "Nothing up front and terms beyond 60 days.",
}

FACTS = ContractFacts(clause=CLAUSE, rule_id="R01", known_clauses=frozenset({"2.2"}))


def card(**overrides) -> dict:
    out = dict(GOOD)
    out.update(overrides)
    return out


print("\n== guards: the good card passes ==")
check("a clean card passes", check_card(GOOD, FACTS) == [], str(check_card(GOOD, FACTS)))

print("\n== guards: fabricated evidence is caught ==")
bad_quote = card(fix='Ask them to delete the sentence "the client may withhold all payment forever".')
problems = check_card(bad_quote, FACTS)
check("a quote that is not in the clause is rejected",
      any("not in the clause" in p for p in problems), str(problems))

real_quote = card(why='The phrase "within sixty (60) days of the invoice date" is the problem.')
check("a real quote from the clause is accepted",
      check_card(real_quote, FACTS) == [], str(check_card(real_quote, FACTS)))

print("\n== guards: scope and language ==")
check("another rule id is rejected",
      any("another rule" in p for p in check_card(card(why=GOOD["why"] + " See R11."), FACTS)))
check("another section number is rejected",
      any("not in this contract" in p for p in check_card(card(why=GOOD["why"] + " Compare Section 9.4."), FACTS)))
check("its own section number is allowed",
      check_card(card(why=GOOD["why"] + " This is Section 2.2."), FACTS) == [])
check("Chinese characters are rejected",
      any("non-English" in p for p in check_card(card(why=GOOD["why"] + " 这是一份合同。"), FACTS)))
check("'as an AI' is rejected",
      any("AI" in p for p in check_card(card(why="As an AI, " + GOOD["why"]), FACTS)))
check("a statute citation is rejected",
      any("statute" in p for p in check_card(card(fix="Cite 15 U.S.C. 1692 and ask for 30 days."), FACTS)))
check("calling a flagged clause 'standard' is rejected",
      any("safe" in p or "standard" in p
          for p in check_card(card(fix="This payment term is standard practice."), FACTS)))
check("an empty field is rejected",
      any("empty" in p for p in check_card(card(ask=""), FACTS)))
check("an over-long field is rejected",
      any("limit" in p for p in check_card(card(fix="x " * 400), FACTS)))

print("\n== guards: no invented money ==")
money_facts = ContractFacts(
    clause="Client shall pay a fee of $5,000, and a late fee of $100 per day.",
    rule_id="R18",
    known_clauses=frozenset(),
)
money_card = card(
    why="A late fee can eat into the $5,000 fee you quoted for the whole job.",
    fix="Cap the late fee at 10% of the fee.",
)
money_card["ask"] = "Could we cap the late fee at 10% of the $5,000 fee?"
money_card["fallback"] = "Accept $100 per day only for delays you cause."
check("dollar figures that are in the clause are allowed",
      check_card(money_card, money_facts) == [], str(check_card(money_card, money_facts)))

invented = card(why="A two-week slip costs you $7,000, more than a $5,000 job pays.")
invented["ask"] = "Could we cap the fee?"
check("a dollar figure the model worked out itself is rejected",
      any("cites $7000" in p for p in check_card(invented, money_facts)),
      str(check_card(invented, money_facts)))

print("\n== parse_card: model replies are messy ==")
payload = json.dumps(GOOD)
check("plain JSON", ds.parse_card(payload) == GOOD)
check("fenced JSON", ds.parse_card("```json\n" + payload + "\n```") == GOOD)
check("JSON with chatter around it",
      ds.parse_card("Here is the card:\n" + payload + "\nHope that helps.") == GOOD)
try:
    ds.parse_card("I cannot help with that.")
    check("non-JSON raises DeepSeekError", False)
except ds.DeepSeekError:
    check("non-JSON raises DeepSeekError", True)
try:
    ds.parse_card("{not json}")
    check("broken JSON raises DeepSeekError", False)
except ds.DeepSeekError:
    check("broken JSON raises DeepSeekError", True)

print("\n== explain_one: retry, then fall back ==")
text = (Path("data/samples/fake_contract_01.txt")).read_text(encoding="utf-8")
findings = [f for f in scan(prepare(text), RULES) if f.is_reportable]
finding = next(f for f in findings if f.clause == "2.2")

real_chat = ds.chat
real_cache = ds.CACHE_DIR
tmp = Path(tempfile.mkdtemp())
ds.CACHE_DIR = tmp


def fake_chat_sequence(replies):
    queue = list(replies)

    def _fake(messages, **kwargs):
        content = queue.pop(0) if len(queue) > 1 else queue[0]
        return content, {"prompt_tokens": 100, "completion_tokens": 50}

    return _fake


ds.chat = fake_chat_sequence([json.dumps(GOOD)])
card1 = ds.explain_one(finding, use_cache=False)
check("a good first answer is used as-is",
      card1.source == "llm" and card1.attempts == 1 and card1.problems == (),
      f"source={card1.source} attempts={card1.attempts}")

bad = card(why=GOOD["why"] + " 这是中文。")
ds.chat = fake_chat_sequence([json.dumps(bad), json.dumps(GOOD)])
card2 = ds.explain_one(finding, use_cache=False)
check("a rejected answer is retried once and the repair is used",
      card2.source == "llm" and card2.attempts == 2, f"source={card2.source} attempts={card2.attempts}")
check("the repair keeps a record of what was wrong",
      any("non-English" in p for p in card2.problems), str(card2.problems))

ds.chat = fake_chat_sequence([json.dumps(bad)])
card3 = ds.explain_one(finding, use_cache=False)
check("two bad answers fall back to the rule's own text",
      card3.source == "fallback" and len(card3.why) > 30,
      f"source={card3.source} why={card3.why[:40]!r}")
check("the fallback still carries a usable fix", len(card3.fix) > 20)
check("the fallback cost is still counted", card3.prompt_tokens == 200)


def boom(messages, **kwargs):
    raise ds.DeepSeekError("network error: simulated")


ds.chat = boom
card4 = ds.explain_one(finding, use_cache=False)
check("a network failure produces a card, not an exception",
      card4.source == "fallback" and "network error" in " ".join(card4.problems),
      f"{card4.problems}")

print("\n== cache ==")
ds.chat = fake_chat_sequence([json.dumps(GOOD)])
first = ds.explain_one(finding, use_cache=True)
calls = {"n": 0}


def counting_chat(messages, **kwargs):
    calls["n"] += 1
    return json.dumps(GOOD), {"prompt_tokens": 1, "completion_tokens": 1}


ds.chat = counting_chat
second = ds.explain_one(finding, use_cache=True)
check("the second run is served from cache", second.source == "cache")
check("the cache makes zero API calls", calls["n"] == 0, f"calls={calls['n']}")
check("the cached card is identical",
      (first.why, first.fix, first.ask) == (second.why, second.fix, second.ask))

ds.chat = real_chat
ds.CACHE_DIR = real_cache

print("\n== config ==")
env_file = tmp / ".env"
env_file.write_text(
    '# comment\nDEEPSEEK_API_KEY="sk-test-123"\nexport DEEPSEEK_MODEL=\'deepseek-chat\'\n'
    "\nnot_a_pair\nDEEPSEEK_MAX_WORKERS=2\n",
    encoding="utf-8",
)
parsed = cfg.parse_env_file(env_file)
check("quoted values are unwrapped", parsed.get("DEEPSEEK_API_KEY") == "sk-test-123", str(parsed))
check("an 'export ' prefix is tolerated", parsed.get("DEEPSEEK_MODEL") == "deepseek-chat")
check("a line without '=' is skipped", "not_a_pair" not in parsed)
check("a missing file is not an error", cfg.parse_env_file(tmp / "nope.env") == {})

check("endpoint from a bare base url",
      cfg.Settings(api_key="k", base_url="https://api.deepseek.com").endpoint
      == "https://api.deepseek.com/chat/completions")
check("endpoint from a /v1 base url",
      cfg.Settings(api_key="k", base_url="https://api.deepseek.com/v1/").endpoint
      == "https://api.deepseek.com/v1/chat/completions")
check("describe() never prints the key",
      "sk-test-123" not in cfg.Settings(api_key="sk-test-123").describe())
check("describe() reports the key length only",
      "11 chars" in cfg.Settings(api_key="sk-test-123").describe())

print("\n== prompt template ==")
template = ds.load_prompt_template()
check("the prompt file is found", len(template) > 500)
for placeholder in ("{clause}", "{why}", "{fix}", "{rule_id}"):
    check(f"prompt has placeholder {placeholder}", placeholder in template)
messages = ds.build_messages(finding, template)
check("the clause is inserted verbatim", finding.sentence.strip() in messages[1]["content"])
check("the rule's own why is inserted", "You wait" in messages[1]["content"] or len(messages[1]["content"]) > 800)
check("the system message is short and stable", len(messages[0]["content"]) < 200)

print()
if FAILED:
    print(f"RESULT: {FAILED} failed, {PASSED} passed")
    raise SystemExit(1)
print(f"RESULT: all {PASSED} checks passed")
