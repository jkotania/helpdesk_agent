import json

from helpdesk.agent import FALLBACK_ANSWER, Agent


def tool_call(name: str, call_id: str = "call_1", **arguments) -> dict:
    return {
        "role": "assistant",
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        ],
    }


def reply(text: str) -> dict:
    return {"role": "assistant", "content": text}


class FakeModel:
    # Replays canned responses and records every message list it was given.

    def __init__(self, *responses: dict) -> None:
        self.responses = list(responses)
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools):
        self.seen.append(list(messages))
        return self.responses.pop(0)


def test_agent_runs_tool_and_feeds_result_back():
    model = FakeModel(tool_call("calculate_refund", booking_id="CW-1002"), reply("You get 340.00 EUR back."))
    answer = Agent(model).ask("I want to cancel CW-1002. How much will I get back?")

    assert answer.text == "You get 340.00 EUR back."
    assert [call["name"] for call in answer.tool_calls] == ["calculate_refund"]
    assert answer.tool_calls[0]["result"]["total_refund_eur"] == 340.0
    # second call has to see our number, not one the model came up with
    tool_message = model.seen[1][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_1"
    assert json.loads(tool_message["content"])["total_refund_eur"] == 340.0


def test_unknown_booking_does_not_crash():
    model = FakeModel(tool_call("get_booking", booking_id="CW-404"), reply("Booking not found."))
    answer = Agent(model).ask("Where is my booking CW-404?")
    assert answer.tool_calls[0]["result"]["found"] is False


def test_bad_tool_name_and_arguments_go_back_as_errors():
    model = FakeModel(
        tool_call("delete_everything"),
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "c2", "type": "function", "function": {"name": "get_booking", "arguments": "{not json"}}
            ],
        },
        tool_call("get_booking", call_id="c3", wrong_argument="x"),
        reply("Sorry."),
    )
    answer = Agent(model).ask("hi")
    assert answer.text == "Sorry."
    assert all("error" in call["result"] for call in answer.tool_calls)


def test_agent_stops_after_max_steps():
    model = FakeModel(*[tool_call("search_policies", query="x") for _ in range(3)])
    answer = Agent(model, max_steps=3).ask("loop forever")
    assert answer.text == FALLBACK_ANSWER
    assert len(answer.tool_calls) == 3


def test_conversation_is_kept_between_questions():
    model = FakeModel(reply("First."), reply("Second."))
    agent = Agent(model)
    agent.ask("Cancel CW-1001?")
    agent.ask("And tomorrow?")
    contents = [m.get("content") for m in model.seen[1]]
    assert "Cancel CW-1001?" in contents and "First." in contents
