"""Thin wrapper around the DeepSeek API (OpenAI-compatible endpoint).

Non-negotiable rules:
  - The API key comes from app.config, which reads .env. Never hardcoded,
    never printed, never logged, never put in an exception message.
  - Input is ALWAYS: the one matched sentence + that rule's "why"/"fix" anchors.
  - Output is explanation prose only. The model may not add findings, may not
    see the rest of the contract, and its text is never used to decide whether
    a risk exists.
  - Every response is checked by app/llm/guards.py. A rejected response is
    retried once, then replaced by the rule's own hand-written text. The report
    always renders.

Why urllib and not the openai SDK: this is one POST with a JSON body. urllib is
in the standard library, so there is nothing to install (or break) on a
beginner's machine, and we control the retry behaviour ourselves.

Cost control:
  - one call per finding (not one call for the whole contract), so a failure is
    local and the prompt stays short;
  - results are cached on disk by (model, prompt version, rule, clause), so
    re-running the same contract costs nothing;
  - `max_workers` bounds concurrency so a 24-finding contract takes seconds.
"""

from __future__ import annotations

import hashlib
import json
import random
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from app.config import PROJECT_ROOT, ConfigError, Settings, get_settings
from app.engine.matcher import Finding
from app.llm.guards import ContractFacts, check_card, repair_instruction

PROMPT_FILE = PROJECT_ROOT / "prompts" / "card_en.md"
CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "llm"

# Bump when the prompt or the guardrails change, so stale cached cards are not
# reused after a behaviour change.
PROMPT_VERSION = "card-v1"

MAX_TOKENS = 700


class DeepSeekError(RuntimeError):
    """Any failure talking to the API. Never contains the API key."""


class DeepSeekAuthError(DeepSeekError):
    """The key was rejected. Retrying cannot help."""


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------

def load_prompt_template() -> str:
    """Read the prompt body from prompts/card_en.md (everything after the ---)."""
    raw = PROMPT_FILE.read_text(encoding="utf-8")
    marker = "\n---\n"
    body = raw.split(marker, 1)[1] if marker in raw else raw
    return body.strip()


def build_messages(finding: Finding, template: str | None = None) -> list[dict]:
    template = template or load_prompt_template()
    user = (
        template.replace("{rule_id}", finding.rule_id)
        .replace("{rule_name}", finding.rule_name)
        .replace("{severity}", str(finding.severity))
        .replace("{clause}", finding.sentence.strip())
        .replace("{why}", _rule_text(finding, "why"))
        .replace("{fix}", _rule_text(finding, "fix"))
    )
    return [
        {
            "role": "system",
            "content": (
                "You write short, concrete contract warnings for US freelancers. "
                "You answer with a single JSON object and nothing else."
            ),
        },
        {"role": "user", "content": user},
    ]


def _rule_text(finding: Finding, attr: str) -> str:
    from app.rules.redlines_us import RULES

    for rule in RULES:
        if rule.id == finding.rule_id:
            return getattr(rule, attr, "") or ""
    return ""


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------

RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _post(url: str, payload: dict, settings: Settings) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # 4xx / 5xx
        detail = _snippet(exc)
        if exc.code in (401, 403):
            raise DeepSeekAuthError(
                f"DeepSeek rejected the API key (HTTP {exc.code}). "
                "Check DEEPSEEK_API_KEY in .env."
            ) from None
        raise DeepSeekError(f"HTTP {exc.code} from DeepSeek: {detail}") from None
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise DeepSeekError(f"network error: {reason}") from None
    except json.JSONDecodeError:
        raise DeepSeekError("DeepSeek returned a body that is not JSON") from None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise DeepSeekError(f"DeepSeek returned a non-JSON body: {_head(raw)}") from None


def _snippet(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - body already consumed
        return "<no body>"
    return _head(body)


def _head(text: str, limit: int = 300) -> str:
    return " ".join(text.split())[:limit]


def chat(
    messages: Sequence[dict],
    *,
    settings: Settings | None = None,
    json_mode: bool = True,
    max_tokens: int = MAX_TOKENS,
) -> tuple[str, dict]:
    """One request, with retries on transient errors. Returns (content, usage)."""
    settings = settings or get_settings()
    payload: dict = {
        "model": settings.model,
        "messages": list(messages),
        "temperature": settings.temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_error: Exception | None = None
    for attempt in range(settings.max_retries + 1):
        try:
            body = _post(settings.endpoint, payload, settings)
            choices = body.get("choices") or []
            if not choices:
                raise DeepSeekError(f"no choices in response: {_head(json.dumps(body))}")
            content = (choices[0].get("message") or {}).get("content") or ""
            usage = body.get("usage") or {}
            return content, usage
        except DeepSeekAuthError:
            raise
        except DeepSeekError as exc:
            last_error = exc
            message = str(exc)
            transient = (
                "network error" in message
                or any(f"HTTP {code} " in message for code in RETRY_STATUS)
            )
            if not transient or attempt == settings.max_retries:
                raise
            # Exponential backoff with jitter: 0.8s, 1.6s, 3.2s (+ noise).
            delay = (0.8 * (2 ** attempt)) + random.uniform(0.0, 0.4)
            time.sleep(delay)

    raise last_error or DeepSeekError("unknown failure")


# --------------------------------------------------------------------------
# Card parsing
# --------------------------------------------------------------------------

CARD_FIELDS = ("why", "fix", "ask", "fallback", "walk_away")


@dataclass
class Card:
    rule_id: str
    clause: str
    why: str
    fix: str
    ask: str = ""
    fallback: str = ""
    walk_away: str = ""
    source: str = "llm"          # "llm" | "cache" | "fallback"
    attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed: float = 0.0
    problems: tuple[str, ...] = ()

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def parse_card(content: str) -> dict:
    """Pull the JSON object out of a model reply, fences and chatter included."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise DeepSeekError(f"model did not return JSON: {_head(content, 160)}")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DeepSeekError(f"model returned invalid JSON ({exc.msg})") from None
    if not isinstance(data, dict):
        raise DeepSeekError("model returned JSON that is not an object")
    return data


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def _cache_key(model: str, finding: Finding) -> str:
    basis = "|".join(
        [PROMPT_VERSION, model, finding.rule_id, finding.sentence.strip()]
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def _cache_read(path: Path) -> Card | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        card = Card(**data)
        card.source = "cache"
        card.elapsed = 0.0
        return card
    except Exception:
        return None


def _cache_write(path: Path, card: Card) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in card.__dict__.items() if k != "elapsed"}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_cache() -> int:
    if not CACHE_DIR.exists():
        return 0
    removed = 0
    for path in CACHE_DIR.glob("*.json"):
        path.unlink()
        removed += 1
    return removed


# --------------------------------------------------------------------------
# One finding
# --------------------------------------------------------------------------

def explain_one(
    finding: Finding,
    *,
    settings: Settings | None = None,
    use_cache: bool = True,
    template: str | None = None,
) -> Card:
    """Explain a single finding. Never raises: falls back to the rule's own text."""
    settings = settings or get_settings()
    cache_path = CACHE_DIR / f"{_cache_key(settings.model, finding)}.json"

    if use_cache:
        cached = _cache_read(cache_path)
        if cached is not None:
            return cached

    facts = ContractFacts(
        clause=finding.sentence,
        rule_id=finding.rule_id,
        known_clauses=frozenset({finding.clause} if finding.clause else set()),
    )

    messages = build_messages(finding, template)
    prompt_tokens = completion_tokens = 0
    problems: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    started = time.perf_counter()

    for attempt in (1, 2):
        try:
            content, usage = chat(messages, settings=settings)
        except DeepSeekError as exc:
            return _fallback_card(finding, (str(exc),), started, prompt_tokens, completion_tokens, attempt)

        prompt_tokens += int(usage.get("prompt_tokens") or 0)
        completion_tokens += int(usage.get("completion_tokens") or 0)

        try:
            data = parse_card(content)
        except DeepSeekError as exc:
            problems = (str(exc),)
            rejected = problems
            messages = messages[:2] + [{"role": "assistant", "content": content},
                                       {"role": "user", "content": repair_instruction(list(problems))}]
            continue

        problems = tuple(check_card(data, facts))
        if not problems:
            card = Card(
                rule_id=finding.rule_id,
                clause=finding.sentence,
                why=data["why"].strip(),
                fix=data["fix"].strip(),
                ask=data.get("ask", "").strip(),
                fallback=data.get("fallback", "").strip(),
                walk_away=data.get("walk_away", "").strip(),
                source="llm",
                attempts=attempt,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                elapsed=time.perf_counter() - started,
                # What the first attempt got wrong, kept for the QA log.
                problems=rejected,
            )
            if use_cache:
                _cache_write(cache_path, card)
            return card

        rejected = problems
        messages = messages[:2] + [{"role": "assistant", "content": content},
                                   {"role": "user", "content": repair_instruction(list(problems))}]

    return _fallback_card(finding, problems, started, prompt_tokens, completion_tokens, 2)


def _fallback_card(
    finding: Finding,
    problems: tuple[str, ...],
    started: float,
    prompt_tokens: int,
    completion_tokens: int,
    attempts: int,
) -> Card:
    return Card(
        rule_id=finding.rule_id,
        clause=finding.sentence,
        why=_rule_text(finding, "why"),
        fix=_rule_text(finding, "fix"),
        source="fallback",
        attempts=attempts,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        elapsed=time.perf_counter() - started,
        problems=problems,
    )


# --------------------------------------------------------------------------
# A whole contract
# --------------------------------------------------------------------------

@dataclass
class RunStats:
    findings: int = 0
    api_calls: int = 0
    cached: int = 0
    fallbacks: int = 0
    repaired: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_saved_estimate: int = 0
    wall_seconds: float = 0.0
    slowest: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def tokens_per_finding(self) -> float:
        return self.total_tokens / self.findings if self.findings else 0.0

    def add(self, card: Card) -> None:
        self.findings += 1
        if card.source == "cache":
            # A cached card cost nothing in THIS run. Its tokens were billed
            # the first time round, so counting them again would overstate the
            # bill and make the summary useless.
            self.cached += 1
            self.tokens_saved_estimate += card.total_tokens
        else:
            self.api_calls += card.attempts
            self.prompt_tokens += card.prompt_tokens
            self.completion_tokens += card.completion_tokens
            self.slowest = max(self.slowest, card.elapsed)
            if card.attempts > 1:
                self.repaired += 1
                for p in card.problems:
                    self.problems.append(f"{card.rule_id}: repaired - {p}")
            if card.source == "fallback":
                self.fallbacks += 1
                for p in card.problems:
                    self.problems.append(f"{card.rule_id}: fell back - {p}")


def enrich(
    findings: Iterable[Finding],
    *,
    settings: Settings | None = None,
    use_cache: bool = True,
    progress=None,
) -> tuple[list[Card], RunStats]:
    """Explain every finding, in order, with bounded concurrency."""
    settings = settings or get_settings()
    if not settings.api_key:
        raise ConfigError(
            "DEEPSEEK_API_KEY is not set — cannot explain findings. "
            "The rule engine still works without it."
        )

    items = [f for f in findings if f.is_reportable]
    template = load_prompt_template()
    stats = RunStats()
    started = time.perf_counter()

    def work(finding: Finding) -> Card:
        card = explain_one(
            finding, settings=settings, use_cache=use_cache, template=template
        )
        if progress is not None:
            progress(finding, card)
        return card

    workers = max(1, min(settings.max_workers, len(items) or 1))
    if workers == 1:
        cards = [work(f) for f in items]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            cards = list(pool.map(work, items))

    for card in cards:
        stats.add(card)
    stats.wall_seconds = time.perf_counter() - started
    return cards, stats
