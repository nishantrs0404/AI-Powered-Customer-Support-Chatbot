
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors


# Load .env from the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = "gemini-3.5-flash-lite"


def generate_reply(message: str) -> str:
    """Generate a customer-support response using Gemini."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from the .env file."
        )

    client = genai.Client(api_key=api_key)

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=message,
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
