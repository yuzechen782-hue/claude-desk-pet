# 在桌面生成「Claude 桌宠.app」：双击启动桌宠，不弹终端
# 用法（只需运行一次）：
#   cd ~/claude-pet
#   .venv/bin/python make_app.py
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
APP = Path.home() / "Desktop" / "Claude 桌宠.app"
CONTENTS = APP / "Contents"


# ===== 1. 清掉旧的，建好 App 的文件夹结构 =====
if APP.exists():
    shutil.rmtree(APP)
(CONTENTS / "MacOS").mkdir(parents=True)
(CONTENTS / "Resources").mkdir(parents=True)


# ===== 2. 启动脚本：先关掉已经在跑的桌宠，再启动新的 =====
launcher = CONTENTS / "MacOS" / "launch"
launcher.write_text(f"""#!/bin/bash
cd "{HERE}"
pkill -f "{HERE}/pet.py"
exec "{HERE}/.venv/bin/python" "{HERE}/pet.py" >/dev/null 2>&1
""")
os.chmod(launcher, 0o755)


# ===== 3. Info.plist：告诉 macOS 这是个 App，用哪个脚本、哪个图标 =====
(CONTENTS / "Info.plist").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Claude 桌宠</string>
    <key>CFBundleIdentifier</key><string>local.asuna.claude-pet</string>
    <key>CFBundleExecutable</key><string>launch</string>
    <key>CFBundleIconFile</key><string>icon</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSUIElement</key><true/>
</dict>
</plist>
""")


# ===== 4. 图标：她的笑脸头像，圆形 + 橙色边 =====
face = Image.open(HERE / "assets" / "face_smile.png").convert("RGBA").resize((1024, 1024), Image.LANCZOS)
mask = Image.new("L", (1024, 1024), 0)
ImageDraw.Draw(mask).ellipse((40, 40, 984, 984), fill=255)
icon = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
icon.paste(face, (0, 0), mask)
ImageDraw.Draw(icon).ellipse((40, 40, 984, 984), outline=(217, 119, 87, 255), width=36)

iconset = HERE / "icon.iconset"
if iconset.exists():
    shutil.rmtree(iconset)
iconset.mkdir()
for size in (16, 32, 128, 256, 512):
    icon.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
    icon.resize((size * 2, size * 2), Image.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(CONTENTS / "Resources" / "icon.icns")],
               check=True)
shutil.rmtree(iconset)

# 让 Finder 立刻刷新图标
subprocess.run(["touch", str(APP)])
print("已生成：", APP)
print("双击启动；想开机自动启动：系统设置 → 通用 → 登录项 → 加号 → 选这个 App")
