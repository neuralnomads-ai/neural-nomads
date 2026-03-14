import os, json, subprocess
from agent.brain import run_task
from dotenv import load_dotenv
load_dotenv()

NEURAL_NOMADS = os.path.expanduser("~/OpenClaw/neural_nomads")

print("OpenClaw ready. Type your request. Ctrl+C to exit.")
print("-" * 50)

while True:
    try:
        user_input = input("You: ").strip()
        if not user_input:
            continue

        low = user_input.lower()

        if any(w in low for w in ["post", "farcaster", "cast"]):
            print("Running Farcaster agent...")
            subprocess.run(["python3", "agents/farcaster_agent.py"], cwd=NEURAL_NOMADS)

        elif any(w in low for w in ["upload", "pinata", "ipfs"]):
            print("Running Pinata upload...")
            subprocess.run(["python3", "agents/pinata_upload.py"], cwd=NEURAL_NOMADS)

        elif any(w in low for w in ["website", "site", "build"]):
            print("Building website...")
            subprocess.run(["python3", "agents/build_site.py"], cwd=NEURAL_NOMADS)

        else:
            print("OpenClaw:", run_task(task_type="reason", objective=user_input, allow_cloud=False))

    except KeyboardInterrupt:
        print("\nGoodnight.")
        break
