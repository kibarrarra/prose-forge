import os
import httpx
from types import SimpleNamespace
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

# Attempt to import Anthropic SDK – if unavailable, we degrade gracefully.
try:
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover – Anthropic support optional
    anthropic = None


def _flatten_anthropic_content(content_blocks):
    """Anthropic returns a list of blocks; join them into a single string."""
    text_parts = []
    for block in content_blocks:
        # SDK ≤0.25: each block is an object with `.text`
        if hasattr(block, "text"):
            text_parts.append(block.text)
        # Future‐proof: plain strings or dict-like objects
        elif isinstance(block, str):
            text_parts.append(block)
        else:
            text_parts.append(str(block))
    return "".join(text_parts)


class _AnthropicResponseAdapter:  # pylint: disable=too-few-public-methods
    """Wrap an Anthropic response so it mimics OpenAI's return structure."""

    def __init__(self, response):
        # Match the minimal interface we rely on: `choices[0].message.content`.
        content = _flatten_anthropic_content(response.content)
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


class UnifiedClient:
    """A drop-in replacement for `openai.OpenAI` that also supports Anthropic.

    If the *model* argument passed to `chat.completions.create()` begins with
    "claude" we route the request to Anthropic's API.  Otherwise, we fall back
    to OpenAI.  The returned object always exposes the OpenAI-style structure
    (with `.choices[0].message.content`) so existing call-sites keep working.
    """

    def __init__(self, timeout: httpx.Timeout | None = None):
        self._openai = OpenAI(timeout=timeout)

        self._anthropic = None
        if anthropic is not None and os.getenv("ANTHROPIC_API_KEY"):
            self._anthropic = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout=timeout,
            )

        # Build a namespace hierarchy so that callers can do
        #   client.chat.completions.create(...)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat_create))

    # ---------------------------------------------------------------------
    # Internal dispatch method
    # ---------------------------------------------------------------------
    def _chat_create(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ):
        # → Anthropic
        if model.startswith("claude"):
            if self._anthropic is None:
                raise RuntimeError(
                    "Anthropic not configured.  Please `pip install anthropic` and set ANTHROPIC_API_KEY."
                )

            # Separate system prompt from messages for Anthropic API
            system_prompt = None
            user_assistant_messages = []
            if messages and messages[0]["role"] == "system":
                system_prompt = messages[0]["content"]
                user_assistant_messages = messages[1:] # Assumes user msg follows system
            else:
                user_assistant_messages = messages # No system prompt found

            response = self._anthropic.messages.create(
                model=model,
                system=system_prompt, # Pass system prompt separately
                messages=user_assistant_messages, # Pass only user/assistant messages
                temperature=temperature,
                max_tokens=max_tokens,
                **{k: v for k, v in kwargs.items() if v is not None},
            )
            return _AnthropicResponseAdapter(response)

        # → OpenAI (default)
        return self._openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )


def get_llm_client():
    """Return a *UnifiedClient* that transparently supports OpenAI & Anthropic."""

    timeout = httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=60.0)
    return UnifiedClient(timeout=timeout) 