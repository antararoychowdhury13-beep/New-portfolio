"""A1 · UI Perception — the live implementation.

Turns a screenshot into a validated ``ScreenPerception`` (the ONLY screen
information downstream synthetic users ever receive) by calling a hosted
vision-language model through Hugging Face Inference Providers.

Activation: set ``SYNTHUX_HF_TOKEN`` (or ``HF_TOKEN``) in the environment.
Without a token the module imports fine and everything is testable with an
injected fake client; only a real call raises a clear setup error.

Smoke test from the command line once a token is set:

    cd synthux/backend
    python -m synthux.perception tests/fixtures/payment_methods.png
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from .models import ScreenPerception

DEFAULT_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "01_ui_perception.md"
TOKEN_ENV_VARS = ("SYNTHUX_HF_TOKEN", "HF_TOKEN")


class PerceptionError(RuntimeError):
    """Raised when the perception layer cannot produce a valid result."""


def load_system_prompt() -> str:
    """The agent's contract lives in prompts/01_ui_perception.md — one source
    of truth for both documentation and runtime."""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    raise PerceptionError(f"Perception prompt not found at {PROMPT_PATH}")


def image_to_data_uri(image_path: str | Path) -> str:
    path = Path(image_path)
    if not path.exists():
        raise PerceptionError(f"Screenshot not found: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_json(text: str) -> dict:
    """Models wrap JSON in prose or ``` fences; recover the object anyway."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise PerceptionError(f"No JSON object in model output: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def _response_text(response) -> str:
    """Tolerate both huggingface_hub dataclasses and plain-dict fakes."""
    choices = response["choices"] if isinstance(response, dict) else response.choices
    choice = choices[0]
    message = choice["message"] if isinstance(choice, dict) else choice.message
    return message["content"] if isinstance(message, dict) else message.content


class PerceptionAgent:
    """One perceive() call = one screenshot in, one ScreenPerception out.

    ``client`` is any object with a ``chat_completion(messages=..., ...)``
    method (huggingface_hub.InferenceClient in production, a fake in tests).
    """

    def __init__(self, client=None, model: str = DEFAULT_MODEL, max_retries: int = 1):
        self._client = client
        self.model = model
        self.max_retries = max_retries

    def _client_or_raise(self):
        if self._client is not None:
            return self._client
        token = next((os.environ[v] for v in TOKEN_ENV_VARS if os.environ.get(v)), None)
        if not token:
            raise PerceptionError(
                "No Hugging Face token found. Set SYNTHUX_HF_TOKEN (or HF_TOKEN) "
                "to your 'hf_...' access token from huggingface.co/settings/tokens. "
                "This is Step 2 of the SynthUX setup."
            )
        from huggingface_hub import InferenceClient

        self._client = InferenceClient(model=self.model, token=token)
        return self._client

    def perceive(
        self,
        image_path: str | Path,
        screen_id: str,
        accessibility: tuple[str, ...] = (),
    ) -> ScreenPerception:
        client = self._client_or_raise()
        data_uri = image_to_data_uri(image_path)

        instruction = (
            f"Screen id: {screen_id}. Describe this viewport per your rules "
            f"and return the JSON object only."
        )
        if accessibility:
            instruction += (
                " Apply this accessibility degradation profile before reporting: "
                + ", ".join(accessibility)
                + "."
            )

        messages = [
            {"role": "system", "content": load_system_prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": instruction},
                ],
            },
        ]

        last_error = None
        for _ in range(self.max_retries + 1):
            response = client.chat_completion(
                messages=messages, max_tokens=3000, temperature=0.1
            )
            text = _response_text(response)
            try:
                data = extract_json(text)
                data.setdefault("screen_id", screen_id)
                return ScreenPerception.model_validate(data)
            except (PerceptionError, ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                # One corrective round-trip: show the model its own output and
                # the validation failure, ask for the corrected JSON only.
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            "Your output failed validation with this error:\n"
                            f"{exc}\n"
                            "Return ONLY the corrected JSON object."
                        ),
                    },
                ]
        raise PerceptionError(f"Model output failed validation after retry: {last_error}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m synthux.perception",
        description="Run the UI Perception agent on one screenshot and print the ScreenPerception JSON.",
    )
    parser.add_argument("image", help="Path to a screenshot (png/jpg)")
    parser.add_argument("--screen-id", default=None, help="Screen id (defaults to the file stem)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--accessibility", default="",
        help="Comma-separated degradation profile, e.g. low_vision,colour_vision_deficiency",
    )
    args = parser.parse_args(argv)

    screen_id = args.screen_id or Path(args.image).stem
    accessibility = tuple(a.strip() for a in args.accessibility.split(",") if a.strip())
    agent = PerceptionAgent(model=args.model)
    try:
        perception = agent.perceive(args.image, screen_id, accessibility)
    except PerceptionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(perception.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
