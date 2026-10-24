# 小场景动画：Claude 娘在桌前工作（Seedance 2.0，通过 fal）
# 所有动画都从底图 anim/base.png 出发，大部分也回到底图，所以衔接处姿势一致。
#
# 用法：
#   source ~/claude-pet/fal_key.sh
#   .venv/bin/python make_scene.py type          # 一次生成一段
#   .venv/bin/python make_scene.py all           # 基础动作：打字、快速打字、伸懒腰、打瞌睡
#   .venv/bin/python make_scene.py stories       # 五段小剧情：续咖啡、卡住了、活动筋骨、注意到你、好消息
#   .venv/bin/python make_scene.py sleep wake    # 第二批（要先有 doze）
# 结果：anim/<名字>_1.mp4（再生成会编号 _2、_3）
# 然后切帧：.venv/bin/python video_to_frames.py anim/type_1.mp4 type
import os
import sys
import threading
from pathlib import Path

import av
import fal_client
import httpx
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "anim"
MODEL = "bytedance/seedance-2.0/image-to-video"

COMMON = (
    " Static camera, no zoom, no pan. The desk, chair, laptop and mug stay exactly where they are. "
    "Flat solid green background everywhere, no shadow, no floor, no other objects. "
    "Keep her face, hair, outfit and colors exactly the same as the image. "
    "Realistic body mechanics with real weight and momentum: weight shifts before each movement, "
    "hair and skirt follow the body with natural lag and settle. No floating, feet never slide."
)

# 站立身高：按三视图（约 8.3 头身）和底图里她的头部大小算出来，
# 站直时约是桌面高度的 2.3 倍，桌面大约到她胯部下方；
# 底图留了头顶空间后，站直时头顶离画面上沿约 1/4 画面高。
HEIGHT = (
    " Her height must stay consistent: when she stands up straight she is about 2.3 times as tall "
    "as the desk, the desktop comes up to just below her hips, and the top of her head is about a "
    "quarter of the frame height below the top edge of the frame. Her head never leaves the frame."
)

# start / end：base = 底图；doze_end = 打瞌睡那段视频的最后一帧（她趴在桌上睡着的样子）
CLIPS = {
    "type": {
        "start": "base", "end": "base", "duration": "5",
        "prompt": "She keeps typing on the laptop at a calm, steady pace, fingers moving on the "
                  "keyboard, occasionally glancing at the screen, blinking, a small focused smile, "
                  "breathing softly. The last frame matches the first frame so it loops seamlessly.",
    },
    "type_fast": {
        "start": "base", "end": "base", "duration": "5",
        "prompt": "She types very fast and intensely on the laptop, leaning slightly forward, "
                  "eyebrows knitted, focused and a bit stressed, quick finger movements. "
                  "The last frame matches the first frame so it loops seamlessly.",
    },
    "stretch": {
        "start": "base", "end": "base", "duration": "6",
        "prompt": "She stops typing, leans back in the chair and stretches both arms up over her "
                  "head with a small yawn, holds the stretch for a moment, relaxes, rolls her "
                  "shoulders, then goes back to typing on the laptop.",
    },
    "stroll": {
        "start": "base", "end": "base", "duration": "15",
        "prompt": "One continuous take. She stops typing, pushes back the chair and stands up, "
                  "steps away from the desk and walks a few relaxed steps to the left side of the "
                  "frame, playfully turns around once on the spot with her long hair and skirt "
                  "swinging out, smiles, walks back to the desk, sits down on the chair, pulls "
                  "it in and continues typing on the laptop.",
    },
    "coffee": {
        "start": "base", "end": "base", "duration": "15",
        "prompt": "One continuous take. She reaches for the mug to take a sip, finds it empty, "
                  "glances into it with a little sigh, pushes back the chair and stands up holding "
                  "the mug, and walks off the left edge of the frame. A moment later she walks back "
                  "in from the left carrying the mug with steam rising from it, blows on it and takes "
                  "a careful sip while walking, sets the mug back on the desk, sits down, pulls the "
                  "chair in and continues typing on the laptop.",
    },
    "think": {
        "start": "base", "end": "base", "duration": "12",
        "prompt": "One continuous take. She stops typing and frowns at the screen, stuck on a hard "
                  "problem, leans back, then stands up and paces two or three steps to the left and "
                  "back with one hand on her chin, thinking. Suddenly she gets an idea, her eyes "
                  "light up, she hurries back to the desk, sits down and types quickly and eagerly "
                  "on the laptop.",
    },
    "exercise": {
        "start": "base", "end": "base", "duration": "10",
        "prompt": "One continuous take. Stiff from sitting too long, she stands up beside the desk, "
                  "puts both hands on her lower back and leans back to stretch, twists her waist to "
                  "the left and to the right, rolls her neck, lets out a long relaxed breath, then "
                  "sits back down and continues typing on the laptop.",
    },
    "notice": {
        "start": "base", "end": "base", "duration": "10",
        "prompt": "One continuous take. While typing she senses someone watching, looks up straight "
                  "at the camera, pauses in surprise, then stands up and takes two steps toward the "
                  "camera, leans in curiously, tilts her head, smiles warmly and gives a small wave, "
                  "then walks back, sits down and continues typing on the laptop.",
    },
    "good_news": {
        "start": "base", "end": "base", "duration": "8",
        "prompt": "One continuous take. She reads something on the screen, her eyes widen in happy "
                  "surprise, she stands up and does a small cheer with both fists, beaming, then "
                  "sits back down happily and continues typing on the laptop.",
    },
    "doze": {
        "start": "base", "end": None, "duration": "5",
        "prompt": "She slows down typing, gets very sleepy, yawns, her eyelids droop, and she "
                  "slowly folds her arms on the desk and rests her head on them, falling asleep.",
    },
    "sleep": {
        "start": "doze_end", "end": "doze_end", "duration": "5",
        "prompt": "She sleeps peacefully with her head resting on her folded arms on the desk, "
                  "slow calm breathing, shoulders rising and falling gently, a few strands of hair "
                  "move slightly. The last frame matches the first frame so it loops seamlessly.",
    },
    "wake": {
        "start": "doze_end", "end": "base", "duration": "5",
        "prompt": "She wakes up, lifts her head from her arms, rubs her eyes, stretches a little, "
                  "smiles and goes back to typing on the laptop.",
    },
}
FIRST_BATCH = ["type", "type_fast", "stretch", "doze"]
STORIES = ["coffee", "think", "exercise", "notice", "good_news"]
STANDING = ["stretch"] + STORIES      # 会站起来 / 举手的几段：底图留了头顶空间后要重新生成


# ===== 1. 起止帧 =====
def doze_last_frame():
    """取最新一段 doze 视频的最后一帧，存成图片"""
    videos = sorted(OUT_DIR.glob("doze_[0-9]*.mp4"), key=lambda p: p.stat().st_mtime)
    if not videos:
        sys.exit("还没有 doze 视频：先运行 make_scene.py doze")
    container = av.open(str(videos[-1]))
    last = None
    for frame in container.decode(video=0):
        last = frame
    container.close()
    path = OUT_DIR / "doze_end.png"
    last.to_image().save(path)
    print("睡着的帧取自：", videos[-1].name)
    return path


DOZE_END = None     # 本次运行里已经取好的睡着帧


# 底图缩小到这个比例、贴在画面右下角：上方留出空间，她站起来头不会出画
# （video_to_frames.py 里的 SCENE_SCALE 要和这里一样）
SCENE_SCALE = 0.72
GREEN = (0, 177, 64)


def padded_base():
    """把 base.png 缩小贴到同样大小的纯绿画布右下角，存成 base_padded.png。
    先把原图的绿底抠掉再贴，整张图的绿色完全一致，没有接缝。"""
    src = OUT_DIR / "base.png"
    if not src.exists():
        sys.exit("没有 anim/base.png：先挑一张底图，cp anim/base_1.png anim/base.png")
    base = Image.open(src).convert("RGB")
    w, h = base.size

    # 抠绿：绿色程度 = G - max(R, B)，和 video_to_frames.py 一样
    a = np.asarray(base).astype(np.float32)
    greenness = a[..., 1] - np.maximum(a[..., 0], a[..., 2])
    alpha = np.clip((70 - greenness) / 45, 0, 1)
    rgba = base.convert("RGBA")
    rgba.putalpha(Image.fromarray((alpha * 255).astype(np.uint8)))

    small = rgba.resize((round(w * SCENE_SCALE), round(h * SCENE_SCALE)), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), GREEN + (255,))
    canvas.alpha_composite(small, (w - small.width, h - small.height))
    path = OUT_DIR / "base_padded.png"
    canvas.convert("RGB").save(path)
    return path


def frame_path(kind):
    global DOZE_END
    if kind == "base":
        return padded_base()
    if DOZE_END is None:
        DOZE_END = doze_last_frame()
    return DOZE_END


# ===== 2. 生成一段 =====
def generate(name):
    clip = CLIPS[name]
    start_url = fal_client.upload_file(str(frame_path_safe(clip["start"])))
    arguments = {
        "prompt": clip["prompt"] + COMMON + (HEIGHT if name in STANDING else ""),
        "image_url": start_url,
        "resolution": "720p",
        "duration": clip["duration"],
        "aspect_ratio": "16:9",
        "generate_audio": False,
    }
    if clip["end"] == clip["start"]:
        arguments["end_image_url"] = start_url
    elif clip["end"]:
        arguments["end_image_url"] = fal_client.upload_file(str(frame_path_safe(clip["end"])))

    print(f"[{name}] 生成中……")
    result = fal_client.subscribe(MODEL, arguments=arguments)

    n = 1
    while (OUT_DIR / f"{name}_{n}.mp4").exists():
        n += 1
    path = OUT_DIR / f"{name}_{n}.mp4"
    response = httpx.get(result["video"]["url"], follow_redirects=True, timeout=180)
    response.raise_for_status()
    path.write_bytes(response.content)
    print(f"[{name}] 完成：{path.name}")


def generate_safely(name, failed):
    try:
        generate(name)
    except Exception as e:
        print(f"[{name}] 失败：{e}")
        failed.append(name)


# ===== 3. 主程序 =====
if not os.environ.get("FAL_KEY"):
    sys.exit("没有找到 FAL_KEY，先运行：source ~/claude-pet/fal_key.sh")

names = sys.argv[1:]
if names == ["all"]:
    names = FIRST_BATCH
elif names == ["stories"]:
    names = STORIES
elif names == ["standing"]:
    names = STANDING
if not names or any(n not in CLIPS for n in names):
    sys.exit("用法：make_scene.py all | stories | standing | " + " ".join(CLIPS))

# 几段同时提交，一起等（起止帧文件只读不写，不会互相干扰）
BASE_PATH = padded_base()     # 先做好，几个线程只读


def frame_path_safe(kind):
    return BASE_PATH if kind == "base" else frame_path(kind)


if "doze_end" in [CLIPS[n]["start"] for n in names]:
    frame_path("doze_end")     # 先取好，避免几个线程同时写这个文件
failed = []
threads = [threading.Thread(target=generate_safely, args=(n, failed)) for n in names]
for t in threads:
    t.start()
for t in threads:
    t.join()

print("全部结束。" + (f"失败：{failed}" if failed else ""))
print("切帧：.venv/bin/python video_to_frames.py anim/<名字>_1.mp4 <名字>")
