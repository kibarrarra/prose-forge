import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def get_openai_client():
    """Get a configured OpenAI client with standard timeouts."""
    timeout = httpx.Timeout(
        connect=30.0,
        read=600.0,
        write=600.0,
        pool=60.0
    )
    return OpenAI(timeout=timeout) 