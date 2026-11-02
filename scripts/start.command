#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo '请先按 README 完成开发环境安装。'
  read -r
  exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
  echo '缺少 Web 构建产物，请先运行 npm install 和 npm run build。'
  read -r
  exit 1
fi
open http://127.0.0.1:8000
exec .venv/bin/python -m uvicorn agent.app:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
