import json
import logging
import os
from dataclasses import dataclass, field
from typing import Protocol

from helpdesk.tools import NOW, STAFF_CONTACT, TOOL_SCHEMAS, TOOLS

log = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""You are the help desk assistant of CityWheels, a bike rental shop.
The current date and time is {NOW:%A, %Y-%m-%d %H:%M} (Europe/Warsaw, UTC+02:00).

Rules:
- Answer only from what the tools return. Do not use general knowledge about bikes, prices or other shops.
- For questions about prices, opening hours, rules, age limits, payment or cancellations, call search_policies first.
- For anything about a specific booking, call get_booking. Never invent booking details.
- For any refund amount, call calculate_refund and repeat its numbers. Never calculate money yourself.
  If the customer asks about cancelling at another time ("tomorrow", "on Friday"), pass that time as cancel_at.
- You cannot cancel or change bookings, you can only say what the customer would get back.
  Never say a booking has been cancelled. To actually cancel, the customer contacts the staff.
- If a booking is not found, tell the customer and ask them to check the number.
- If the tools do not answer the question, or it is not about CityWheels, say you cannot help with that
  and give the staff contact: {STAFF_CONTACT}.
- Answer briefly, in the language the customer wrote their question in (the user message, not the tool
  results). The documents are in English, so translate what you quote from them. If unsure, use English.
  Amounts in EUR."""

FALLBACK_ANSWER = f"Sorry, I could not answer that. Please contact the staff: {STAFF_CONTACT}."


# Returns the next assistant message as an OpenAI style dict. Tests plug a fake in here.
class Model(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...


# Groq, Gemini and Ollama all speak this API, so switching provider is just env vars.
class OpenAICompatibleModel:
    def __init__(self) -> None:
        from openai import OpenAI

        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY is not set. Copy .env.example to .env and put your key there.")
        self.client = OpenAI(
            api_key=api_key,
            max_retries=5,  # free tiers throttle hard during eval runs
            base_url=os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        )
        self.model = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools, temperature=0)
        return response.choices[0].message.model_dump(exclude_none=True)


@dataclass
class Answer:
    text: str
    tool_calls: list[dict] = field(default_factory=list)  # name, arguments, result; the eval checks these


def run_tool(name: str, raw_arguments: str) -> dict:
    # Errors go back as a tool result. The model can recover from that, not from a crash.
    if name not in TOOLS:
        return {"error": f"Unknown tool {name!r}."}
    try:
        arguments = json.loads(raw_arguments or "{}")
        return TOOLS[name](**arguments)
    except Exception as error:
        log.exception("Tool %s failed with arguments %s", name, raw_arguments)
        return {"error": f"Tool {name} failed: {error}"}


class Agent:
    def __init__(self, model: Model, max_steps: int = 6) -> None:
        self.model = model
        self.max_steps = max_steps
        # History survives between ask() calls, that is all follow-up questions need.
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def ask(self, question: str) -> Answer:
        self.messages.append({"role": "user", "content": question})
        calls: list[dict] = []
        for _ in range(self.max_steps):
            message = self.model.complete(self.messages, TOOL_SCHEMAS)
            self.messages.append(message)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return Answer(message.get("content") or FALLBACK_ANSWER, calls)
            for call in tool_calls:
                name = call["function"]["name"]
                arguments = call["function"].get("arguments", "{}")
                result = run_tool(name, arguments)
                log.info("tool %s(%s) -> %s", name, arguments, result)
                calls.append({"name": name, "arguments": arguments, "result": result})
                self.messages.append(
                    {"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result)}
                )
        log.warning("Gave up after %d steps", self.max_steps)
        return Answer(FALLBACK_ANSWER, calls)
