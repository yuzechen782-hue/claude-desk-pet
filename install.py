# 把 statusline.py 登记到 Claude Code 的设置里（~/.claude/settings.json）
# 原设置会先备份成 settings.json.bak
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
settings_path = Path.home() / ".claude" / "settings.json"
command = f'python3 "{HERE / "statusline.py"}"'

settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        sys.exit(f"{settings_path} 不是合法 JSON，请先手动检查")
    shutil.copy(settings_path, settings_path.with_suffix(".json.bak"))
    print("已备份原设置到", settings_path.with_suffix(".json.bak"))

old = settings.get("statusLine")
if old and old.get("command") != command:
    print("注意：原来已有状态栏设置，将被替换：", old)

settings["statusLine"] = {"type": "command", "command": command}
settings_path.parent.mkdir(parents=True, exist_ok=True)
settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
print("已设置状态栏：", command)
print("下一步：打开 claude，随便发一句话，usage.json 就会出现在", HERE)
