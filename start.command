#!/bin/bash
# 双击启动桌宠。第一次会自动：建虚拟环境、安装依赖、切帧（要等几分钟）
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "第一次运行：安装依赖……"
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt || exit 1
fi

if [ ! -f assets/type/meta.json ]; then
  echo "第一次运行：切帧……"
  bash build_assets.sh
fi

pkill -f "$(pwd)/pet.py"
nohup .venv/bin/python pet.py >/dev/null 2>&1 &
