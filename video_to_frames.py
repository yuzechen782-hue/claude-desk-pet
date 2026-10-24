# 把绿幕动画视频切成透明背景的帧，给桌宠播放
# 用法：
#   .venv/bin/python video_to_frames.py anim/idle_1.mp4 idle
#   .venv/bin/python video_to_frames.py anim/walk_1.mp4 walk
#   .venv/bin/python video_to_frames.py anim/wind_1.mp4 wind
#   .venv/bin/python video_to_frames.py anim/turn_back_1.mp4 turn_back
#   .venv/bin/python video_to_frames.py anim/turn_side_1.mp4 turn_side
#   .venv/bin/python video_to_frames.py anim/turn_side_r_1.mp4 turn_side_r
#   （其他动画同理：第二个参数就是动画名字）
#   .venv/bin/python video_to_frames.py anim/stroll_left_1.mp4 stroll_left
# 结果：assets/<名字>/0000.png …，assets/<名字>/meta.json
#       anim/check_<名字>.png（抽 6 帧拼在深色背景上，检查抠图）
import json
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
LOOPS = {"idle", "walk", "type", "type_fast", "sleep"}      # 首尾相同的循环动画
SCENE_W = 960                 # 小场景（横版视频）保存的帧宽度
SCENE_SCALE = 0.72            # 和 make_scene.py 一样：底图缩小后贴在右下角
# 用旧底图（没缩小）生成的视频，切帧时加 --shrink，按同样比例缩小贴到右下角，和新视频对齐
SHRINK = "--shrink" in sys.argv
# 第一帧不是底图坐姿的片段（比如睡觉、醒来：开头是趴在桌上），没法按第一帧对齐，
# 用 --align-like doze 直接沿用另一段（同一批视频）的对齐参数
ALIGN_LIKE = sys.argv[sys.argv.index("--align-like") + 1] if "--align-like" in sys.argv else None
FRAME_H = 480                 # 保存的帧高度（像素）

# 和 make_anim.py 里的画布比例一致：人物高 88%，离底边 5%
BODY_FRAC = 0.88
BOTTOM_FRAC = 0.05
TOP_MARGIN = 0.04             # 头顶上方多留一点，头发飘起来不会被切掉
BOTTOM_MARGIN = 0.01

# 绿色程度 = G - max(R, B)；低于 KEEP 完全保留，高于 DROP 完全透明
KEEP = 25
DROP = 70


# ===== 1. 读视频 =====
video_path = Path(sys.argv[1])
name = sys.argv[2]
container = av.open(str(video_path))
stream = container.streams.video[0]
fps = float(stream.average_rate)
frames = [f.to_ndarray(format="rgb24") for f in container.decode(stream)]
container.close()
print(f"读到 {len(frames)} 帧，{fps:.1f} fps")

# ===== 1.5 去掉重复帧 =====
# 生成的视频里常有"同一画面连出两帧、下一帧再跳一大步"，看起来一卡一卡。
# 删掉重复帧，并按比例降低帧率，总时长不变，节奏变均匀。
# 判断标准：缩小到 320 宽后逐像素比较，差别最大的那 0.5% 像素都几乎没变 → 重复帧。
# （打字这类动作只有手指在动，平均差别很小，但局部差别大，不会被误删）
def small(f):
    img = Image.fromarray(f)
    return np.asarray(img.resize((320, round(img.height * 320 / img.width)))).astype(np.float32)


def is_duplicate(a, b):
    d = np.abs(a - b)
    if np.percentile(d, 99.5) < 4:
        return True
    # 走路：画面整体在动，几乎没变的帧是生成时的"卡顿"，也去掉
    return name == "walk" and d.mean() < 1.5


thumbs = [small(f) for f in frames]
keep = [0]
for i in range(1, len(frames)):
    if not is_duplicate(thumbs[i], thumbs[keep[-1]]):
        keep.append(i)
if len(keep) < len(frames):
    print(f"去掉 {len(frames) - len(keep)} 个重复帧")
    fps = fps * len(keep) / len(frames)
    frames = [frames[i] for i in keep]
    thumbs = [thumbs[i] for i in keep]


def diff(i, j):
    return np.abs(thumbs[i] - thumbs[j]).mean()


# ===== 1.6 循环 =====
if name == "walk":
    # 走路：找出一个完整步态（左右脚各一步）有多少帧，
    # 截取整数个步态当循环，避开视频结尾被硬拉回首帧而走乱的部分
    n = len(frames)
    lags = range(10, n // 2)
    period = min(lags, key=lambda L: np.mean([diff(i, i + L) for i in range(n - L)]))
    cycles = max(1, (n - 1) // period - 1)
    length = cycles * period
    start = min(range(0, n - length), key=lambda a: diff(a, a + length))
    print(f"步态周期 {period} 帧，截取第 {start}–{start + length} 帧（{cycles} 个周期）")
    frames = frames[start:start + length]
elif name in LOOPS:
    frames = frames[:-1]      # 循环动画：最后一帧和第一帧重复，去掉


# ===== 2. 抠绿 =====
def key_green(rgb):
    a = rgb.astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    greenness = g - np.maximum(r, b)

    alpha = np.clip((DROP - greenness) / (DROP - KEEP), 0, 1)

    # 去绿边：绿色不超过红、蓝里较大的那个
    g_fixed = np.minimum(g, np.maximum(r, b))
    out = np.stack([r, g_fixed, b], axis=-1)
    return np.dstack([out, alpha * 255]).round().astype(np.uint8)


keyed = [key_green(f) for f in frames]


# ===== 小场景（横版视频）：整个画面就是场景，不裁人物，直接保存 =====
if keyed[0].shape[1] > keyed[0].shape[0]:
    out_dir = HERE / "assets" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    h = round(keyed[0].shape[0] * SCENE_W / keyed[0].shape[1])

    def to_scene(rgba):
        img = Image.fromarray(rgba, "RGBA").resize((SCENE_W, h), Image.LANCZOS)
        if SHRINK:
            small = img.resize((round(SCENE_W * SCENE_SCALE), round(h * SCENE_SCALE)), Image.LANCZOS)
            img = Image.new("RGBA", (SCENE_W, h), (0, 0, 0, 0))
            img.alpha_composite(small, (SCENE_W - small.width, h - small.height))
        return img

    # ----- 对齐：每段视频里桌子和人的位置、大小会差几个像素 -----
    # 以第一次切帧那段的第一帧为标准（存进 assets/scene_ref.json），
    # 其他段都按第一帧里"桌子 + 人"的外框缩放、平移到和标准一样，切换时就不会跳。
    def outer_box(img):
        a = np.asarray(img)[..., 3] > 128
        ys, xs = np.nonzero(a)
        return xs.min(), ys.min(), xs.max(), ys.max()

    if ALIGN_LIKE:
        other = json.loads((HERE / "assets" / ALIGN_LIKE / "meta.json").read_text())
        scale, shift_x, shift_y = other["align"]
        print(f"沿用 {ALIGN_LIKE} 的对齐参数")
    else:
        first = to_scene(keyed[0])
        x0, y0, x1, y1 = outer_box(first)
        ref_path = HERE / "assets" / "scene_ref.json"
        if ref_path.exists():
            rx0, ry0, rx1, ry1 = json.loads(ref_path.read_text())
        else:
            rx0, ry0, rx1, ry1 = int(x0), int(y0), int(x1), int(y1)
            ref_path.write_text(json.dumps([rx0, ry0, rx1, ry1]))
            print("以这段为对齐标准：", ref_path)
        scale = ((rx1 - rx0) / (x1 - x0) + (ry1 - ry0) / (y1 - y0)) / 2
        # 外框的横向中心、底边对齐
        shift_x = (rx0 + rx1) / 2 - scale * (x0 + x1) / 2
        shift_y = ry1 - scale * y1
    print(f"对齐：缩放 {scale:.3f}，平移 ({shift_x:+.1f}, {shift_y:+.1f}) 像素")

    def align(img):
        if abs(scale - 1) < 0.002 and abs(shift_x) < 0.5 and abs(shift_y) < 0.5:
            return img
        big = img.resize((round(SCENE_W * scale), round(h * scale)), Image.LANCZOS)
        out = Image.new("RGBA", (SCENE_W, h), (0, 0, 0, 0))
        out.paste(big, (round(shift_x), round(shift_y)))     # 画布是空的，直接贴（可以是负坐标）
        return out

    for i, rgba in enumerate(keyed):
        img = align(to_scene(rgba))
        img.save(out_dir / f"{i:04d}.png", optimize=True)
    meta = {"fps": fps, "loop": name in LOOPS, "scene": True,
            "align": [round(scale, 5), round(shift_x, 2), round(shift_y, 2)]}

    # 量身高：整段里画面最高点（站起来时就是头顶）离地面有多高，占画面高度的百分比
    # 标准值约 74%（站直、底图留了头顶空间）；差得多的那段可以重抽
    tops, floors = [], []
    for rgba in keyed:
        rows = np.nonzero((rgba[..., 3] > 128).any(axis=1))[0]
        if len(rows):
            tops.append(rows.min())
            floors.append(rows.max())
    if tops:
        H0 = keyed[0].shape[0]
        tallest = (max(floors) - min(tops)) / H0 * 100
        meta["tallest"] = round(tallest, 1)
        note = "（头碰到画面上沿，可能被切了）" if min(tops) <= 1 else ""
        print(f"最高点离地：{tallest:.0f}% 画面高{note}；站直的标准约 74%")
    (out_dir / "meta.json").write_text(json.dumps(meta))
    print(f"已保存 {len(keyed)} 帧到 {out_dir}（小场景）")

    picks = np.linspace(0, len(keyed) - 1, 6).round().astype(int)
    tiles = [Image.open(out_dir / f"{i:04d}.png").resize((SCENE_W // 2, h // 2)) for i in picks]
    sheet = Image.new("RGBA", (SCENE_W // 2 * 3, h // 2 * 2), (40, 50, 70, 255))
    for k, t in enumerate(tiles):
        sheet.alpha_composite(t, ((k % 3) * SCENE_W // 2, (k // 3) * h // 2))
    check_path = HERE / "anim" / f"check_{name}.png"
    sheet.convert("RGB").save(check_path)
    print("检查图：", check_path)
    sys.exit(0)


# ===== 2.5 走路：从着地的脚算出前进速度 =====
def ground_speed(alpha_frames, tol=3, band=32, match=40):
    """着地那只脚相对身体往后移动的速度，就是身体往前走的速度（视频像素/帧）"""
    masks = [a > 128 for a in alpha_frames]
    floor = max(np.nonzero(m.any(1))[0].max() for m in masks)    # 地面高度

    # 每帧找出着地的脚（最底下一条里，碰到地面的那几块）的横坐标
    contacts = []
    for m in masks:
        strip = m[floor - band:floor + 1]
        labels, n = ndimage.label(strip.any(0))
        feet = []
        for k in range(1, n + 1):
            xs = np.nonzero(labels == k)[0]
            if len(xs) < 8:
                continue
            column = strip[:, xs.min():xs.max() + 1]
            bottom = floor - band + np.nonzero(column.any(1))[0].max()
            if bottom >= floor - tol:
                feet.append(xs.mean())
        contacts.append(feet)

    # 相邻两帧同一只着地脚移动了多少
    speeds = []
    for i in range(len(contacts)):
        prev, cur = contacts[i - 1], contacts[i]          # 第 0 帧和最后一帧比（循环）
        moves = []
        for c in cur:
            if not prev:
                continue
            nearest = min(prev, key=lambda q: abs(q - c))
            if abs(c - nearest) < match:
                moves.append(abs(c - nearest))
        speeds.append(np.median(moves) if moves else np.nan)

    # 补上没测到的帧，再稍微平滑
    speeds = np.array(speeds, float)
    good = ~np.isnan(speeds)
    idx = np.arange(len(speeds))
    speeds = np.interp(idx, idx[good], speeds[good], period=len(speeds))
    kernel = np.array([1, 2, 3, 2, 1], float)
    kernel /= kernel.sum()
    padded = np.concatenate([speeds[-2:], speeds, speeds[:2]])
    return np.convolve(padded, kernel, mode="valid")


walk_speed = None
if name == "walk":
    speeds = ground_speed([k[..., 3] for k in keyed])
    body_h = keyed[0].shape[0] * BODY_FRAC
    walk_speed = [round(float(v) / body_h, 5) for v in speeds]     # 单位：身高/帧
    print(f"走路速度：平均每帧 {np.mean(speeds):.1f} 视频像素")


# ===== 3. 裁剪框 =====
# 上下：按画布比例固定，所有动画一样 → 大小一致、脚底对齐
H, W = keyed[0].shape[:2]
top = round(H * (1 - BOTTOM_FRAC - BODY_FRAC - TOP_MARGIN))
bottom = round(H * (1 - BOTTOM_FRAC + BOTTOM_MARGIN))

# 左右：以人物的"根位置"为中心裁剪
# 原地动画：根位置就是画面中心
# 散步（stroll_*）：她会走过画面，根位置每帧不同 → 裁剪框跟着她走，
#                    并把移动量存进 meta，桌宠按它移动窗口（镜头不动，所以移动量是真实的）
moving = name.startswith("stroll")
if moving:
    body_top = round(H * (1 - BOTTOM_FRAC - BODY_FRAC))
    hips = body_top + round(H * BODY_FRAC * 0.55)       # 只看腰以下（裙子 + 脚），不受头发甩动影响
    roots = []
    for rgba in keyed:
        weights = (rgba[hips:bottom, :, 3] / 255.0).sum(axis=0)
        roots.append((weights * np.arange(W)).sum() / max(weights.sum(), 1))
    # 平滑：去掉裙摆摆动带来的抖动，留下身体真正的移动
    roots = np.array(roots)
    k = 9
    padded = np.concatenate([np.full(k // 2, roots[0]), roots, np.full(k // 2, roots[-1])])
    roots = np.convolve(padded, np.ones(k) / k, mode="valid")
else:
    roots = np.full(len(keyed), W / 2)

half = 0
for rgba, root in zip(keyed, roots):
    xs = np.nonzero((rgba[top:bottom, :, 3] > 20).any(axis=0))[0]
    if len(xs):
        half = max(half, root - xs.min(), xs.max() + 1 - root)
half = int(half) + 4
print("裁剪框：上", top, "下", bottom, "半宽", half)


def crop_frame(rgba, root):
    """以 root 为中心裁出固定宽度；超出画面的部分补透明"""
    img = Image.fromarray(rgba, "RGBA")
    box = (round(root) - half, top, round(root) + half, bottom)
    return img.crop(box)            # PIL 对超出范围的部分自动补透明


# ===== 4. 保存 =====
out_dir = HERE / "assets" / name
out_dir.mkdir(parents=True, exist_ok=True)
for old in out_dir.glob("*.png"):
    old.unlink()

for i, (rgba, root) in enumerate(zip(keyed, roots)):
    img = crop_frame(rgba, root)
    w = round(img.width * FRAME_H / img.height)
    img.resize((w, FRAME_H), Image.LANCZOS).save(out_dir / f"{i:04d}.png", optimize=True)

crop_h = bottom - top
meta = {
    "fps": fps,
    "loop": name in LOOPS,
    "body_frac": H * BODY_FRAC / crop_h,          # 人物身高占帧高的比例
    "feet_frac": H * BOTTOM_MARGIN / crop_h,      # 脚底到帧底的距离占帧高的比例
}
if walk_speed:
    meta["speed"] = walk_speed                    # 每帧前进多少个身高（脚不打滑）
if moving:
    body_h = H * BODY_FRAC
    meta["root"] = [round(float(r - roots[0]) / body_h, 5) for r in roots]   # 相对第一帧移动了几个身高
    print(f"散步距离：{meta['root'][-1]:+.2f} 个身高")
(out_dir / "meta.json").write_text(json.dumps(meta))
print(f"已保存 {len(keyed)} 帧到 {out_dir}")


# ===== 5. 检查图 =====
picks = np.linspace(0, len(keyed) - 1, 6).round().astype(int)
tiles = [Image.open(out_dir / f"{i:04d}.png") for i in picks]
sheet = Image.new("RGBA", (sum(t.width for t in tiles) + 10 * 5, FRAME_H), (40, 50, 70, 255))
x = 0
for t in tiles:
    sheet.alpha_composite(t, (x, 0))
    x += t.width + 10
check_path = HERE / "anim" / f"check_{name}.png"
sheet.convert("RGB").save(check_path)
print("检查图：", check_path)
