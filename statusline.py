# Claude Code 状态栏脚本
# Claude Code 每次回复后会把会话信息（JSON）传给这个脚本；
# 我们把其中的订阅额度（5 小时 / 每周）存到 usage.json，桌宠去读这个文件。
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
USAGE_FILE = HERE / "usage.json"
WINDOWS = {"five_hour": "5h", "seven_day": "周"}


def save_usage(rate_limits):
    now = time.time()
    try:
        old = json.loads(USAGE_FILE.read_text())
    except Exception:
        old = {}

    out = {"updated_at": int(now)}
    for key in WINDOWS:
        w = rate_limits.get(key)
        if w and w.get("used_percentage") is not None:
            out[key] = {"used_percentage": w["used_percentage"], "resets_at": w.get("resets_at")}
        elif key in old and (old[key].get("resets_at") or 0) > now:
            out[key] = old[key]          # 这次没给，但旧数据还没过期，保留

    tmp = USAGE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(out))
    tmp.replace(USAGE_FILE)


def main():
    data = json.load(sys.stdin)
    rate_limits = data.get("rate_limits") or {}
    if rate_limits:
        save_usage(rate_limits)

    # 顺便在 Claude Code 底部显示一行
    parts = [(data.get("model") or {}).get("display_name", "")]
    for key, name in WINDOWS.items():
        w = rate_limits.get(key)
        if w and w.get("used_percentage") is not None:
            parts.append(f"{name} {w['used_percentage']:.0f}%")
    if not rate_limits:
        parts.append("暂无订阅额度数据")
    print(" · ".join(p for p in parts if p))


try:
    main()
except Exception as e:      # 状态栏脚本出错不能影响 Claude Code
    print(f"claude-pet: {e}")
