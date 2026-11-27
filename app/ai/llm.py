"""Chat brain over OpenAI-compatible APIs with tool calling and automatic fallback.

Primary: Sarvam (sarvam-105b-conversations) - best tested accuracy in Indian languages, ~1 s.
Backup:  NVIDIA (nemotron-3-ultra) - used automatically if the primary fails or is slow.
"""
import json
import os
import time

import requests

PROVIDERS = {
    "sarvam": {"url": "https://api.sarvam.ai/v1/chat/completions",
               "model": "sarvam-105b-conversations",
               "headers": lambda: {"api-subscription-key": os.environ["SARVAM_API_KEY"]}},
    "nvidia": {"url": "https://integrate.api.nvidia.com/v1/chat/completions",
               "model": "nvidia/nemotron-3-ultra-550b-a55b",
               "headers": lambda: {"Authorization": "Bearer " + os.environ["NVIDIA_API_KEY"]},
               "extra": {"chat_template_kwargs": {"enable_thinking": False}}},
}


_DOWN: dict[str, float] = {}


class LLM:
    def __init__(self, order=None, timeout=15, models=None):
        from ..config import llm_order
        self.order = [p for p in (order or llm_order()) if p in PROVIDERS]
        # a provider with no credits left (402) is skipped for 10 minutes instead of being retried every turn
        self.order = [p for p in self.order if time.time() - _DOWN.get(p, 0) > 600] or self.order
        self.timeout = timeout
        self.models = models or {}
        self.last_provider = None

    def chat(self, messages, tools=None, temperature=0.2, max_tokens=400) -> dict:
        errors = []
        for name in self.order:
            p = PROVIDERS[name]
            body = {"model": self.models.get(name, p["model"]), "messages": messages,
                    "temperature": temperature, "max_tokens": max_tokens, **p.get("extra", {})}
            if tools:
                body["tools"] = tools
            try:
                t = time.time()
                for wait in (0, 1.5, 4):  # rate limited (429)? wait and retry the same provider
                    time.sleep(wait)
                    r = requests.post(p["url"], headers=p["headers"](), json=body, timeout=self.timeout)
                    if r.status_code != 429:
                        break
                if r.status_code == 402:
                    _DOWN[name] = time.time()
                r.raise_for_status()
                msg = r.json()["choices"][0]["message"]
                if not msg.get("content") and not msg.get("tool_calls"):
                    raise ValueError("empty reply")
                self.last_provider = f"{name} {time.time() - t:.1f}s"
                return msg
            except Exception as e:  # try next provider
                errors.append(f"{name}: {e.__class__.__name__} {str(e)[:120]}")
        raise RuntimeError("all providers failed: " + " | ".join(errors))


def tool_args(call) -> dict:
    try:
        return json.loads(call["function"].get("arguments") or "{}")
    except ValueError:
        return {}
