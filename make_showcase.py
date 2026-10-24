# 把桌宠的所有动画串成一段展示视频（mp4）和一个小 GIF
# 用法：.venv/bin/python make_showcase.py
# 结果：showcase.mp4、showcase.gif（在 claude-pet 文件夹里）
import json
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

AUTHOR = "Asuna"            # 作者署名，想换成别的名字就改这里

W, H = 1280, 720            # 视频尺寸
FPS = 24
SCENE_W = 960               # 场景在视频里的宽度
GIF_W = 640                 # GIF 宽度
GIF_FPS = 12

CLAY = (217, 119, 87)
INK = (61, 43, 34)
MUTED = (154, 132, 120)

# 展示顺序：(动画名, 播放几遍, 标题, 说明, 面板上的 5 小时 / 每周用量, 头像表情)
SEQUENCE = [
    ("type",      2, "平时",       "坐在桌前，不紧不慢地打字",            30, 22, "smile"),
    ("notice",    1, "注意到你",   "单击她：抬头看你，走过来挥挥手",      30, 22, "shy"),
    ("type",      1, "平时",       "回到桌前继续工作",                    30, 22, "smile"),
    ("coffee",    1, "续咖啡",     "杯子空了，去续一杯（晚上更常出现）",  35, 24, "smile"),
    ("exercise",  1, "活动筋骨",   "坐久了，起来扭扭腰",                  40, 25, "smile"),
    ("think",     1, "卡住了",     "用量过半：难题，起身想一想",          62, 30, "serious"),
    ("stretch",   1, "伸懒腰",     "",                                    70, 33, "serious"),
    ("type_fast", 2, "快没额度了", "用量 80% 以上：埋头飞快地打字",       86, 41, "pout"),
    ("doze",      1, "撑不住了",   "用量 95% 以上：打着瞌睡趴下",         97, 45, "sad"),
    ("sleep",     2, "睡着了",     "等额度重置",                          97, 45, "sad"),
    ("wake",      1, "醒来",       "额度重置",                            3,  45, "laugh"),
    ("good_news", 1, "好消息",     "额度重置啦！",                        3,  45, "laugh"),
    ("type",      1, "继续工作",   "",                                    3,  45, "smile"),
]


# ===== 字体 =====
def font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=1 if (bold and "PingFang" in path) else 0)
            except Exception:
                continue
    return ImageFont.load_default()


F_TITLE = font(40, bold=True)
F_NOTE = font(22)
F_PANEL = font(17, bold=True)
F_SMALL = font(14)


# ===== 背景：柔和的渐变，像桌面 =====
def make_background():
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    top = np.array([62, 78, 110])
    bottom = np.array([28, 34, 52])
    t = (y * 0.85 + x * 0.15)[..., None]
    rgb = top * (1 - t) + bottom * t
    return Image.fromarray(rgb.astype(np.uint8), "RGB").convert("RGBA")


BACKGROUND = make_background()


# ===== 用量面板（和桌宠里的样子一样） =====
FACES = {name: Image.open(ASSETS / f"face_{name}.png").convert("RGBA").resize((76, 76))
         for name in ("smile", "shy", "serious", "pout", "sad", "laugh", "calm")}
CIRCLE = Image.new("L", (76, 76), 0)
ImageDraw.Draw(CIRCLE).ellipse((0, 0, 75, 75), fill=255)


def draw_panel(img, x, y, five, week, face, line):
    pw, ph = 300, 158
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((x, y, x + pw, y + ph), radius=18, fill=(255, 250, 245, 240),
                        outline=CLAY, width=2)
    avatar = FACES[face].copy()
    avatar.putalpha(CIRCLE)
    img.alpha_composite(avatar, (x + 16, y + 20))
    d.ellipse((x + 16, y + 20, x + 92, y + 96), outline=CLAY, width=3)

    def bar(by, label, pct, sub):
        bx, bw = x + 108, pw - 124
        d.text((bx, by), label, font=F_PANEL, fill=INK)
        d.text((bx + bw, by), f"{pct}%", font=F_PANEL, fill=INK, anchor="ra")
        d.rounded_rectangle((bx, by + 24, bx + bw, by + 32), radius=4, fill=(240, 226, 216))
        color = CLAY if pct < 80 else (194, 65, 12) if pct < 95 else (185, 28, 28)
        if pct > 0:
            d.rounded_rectangle((bx, by + 24, bx + max(8, bw * pct / 100), by + 32), radius=4, fill=color)
        d.text((bx, by + 36), sub, font=F_SMALL, fill=MUTED)

    bar(y + 14, "5 小时", five, "2小时13分后重置" if five > 5 else "4小时59分后重置")
    bar(y + 72, "本周", week, "3天11小时后重置")
    d.text((x + pw / 2, y + ph - 24), line, font=F_SMALL, fill=INK, anchor="ma")


# ===== 读动画帧 =====
def load_clip(name):
    folder = ASSETS / name
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        return None, None
    meta = json.loads(meta_path.read_text())
    paths = sorted(folder.glob("*.png"))
    return paths, meta["fps"]


# ===== 片头 / 片尾：作者署名 =====
F_BIG = font(64, bold=True)


def title_card(seconds, line1, line2):
    for k in range(round(seconds * FPS)):
        fade = min(1.0, k / (FPS * 0.5), (seconds * FPS - k) / (FPS * 0.5))
        frame = BACKGROUND.copy()
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.text((W / 2, H / 2 - 40), line1, font=F_BIG, fill=(255, 255, 255), anchor="mm")
        d.text((W / 2, H / 2 + 40), line2, font=F_NOTE, fill=(220, 225, 240), anchor="mm")
        layer.putalpha(layer.getchannel("A").point(lambda a: int(a * fade)))
        frame.alpha_composite(layer)
        yield frame.convert("RGB")


# ===== 逐帧合成 =====
def frames():
    yield from title_card(2.5, "Claude 桌宠", f"by {AUTHOR}  ·  订阅用量陪伴桌宠")
    scene_x = W - SCENE_W - 20
    scene_h = None
    for name, repeat, title, note, five, week, face in SEQUENCE:
        paths, clip_fps = load_clip(name)
        if not paths:
            print(f"跳过 {name}（还没切帧）")
            continue
        print(f"{name}：{len(paths)} 帧 × {repeat}")
        cache = {}
        n_out = round(len(paths) / clip_fps * FPS) * repeat        # 按原速换算成 24 fps
        for k in range(n_out):
            t = k / FPS
            i = int(t * clip_fps) % len(paths)
            if i not in cache:
                scene = Image.open(paths[i]).convert("RGBA")
                scene_h = round(scene.height * SCENE_W / scene.width)
                cache = {i: scene.resize((SCENE_W, scene_h), Image.LANCZOS)}
            frame = BACKGROUND.copy()
            frame.alpha_composite(cache[i], (scene_x, H - scene_h - 10))
            draw_panel(frame, W - 320 - 40, 24, five, week, face, note or title)
            d = ImageDraw.Draw(frame)
            d.text((48, 40), title, font=F_TITLE, fill=(255, 255, 255))
            if note:
                d.text((50, 96), note, font=F_NOTE, fill=(220, 225, 240))
            d.text((48, H - 62), f"Claude 桌宠 · 设计与制作 {AUTHOR}", font=F_NOTE, fill=(235, 238, 248))
            d.text((48, H - 32), "立绘：ai-chan-sheets（胖次狐 / lmy414，CC BY-NC-SA 4.0）",
                    font=F_SMALL, fill=(150, 158, 180))
            yield frame.convert("RGB")
    yield from title_card(2.5, f"by {AUTHOR}", "立绘 ai-chan-sheets（胖次狐 / lmy414）· 动画 Seedance · CC BY-NC-SA 4.0")


# ===== 输出 mp4 + GIF =====
mp4_path = HERE / "showcase.mp4"
gif_path = HERE / "showcase.gif"
container = av.open(str(mp4_path), "w")
stream = container.add_stream("h264", rate=FPS)
stream.width, stream.height = W, H
stream.pix_fmt = "yuv420p"
stream.options = {"crf": "20"}

gif_frames = []
count = 0
for frame in frames():
    for packet in stream.encode(av.VideoFrame.from_image(frame)):
        container.mux(packet)
    if count % (FPS // GIF_FPS) == 0:
        gif_frames.append(frame.resize((GIF_W, round(H * GIF_W / W)), Image.LANCZOS))
    count += 1
for packet in stream.encode():
    container.mux(packet)
container.close()
print(f"视频：{mp4_path}（{count / FPS:.0f} 秒）")

if gif_frames:
    palette_src = gif_frames[len(gif_frames) // 2].quantize(colors=200, method=Image.Quantize.MEDIANCUT)
    gif = [f.quantize(palette=palette_src, dither=Image.Dither.NONE) for f in gif_frames]
    gif[0].save(gif_path, save_all=True, append_images=gif[1:], duration=round(1000 / GIF_FPS),
                loop=0, optimize=True)
    print(f"GIF：{gif_path}（{gif_path.stat().st_size / 1e6:.1f} MB）")
