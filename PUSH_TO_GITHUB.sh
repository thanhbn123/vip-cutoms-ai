#!/usr/bin/env bash
set -euo pipefail
REPO_URL="https://github.com/thanhbn123/vip-cutoms-ai.git"

echo "VIP Customs AI bootstrap push"
echo "Remote: $REPO_URL"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: Run this script inside the vip-cutoms-ai repository."
  exit 1
fi

git branch -M main
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi

echo "Current commit: $(git rev-parse HEAD)"
echo "Pushing main..."
git push -u origin main

echo "DONE. Now open Claude Code in this repo and use docs/prompts/CLAUDE-PROJECT-CONTROLLER.md"
