"""One function to call any agent: system = shared context + role prompt, user = JSON inputs."""
import json
import re
import time

from . import config

COST = {"usd": 0.0, "calls": []}
MOCK = None          # tests set this to a function(agent, system, user) -> str


class BudgetExceeded(RuntimeError):
    pass


def render_shared(ctx):
    txt = (config.PROMPTS / "00_shared.md").read_text(encoding="utf-8")
    for k, v in ctx.items():
        txt = txt.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return txt


def _tools(spec):
    tools = []
    for name, uses in (spec or {}).items():
        if name == "web_search":
            tools.append({"type": "web_search_20250305", "name": "web_search", "max_uses": uses,
                          "user_location": {"type": "approximate", "country": "IN",
                                            "city": "Mumbai", "timezone": "Asia/Kolkata"}})
        elif name == "web_fetch":
            tools.append({"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": uses,
                          "max_content_tokens": 12000})
    return tools


def _account(agent, model, usage):
    pin, pout = config.PRICES.get(model, (4.0, 20.0))
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cache_w = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_r = getattr(usage, "cache_read_input_tokens", 0) or 0
    stu = getattr(usage, "server_tool_use", None)
    searches = (getattr(stu, "web_search_requests", 0) or 0) if stu else 0
    usd = (inp * pin + out * pout + cache_w * pin * 1.25 + cache_r * pin * 0.1) / 1e6 + searches * config.WEB_SEARCH_USD
    COST["usd"] += usd
    COST["calls"].append({"agent": agent, "model": model, "in": inp + cache_w + cache_r, "out": out,
                          "searches": searches, "usd": round(usd, 4)})
    if COST["usd"] > config.MAX_RUN_USD:
        raise BudgetExceeded(f"Run cost ${COST['usd']:.2f} passed the ${config.MAX_RUN_USD} cap")


def call(agent, role_prompt_file, user_payload, shared_ctx, *, tools=None, max_tokens=8000,
         expect_json=True, temperature=None):
    """Run one agent. Returns parsed JSON (expect_json) or text."""
    system = render_shared(shared_ctx) + "\n\n" + (config.PROMPTS / role_prompt_file).read_text(encoding="utf-8")
    user = user_payload if isinstance(user_payload, str) else json.dumps(user_payload, ensure_ascii=False, indent=1)
    model = config.MODELS[agent]

    if MOCK is not None:
        text = MOCK(agent, system, user)
    else:
        text = _call_api(agent, model, system, user, tools, max_tokens, temperature)

    if not expect_json:
        return text
    try:
        return parse_json(text)
    except ValueError:
        if MOCK is not None:
            raise
        fix = _call_api(agent, model, system,
                        user + "\n\nYour previous reply was not valid JSON. Reply again with the JSON object only.\n"
                        "Previous reply:\n" + text[:20000], None, max_tokens, temperature)
        return parse_json(fix)


def _call_api(agent, model, system, user, tools, max_tokens, temperature):
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=4, timeout=600)
    messages = [{"role": "user", "content": user}]
    kwargs = dict(model=model, max_tokens=max_tokens,
                  system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}])
    if tools:
        kwargs["tools"] = _tools(tools)
    if temperature is not None:
        kwargs["temperature"] = temperature
    blocks = []
    for _ in range(12):                       # server tools may pause a long turn; continue it
        for attempt in range(4):
            try:
                resp = client.messages.create(messages=messages, **kwargs)
                break
            except anthropic.APIStatusError as e:
                if e.status_code in (429, 500, 502, 503, 529) and attempt < 3:
                    time.sleep(20 * (attempt + 1))
                    continue
                raise
        _account(agent, model, resp.usage)
        blocks.extend(resp.content)
        if resp.stop_reason == "pause_turn":
            messages = [{"role": "user", "content": user}, {"role": "assistant", "content": list(blocks)}]
            continue
        if resp.stop_reason == "max_tokens":
            raise RuntimeError(f"{agent}: reply hit max_tokens={max_tokens}")
        break
    # The answer is the text written after the last tool result (citations can split it into many blocks).
    last_tool = max([i for i, b in enumerate(blocks) if getattr(b, "type", "").endswith("tool_result")], default=-1)
    return "".join(b.text for b in blocks[last_tool + 1:] if getattr(b, "type", "") == "text")


def parse_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON found")
    s = min(starts)
    end_char = "}" if t[s] == "{" else "]"
    e = t.rfind(end_char)
    try:
        return json.loads(t[s:e + 1])
    except json.JSONDecodeError as ex:
        raise ValueError(str(ex))


def summary():
    by = {}
    for c in COST["calls"]:
        by.setdefault(c["agent"], 0.0)
        by[c["agent"]] += c["usd"]
    return {"total_usd": round(COST["usd"], 3), "by_agent": {k: round(v, 3) for k, v in by.items()},
            "calls": len(COST["calls"])}
