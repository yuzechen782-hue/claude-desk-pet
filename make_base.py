# 生成小场景的底图：Claude 娘坐在桌前用笔记本电脑（Seedream 4.5 图像编辑，通过 fal）
# 所有动画都从这张图开始、回到这张图，所以先挑一张满意的。
# 用法：
#   source ~/claude-pet/fal_key.sh
#   .venv/bin/python make_base.py
# 结果：anim/base_1.png … base_4.png（一次出 4 张候选；再运行会接着编号）
# 挑好以后：cp anim/base_3.png anim/base.png
import os
import sys
from pathlib import Path

import fal_client
import httpx
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "anim"
OUT_DIR.mkdir(exist_ok=True)

MODEL = "fal-ai/bytedance/seedream/v4.5/edit"
NUM_IMAGES = 4
GREEN = (0, 177, 64)

PROMPT = (
    "Use the girl from the reference images and keep her exactly the same: face, amber eyes, "
    "very long orange hair, orange flower hair ornament with black ribbon, white and black dress "
    "with orange panels and flower embroidery, white boots. "
    "Scene: she sits on a simple wooden chair at a small wooden desk, typing on an open laptop, "
    "relaxed and focused. Three-quarter front view, so her face is clearly visible and the back "
    "of the laptop faces the viewer at an angle. A mug on the desk. "
    "The desk and chair are on the right side of the image; the left side is empty space "
    "where she could walk. Everything is fully visible, nothing cropped: her whole body, "
    "the whole chair and the whole desk, standing on the bottom part of the image. "
    "The background is a flat, solid, pure green color everywhere (#00B140), no floor, "
    "no wall, no shadows, no other objects. Anime illustration style matching the reference "
    "images, clean line art."
)


# ===== 1. 检查 key =====
if not os.environ.get("FAL_KEY"):
    sys.exit("没有找到 FAL_KEY，先运行：source ~/claude-pet/fal_key.sh")


# ===== 2. 参考图：正面、侧面、背面立绘放在绿底上 =====
reference_urls = []
for view in ("front", "side", "back"):
    body = Image.open(HERE / "assets" / f"{view}.png").convert("RGBA")
    canvas = Image.new("RGBA", (body.width + 80, body.height + 80), GREEN + (255,))
    canvas.alpha_composite(body, (40, 40))
    path = OUT_DIR / f"ref_{view}.png"
    canvas.convert("RGB").save(path)
    reference_urls.append(fal_client.upload_file(str(path)))
print("参考图已上传")


# ===== 3. 生成 =====
print(f"生成 {NUM_IMAGES} 张候选，可能要一两分钟……")
result = fal_client.subscribe(
    MODEL,
    arguments={
        "prompt": PROMPT,
        "image_urls": reference_urls,
        "image_size": {"width": 2560, "height": 1440},    # 16:9，和之后的动画一致
        "num_images": NUM_IMAGES,
    },
    with_logs=True,
)


# ===== 4. 下载 =====
n = 1
for image in result["images"]:
    while (OUT_DIR / f"base_{n}.png").exists():
        n += 1
    path = OUT_DIR / f"base_{n}.png"
    response = httpx.get(image["url"], follow_redirects=True, timeout=120)
    response.raise_for_status()
    path.write_bytes(response.content)
    print("保存：", path)

print("挑一张满意的，复制成 anim/base.png，例如：cp anim/base_1.png anim/base.png")
