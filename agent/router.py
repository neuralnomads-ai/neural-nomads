import os
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "llama3.1:8b")
CODER_MODEL = os.getenv("CODER_MODEL", "deepseek-coder:6.7b")
DRAFT_MODEL = os.getenv("DRAFT_MODEL", "mistral:7b-instruct")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
CLOUD_MODEL = os.getenv("CLOUD_MODEL", "gpt-4o-mini")

def _ollama_generate(model: str, prompt: str, timeout: int = 180) -> str:
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json().get("response", "").strip()

def _cloud_chat(prompt: str) -> str:
    # Optional. Only used if OPENAI_API_KEY is present.
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=CLOUD_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()

def route(task_type: str, prompt: str, allow_cloud: bool = False) -> str:
    """
    task_type:
      - "reason"  -> general reasoning / planning
      - "code"    -> code generation / scripting
      - "draft"   -> social copy, captions, thread drafts
      - "judge"   -> evaluation / scoring (local unless allow_cloud True)
    """
    task_type = (task_type or "reason").lower().strip()

    if allow_cloud and OPENAI_API_KEY:
        # Use cloud only for "judge" or explicitly hard tasks
        if task_type in {"judge"}:
            return _cloud_chat(prompt)

    if task_type == "code":
        return _ollama_generate(CODER_MODEL, prompt)
    if task_type == "draft":
        return _ollama_generate(DRAFT_MODEL, prompt)
    # default
    return _ollama_generate(LOCAL_MODEL, prompt)
