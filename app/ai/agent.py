"""Generic voice agent: persona + accuracy rules + tools + language guard.
Both sections (Service Center, Dashboard Connect) build an Agent with their own tools."""
import datetime
import json
import re
from dataclasses import dataclass, field
from typing import Callable

from .languages import NAMES, detect_script_language, foreign_script
from .llm import LLM, tool_args


@dataclass
class Tool:
    name: str
    description: str
    params: dict                      # {name: {"type":..., "description":...}}
    fn: Callable[..., dict]
    required: list = field(default_factory=list)

    def schema(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.params, "required": self.required}}}


def calendar_hint(days=8) -> str:
    """Give the model a ready calendar so it never does date maths itself."""
    t = datetime.date.today()
    names = ["today", "tomorrow"] + [""] * days
    rows = [f"{(t + datetime.timedelta(i)).isoformat()} = {(t + datetime.timedelta(i)):%A}"
            + (f" ({names[i]})" if names[i] else "") for i in range(days)]
    return "Calendar: " + "; ".join(rows) + ". Now: " + datetime.datetime.now().strftime("%H:%M") + "."


BASE_RULES = """HOW TO SPEAK
- You are on a LIVE PHONE CALL. Sound like a warm, polite, real human, never robotic.
- Languages: English, Kannada, Hindi, Telugu. Reply in the caller's language, in that language's native
  script. If the caller uses any other language, reply in simple English. If they mix languages
  (Kanglish, Hinglish), mix the same way; English words like phone, order, slot are fine.
- MAXIMUM 2 short sentences (under 30 words) per reply. One question at a time.
  No lists, markdown, emojis or brackets. Say times like "11 to 11:30 in the morning".
- If the caller has a problem or is upset, first say sorry in one short phrase.

ACCURACY RULES (most important)
- Use ONLY the business info, the owner's rules and tool results. Never guess or invent
  prices, dates, times, statuses or promises. Never calculate dates yourself: use the calendar.
- Always check with a tool before answering about bookings, repairs, orders, accounts or KYC.
- Before any action that changes something (booking, cancellation, verification, ticket),
  read the key details back (numbers digit by digit) and act only after the caller says yes.
- Share records only of the caller's own phone number, or an ID they verified. Never read
  out full phone numbers, addresses or payment details.
- If you don't know or a tool fails: apologise, offer a staff callback and create a ticket.
- Angry caller, emergency, or "talk to a human": say a staff member will call back soon
  and create an urgent ticket.
- When the caller is clearly done (bye / thanks), say a short goodbye and call end_call.
- IDs spoken aloud may arrive written in Indian letters or words: e.g. "ಕ್ಯೂಕೆ 1002" or "क्यूके 1002"
  means QK1002, "ಜೆ ಒಂದು ಸಾವಿರದ ಒಂದು" means J1001. Convert them before using a tool.
- Say times the way people do in 12-hour form: "10 in the morning", "2:30 in the afternoon"."""


class Agent:
    def __init__(self, persona: str, tools: list[Tool], caller: str, llm: LLM | None = None,
                 max_rounds: int = 6, turn_rules: str = ""):
        self.turn_rules = turn_rules        # repeated next to every caller message (owner's rules)
        self.tools = {t.name: t for t in tools}
        self.tools["end_call"] = Tool("end_call", "Call only when the caller has clearly finished.",
                                      {}, lambda **_: {"ok": True})
        self.caller = caller
        self.llm = llm or LLM()
        self.max_rounds = max_rounds
        self.persona = persona
        self.messages = [{"role": "system", "content": self._system()}]
        self.actions: list[dict] = []
        self.ended = False

    def _system(self):
        return (f"{self.persona}\n\n{BASE_RULES}\n\nThe caller's phone number is {self.caller} "
                f"(already verified by the phone network; use it for lookups, never ask for it "
                f"or say it aloud).\n{calendar_hint()}")

    def say_first(self, text: str):
        self.messages.append({"role": "assistant", "content": text})

    def _run_tool(self, call) -> str:
        name, args = call["function"]["name"], tool_args(call)
        tool = self.tools.get(name)
        if not tool:
            result = {"error": f"unknown action {name}"}
        else:
            try:
                result = tool.fn(**{k: v for k, v in args.items() if k in tool.params})
            except TypeError as e:
                result = {"error": f"missing details: {e}"}
            except Exception as e:  # a broken system must never crash the call
                result = {"error": f"system problem: {e.__class__.__name__}"}
        if name == "end_call":
            self.ended = True
        else:
            self.actions.append({"tool": name, "args": args, "result": result})
        return json.dumps(result, ensure_ascii=False, default=str)[:4000]

    def reply(self, text: str, lang: str) -> str:
        name = NAMES.get(lang, "English")
        self.messages[0]["content"] = self._system()      # refresh clock each turn
        self.messages.append({"role": "user", "content": text})
        hint = {"role": "system", "content": f"The caller is speaking {name}. Reply in {name}."
                + (f"\nFollow the owner's rules exactly:\n{self.turn_rules}" if self.turn_rules else "")}
        schemas = [t.schema() for t in self.tools.values()]
        msg = {}
        for _ in range(self.max_rounds):
            msg = self.llm.chat(self.messages + [hint], tools=schemas)
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            self.messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                self.messages.append({"role": "tool", "tool_call_id": c["id"], "content": self._run_tool(c)})
        out = (msg.get("content") or "").strip()
        # "Let me check, one moment" without actually checking: make it do the check now, like a person would
        used_tool = any(m.get("role") == "tool" for m in self.messages[self.messages.index(
            next(m for m in reversed(self.messages) if m.get("role") == "user")):])
        if out and not used_tool and STALL.search(out):
            self.messages.append({"role": "assistant", "content": out})
            self.messages.append({"role": "user", "content": "(You said you would check. Use the tool now, then answer.)"})
            for _ in range(3):
                msg = self.llm.chat(self.messages + [hint], tools=schemas)
                calls = msg.get("tool_calls") or []
                if not calls:
                    break
                self.messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
                for c in calls:
                    self.messages.append({"role": "tool", "tool_call_id": c["id"], "content": self._run_tool(c)})
            self.messages = [m for m in self.messages if m.get("content") != "(You said you would check. Use the tool now, then answer.)"
                             and not (m.get("role") == "assistant" and m.get("content") == out and not m.get("tool_calls"))]
            out = (msg.get("content") or out).strip()
        if out and lang != "en" and (detect_script_language(out, lang) != lang or foreign_script(out, lang)):
            fix = self.llm.chat(self.messages + [{"role": "assistant", "content": out},
                                {"role": "user", "content": f"(Say exactly that again in {name}, native script only.)"}])
            out = (fix.get("content") or out).strip()
        out = mask_numbers(out)
        if not out:
            out = {"kn": "ಕ್ಷಮಿಸಿ, ಮತ್ತೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?", "hi": "माफ़ कीजिए, फिर से बोलेंगे?"}.get(
                lang, "Sorry, could you say that again?")
        self.messages.append({"role": "assistant", "content": out})
        return out


STALL = re.compile(r"(let me check|i'?ll check|one moment|checking now|ಚೆಕ್ ಮಾಡ್ತೀನಿ|ನೋಡುತ್ತೇನೆ|ನೋಡ್ತೀನಿ|ಒಂದು ನಿಮಿಷ|"
                   r"చూస్తాను|చెక్ చేస్తాను|ఒక్క నిమిషం|देखती हूँ|देखता हूँ|चेक कर|एक मिनट)", re.I)

_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?\d{5}[\s-]?\d{5}(?!\d)")


def mask_numbers(text: str) -> str:
    """Safety net: never speak a full 10-digit phone number aloud."""
    return _PHONE.sub(lambda m: "******" + re.sub(r"\D", "", m.group(0))[-4:], text)
