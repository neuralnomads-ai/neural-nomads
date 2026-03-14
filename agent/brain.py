import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv

from agent.router import route
from agent import memory

load_dotenv()
PROJECT_NAME = os.getenv("PROJECT_NAME", "neural-nomads-phase1")

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def _log(event: dict) -> None:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(LOG_DIR, f"{PROJECT_NAME}_{ts}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def run_task(task_type: str, objective: str, allow_cloud: bool = False) -> str:
    # Recall
    recalls = memory.search(objective, k=5)
    recall_text = "\n\n".join([f"- {r['text']}" for r in recalls]) if recalls else "None"

    prompt = f"""
You are OpenClaw running a controlled 14-day experiment.

Objective:
{objective}

Relevant memory:
{recall_text}

Constraints:
- Be concrete.
- Do not invent results.
- Output must be directly usable.
- If you propose actions, include file paths and commands where relevant.

Return only the deliverable for the objective.
""".strip()

    t0 = time.time()
    output = route(task_type=task_type, prompt=prompt, allow_cloud=allow_cloud)
    dt = round(time.time() - t0, 2)

    memory.add(
        doc_id=f"{int(time.time())}_{task_type}",
        text=f"OBJECTIVE: {objective}\nOUTPUT:\n{output}",
        meta={"task_type": task_type, "seconds": dt},
    )

    _log({
        "ts_utc": datetime.utcnow().isoformat(),
        "task_type": task_type,
        "allow_cloud": allow_cloud,
        "objective": objective,
        "seconds": dt,
        "output": output,
    })

    return output
