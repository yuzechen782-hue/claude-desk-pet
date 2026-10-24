#!/bin/bash
# 从 anim/ 里的视频切出桌宠用的帧（第一次使用前运行一次，大约几分钟）
# 用法：bash build_assets.sh
cd "$(dirname "$0")"
PY=.venv/bin/python

# 重新对齐：以 coffee 的第一帧为标准，其他段都对齐到它
rm -f assets/scene_ref.json

# 1. 用"留了头顶空间"的底图生成的几段：直接切
for n in coffee stretch think exercise notice good_news; do
  echo "== $n"
  $PY video_to_frames.py anim/$n.mp4 $n | grep -E "对齐|已保存"
done

# 2. 用旧底图生成的几段（坐着的动作）：缩小贴到右下角，和上面对齐
for n in type type_fast doze; do
  echo "== $n"
  $PY video_to_frames.py anim/$n.mp4 $n --shrink | grep -E "对齐|已保存"
done

# 3. 睡觉、醒来：第一帧是趴在桌上，没法按第一帧对齐，沿用 doze 的对齐参数
for n in sleep wake; do
  echo "== $n"
  $PY video_to_frames.py anim/$n.mp4 $n --shrink --align-like doze | grep -E "对齐|已保存"
done

echo "完成。启动：.venv/bin/python pet.py"
