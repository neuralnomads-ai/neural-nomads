#!/bin/bash
set -e
cd ~/OpenClaw
python3 agents/build_site.py
git add -f agents/build_site.py
git add -f site
git add -f scripts/build_and_deploy.sh
git add .gitignore
git commit -m "Update Neural Nomads site" || true
git push origin main
