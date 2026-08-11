"""Tests for the perception layer — all offline, via an injected fake client."""
import json
from pathlib import Path

import pytest

from synthux.models import ScreenPerception
from synthux.perception import (
    PerceptionAgent,
    PerceptionError,
    extract_json,
    image_to_data_uri,
    load_system_prompt,
)

FIXTURE_PNG = Path(__file__).parent / "fixtures" / "payment_methods.png"

VALID_PERCEPTION = {
    "screen_id": "payment_methods",
    "screen_summary": "A billing screen showing the active payment card and payment options.",
    "elements": [
        {"label": "Manage mandate", "kind": "row", "region": "center",
         "bbox": [16, 300, 358, 62], "prominence": 0.45, "affordance_clarity": 0.5},
        {"label": "Pay current bill • ₹12,640", "kind": "button", "region": "bottom-center",
         "bbox": [16, 560, 358, 48], "prominence": 0.9, "affordance_clarity": 0.9},
    ],
    "scroll_hint": False,
}


class FakeClient:
    """Duck-typed stand-in for huggingface_hub.InferenceClient."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat_completion(self, messages, **kwargs):
        self.calls.append(messages)
        text = self.responses.pop(0)
        return {"choices": [{"message": {"content": text}}]}


def test_prompt_file_is_the_source_of_truth():
    prompt = load_system_prompt()
    assert "perception layer" in prompt
    assert "viewport" in prompt


def test_image_to_data_uri_roundtrip():
    uri = image_to_data_uri(FIXTURE_PNG)
    assert uri.startswith("data:image/png;base64,")


def test_extract_json_strips_fences_and_prose():
    wrapped = "Here is the analysis:\n```json\n" + json.dumps(VALID_PERCEPTION) + "\n```\nDone."
    assert extract_json(wrapped)["screen_id"] == "payment_methods"


def test_perceive_happy_path():
    client = FakeClient(["```json\n" + json.dumps(VALID_PERCEPTION) + "\n```"])
    agent = PerceptionAgent(client=client)
    p = agent.perceive(FIXTURE_PNG, "payment_methods")
    assert isinstance(p, ScreenPerception)
    assert any(e.label == "Manage mandate" for e in p.elements)
    # The screenshot went to the model as a data URI.
    user_content = client.calls[0][1]["content"]
    assert user_content[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_perceive_retries_once_with_error_feedback():
    client = FakeClient(["not json at all", json.dumps(VALID_PERCEPTION)])
    agent = PerceptionAgent(client=client)
    p = agent.perceive(FIXTURE_PNG, "payment_methods")
    assert p.screen_id == "payment_methods"
    assert len(client.calls) == 2
    # The retry conversation contains the failed output and a correction ask.
    retry_messages = client.calls[1]
    assert retry_messages[-2]["content"] == "not json at all"
    assert "failed validation" in retry_messages[-1]["content"]


def test_perceive_gives_up_after_retries():
    client = FakeClient(["garbage", "still garbage"])
    agent = PerceptionAgent(client=client)
    with pytest.raises(PerceptionError, match="after retry"):
        agent.perceive(FIXTURE_PNG, "payment_methods")


def test_accessibility_profile_reaches_the_model():
    client = FakeClient([json.dumps(VALID_PERCEPTION)])
    agent = PerceptionAgent(client=client)
    agent.perceive(FIXTURE_PNG, "payment_methods",
                   accessibility=("low_vision", "colour_vision_deficiency"))
    instruction = client.calls[0][1]["content"][1]["text"]
    assert "low_vision" in instruction and "colour_vision_deficiency" in instruction


def test_missing_token_produces_setup_guidance(monkeypatch):
    monkeypatch.delenv("SYNTHUX_HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    agent = PerceptionAgent()  # no injected client → needs a real token
    with pytest.raises(PerceptionError, match="SYNTHUX_HF_TOKEN"):
        agent.perceive(FIXTURE_PNG, "payment_methods")
