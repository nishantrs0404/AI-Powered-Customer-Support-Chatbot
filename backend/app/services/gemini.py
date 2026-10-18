
import os
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types


# Load .env from the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = "gemini-3.5-flash-lite"


def _get_client() -> genai.Client:
    """Create and return a Gemini client using the configured API key."""
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from the .env file."
        )

    return genai.Client(api_key=api_key)


def _call_gemini(
    contents: list,
    system_instruction: Optional[str] = None,
) -> str:
    """
    Call the Gemini API with the given contents and optional system prompt.

    Retries on transient server errors (429, 500, 502, 503, 504) up to 3
    attempts with exponential back-off.  Raises RuntimeError on failure.
    """
    client = _get_client()

    config = None
    if system_instruction:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
        )

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=config,
            )

            reply = response.text

            if not reply or not reply.strip():
                raise RuntimeError("Gemini returned an empty response.")

            return reply.strip()

        except errors.APIError as exc:
            # Retry temporary server errors and rate limits.
            if exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(
                    f"Gemini API error: HTTP {exc.code}"
                ) from exc

            if attempt == 2:
                raise RuntimeError(
                    f"Gemini is temporarily unavailable: HTTP {exc.code}"
                ) from exc

            time.sleep(2 ** (attempt + 1))

        except RuntimeError:
            raise

        except Exception as exc:
            raise RuntimeError(
                "Gemini could not generate a response."
            ) from exc

    raise RuntimeError("Gemini request failed.")


def generate_reply(message: str) -> str:
    """Generate a customer-support response using Gemini (no history)."""
    return _call_gemini(contents=message)


def generate_context_aware_reply(
    message: str,
    history: list[dict],
    system_prompt: str,
) -> str:
    """
    Generate a context-aware customer-support response using Gemini.

    Parameters
    ----------
    message:
        The current customer message (plain text).
    history:
        A list of previous messages in chronological order.  Each entry is a
        dict with ``role`` ("user" or "assistant") and ``content`` (str).
        The current message must NOT be included — it is appended here.
    system_prompt:
        The system-level instruction string passed to Gemini.

    Returns
    -------
    str
        The assistant reply text.
    """
    # Build the Gemini-SDK Contents list.
    # The SDK accepts dicts with "role" and "parts" directly; the "model"
    # role is what Gemini uses for assistant turns.
    contents: list = []

    for entry in history:
        role = "model" if entry["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": entry["content"]}]})

    # Append the current user message.
    contents.append({"role": "user", "parts": [{"text": message}]})

    return _call_gemini(contents=contents, system_instruction=system_prompt)
