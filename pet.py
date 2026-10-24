# Claude 娘桌宠（小场景版）：她坐在桌前工作，偶尔起身走走；面板显示订阅的 5 小时 / 每周用量
# 用量数据来自 usage.json（由 statusline.py 在你使用 Claude Code 时写入）
# 立绘：ai-chan-sheets（作者 胖次狐 ZipZipPipe，整理 lmy414），CC BY-NC-SA 4.0
import json
import random
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QRect
from PySide6.QtGui import QPainter, QPixmap, QColor, QFont, QPainterPath, QPen, QRegion, QAction
from PySide6.QtWidgets import QApplication, QWidget, QMenu

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
USAGE_FILE = HERE / "usage.json"

# ===== 尺寸 =====
SCENE_W = 600               # 场景显示宽度（像素）；高度按视频比例（上方留了她站起来的空间）
PANEL_W, PANEL_H = 236, 122
GAP = 6
TICK = 16                   # 每帧毫秒数（约 60 帧/秒）
FADE = 0.2                  # 两段动画衔接处的淡入时间（秒）

# 场景动画（由 make_scene.py 生成，video_to_frames.py 切帧）
LOOP_CLIPS = ["type", "type_fast", "sleep"]
ONCE_CLIPS = ["stretch", "doze", "wake", "coffee", "think", "exercise", "notice", "good_news"]

# ===== 颜色 =====
CLAY = QColor("#D97757")     # Claude 橙
INK = QColor("#3D2B22")
MUTED = QColor("#9A8478")
PANEL_BG = QColor(255, 250, 245, 238)
BAR_BG = QColor("#F0E2D8")

# ===== 台词 =====
LINES = {
    "smile": ["今天也一起加油吧～", "额度还很充足哦", "有什么想聊的吗？"],
    "serious": ["已经用掉一半多了，悠着点", "重要的问题留给我吧"],
    "pout": ["快见底了……我得抓紧干活", "再聊下去我要罢工了哦"],
    "sad": ["呜……额度用光了，我先睡会儿", "等重置再叫醒我吧"],
    "calm": ["还不知道你的用量呢", "右键 → 刷新用量，就能告诉我啦"],
}
STALE_LINE = "数字有点旧了，右键可以刷新哦"


def make_font(size, bold=False):
    f = QFont()
    f.setFamilies(["PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI"])
    f.setPixelSize(size)
    f.setBold(bold)
    return f


def fmt_left(sec):
    sec = int(sec)
    if sec <= 0:
        return "已重置"
    d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    if d:
        return f"{d}天{h}小时后重置"
    if h:
        return f"{h}小时{m}分后重置"
    return f"{max(m, 1)}分钟后重置"


def fmt_ago(sec):
    sec = int(sec)
    if sec < 60:
        return "刚刚更新"
    if sec < 3600:
        return f"{sec // 60}分钟前更新"
    if sec < 86400:
        return f"{sec // 3600}小时前更新"
    return f"{sec // 86400}天前更新"


def face_for(pct):
    if pct is None:
        return "calm"
    if pct >= 95:
        return "sad"
    if pct >= 80:
        return "pout"
    if pct >= 50:
        return "serious"
    return "smile"


class Pet(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.NoDropShadowWindowHint    # Mac 会给窗口画阴影边框，关掉
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Mac 上 Tool 窗口在程序失去焦点时会自动隐藏，这里让它一直显示
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        # ----- 头像表情 -----
        self.faces = {}
        for name in ("smile", "calm", "surprised", "shy", "pout", "laugh", "serious", "sad"):
            self.faces[name] = QPixmap(str(ASSETS / f"face_{name}.png"))

        # ----- 场景动画 -----
        self.dpr = 2.0
        self.clips = {}
        for name in LOOP_CLIPS + ONCE_CLIPS:
            clip = self.load_clip(name)
            if clip:
                self.clips[name] = clip
                print(f"动画 {name}：{len(clip['frames'])} 帧")
        if "type" not in self.clips:
            sys.exit("还没有打字动画：先生成并切帧 type（见 make_scene.py）")

        first = self.clips["type"]["frames"][0]
        self.scene_h = round(SCENE_W * first.height() / first.width())
        self.win_w = SCENE_W
        self.win_h = PANEL_H + GAP + self.scene_h
        self.setFixedSize(self.win_w, self.win_h)
        self.scene_rect = QRectF(0, PANEL_H + GAP, SCENE_W, self.scene_h)

        # ----- 状态 -----
        self.t = 0
        self.usage = {}
        self.usage_mtime = 0

        self.loop = "type"            # 当前循环：type / type_fast / sleep
        self.loop_start = time.time()
        self.anim = None              # 正在播放的一次性片段：{"name", "start", "then"}
        self.pending = None           # 等循环播到结尾（回到底图姿势）再执行的下一步
        self.next_break = time.time() + random.uniform(25, 60)   # 下次起身活动的时间

        self.last_drawn = None
        self.fade_from = None
        self.fade_start = 0.0

        self.temp_face = None
        self.temp_face_until = 0
        self.speech = ""
        self.speech_until = 0
        self.panel_on = True
        self.seen_resets = set()
        self.last_notice = 0
        self.story_queue = []         # 排队等着播的剧情（比如重置时她正在忙）
        self.press_pos = None
        self.dragged = False

        # 放在屏幕右下角
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.win_w - 20, screen.bottom() - self.win_h)

        self.load_usage()
        self.say("你好呀，我是 Claude 娘～" if self.usage else LINES["calm"][1], 6)
        self.update_mask()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK)

    # ===== 读取动画 =====
    def load_clip(self, name):
        folder = ASSETS / name
        meta_path = folder / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text())
        if not meta.get("scene"):
            return None                      # 旧版（全身立绘）的帧，不用
        frames = []
        for path in sorted(folder.glob("*.png")):
            pm = QPixmap(str(path))
            pm = pm.scaledToWidth(int(SCENE_W * self.dpr), Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(self.dpr)
            frames.append(pm)
        if not frames:
            return None
        return {"frames": frames, "fps": meta["fps"]}

    # ===== 切换动作 =====
    def begin_fade(self):
        self.fade_from = self.last_drawn
        self.fade_start = time.time()

    def start_loop(self, name):
        if name not in self.clips:
            name = "type"
        self.begin_fade()
        self.loop = name
        self.anim = None
        self.loop_start = time.time()

    def play(self, name, then):
        """播放一次性片段，播完执行 then；没有这段动画就直接执行 then"""
        if name not in self.clips:
            then()
            return
        self.begin_fade()
        self.anim = {"name": name, "start": time.time(), "then": then}

    def loop_position(self):
        clip = self.clips[self.loop]
        return (time.time() - self.loop_start) * clip["fps"] % len(clip["frames"])

    def at_loop_end(self):
        """循环是否播到最后一帧附近（此时姿势和底图一样，适合衔接下一段）"""
        n = len(self.clips[self.loop]["frames"])
        return self.loop_position() >= n - 1.5

    def back_to_work(self):
        self.start_loop(self.work_loop())
        self.next_break = time.time() + random.uniform(25, 60)

    # ===== 用量 =====
    def load_usage(self):
        try:
            mtime = USAGE_FILE.stat().st_mtime
        except FileNotFoundError:
            return
        if mtime == self.usage_mtime:
            return
        self.usage_mtime = mtime
        try:
            self.usage = json.loads(USAGE_FILE.read_text())
        except Exception:
            return
        if self.t > 0:
            self.say("用量更新啦", 4)

    def window_info(self, key):
        """返回 (百分比 或 None, 剩余秒数 或 None)"""
        w = self.usage.get(key)
        if not w:
            return None, None
        left = (w.get("resets_at") or 0) - time.time()
        if w.get("resets_at") and left <= 0:
            return None, 0            # 已过重置时间，旧百分比作废
        return w.get("used_percentage"), left if w.get("resets_at") else None

    def usage_level(self):
        pcts = [p for p in (self.window_info("five_hour")[0], self.window_info("seven_day")[0])
                if p is not None]
        return max(pcts) if pcts else None

    def work_loop(self):
        """按用量决定她怎么干活：正常打字 / 拼命打字 / 睡觉"""
        level = self.usage_level()
        if level is not None and level >= 95 and "sleep" in self.clips:
            return "sleep"
        if level is not None and level >= 80 and "type_fast" in self.clips:
            return "type_fast"
        return "type"

    def current_face(self):
        if self.temp_face and time.time() < self.temp_face_until:
            return self.temp_face
        return face_for(self.usage_level())

    def check_resets(self):
        for key in ("five_hour", "seven_day"):
            w = self.usage.get(key)
            if not w or not w.get("resets_at"):
                continue
            mark = (key, w["resets_at"])
            if time.time() >= w["resets_at"] and mark not in self.seen_resets:
                self.seen_resets.add(mark)
                if time.time() - w["resets_at"] < 120:     # 刚刚重置才庆祝
                    name = "5 小时" if key == "five_hour" else "每周"
                    self.set_face("laugh", 6)
                    self.say(f"{name}额度重置啦！", 6)
                    self.queue_story("good_news", wait=True)

    def is_stale(self):
        upd = self.usage.get("updated_at")
        return upd is not None and time.time() - upd > 3 * 3600

    # ===== 小工具 =====
    def say(self, text, seconds=4):
        self.speech = text
        self.speech_until = time.time() + seconds

    def set_face(self, name, seconds):
        self.temp_face = name
        self.temp_face_until = time.time() + seconds

    def update_mask(self):
        """只有场景和面板能点到，别的地方鼠标穿透"""
        region = QRegion(self.scene_rect.toRect())
        if self.panel_on:
            region = region.united(QRegion(QRect(self.win_w - PANEL_W, 0, PANEL_W, PANEL_H)))
        self.setMask(region)

    # ===== 每帧 =====
    def tick(self):
        self.t += 1
        if self.t % 190 == 0:          # 每 3 秒看一次用量文件
            self.load_usage()
        if self.t % 62 == 0:
            self.check_resets()
        self.update_behavior()
        self.update()

    def update_behavior(self):
        now = time.time()

        # ----- 一次性片段：播完执行下一步 -----
        if self.anim:
            clip = self.clips[self.anim["name"]]
            if (now - self.anim["start"]) * clip["fps"] >= len(clip["frames"]):
                self.anim["then"]()
            return

        # ----- 有等着执行的动作：等循环回到底图姿势 -----
        if self.pending:
            if self.at_loop_end():
                action = self.pending
                self.pending = None
                action()
            return

        wanted = self.work_loop()

        # 排队的剧情（睡觉时等醒来再说）
        if self.story_queue and self.loop in ("type", "type_fast") and wanted != "sleep":
            self.queue_story(self.story_queue.pop(0))
            return

        # 用量到了 95%：打瞌睡 → 睡觉
        if wanted == "sleep" and self.loop != "sleep":
            self.pending = lambda: self.play("doze", then=lambda: self.start_loop("sleep"))
            self.say(random.choice(LINES["sad"]), 5)
            return

        # 用量降下来了（重置或刷新）：醒来 → 回去干活
        if self.loop == "sleep" and wanted != "sleep":
            self.pending = lambda: self.play("wake", then=self.back_to_work)
            return

        # 正常打字 ↔ 拼命打字（两段都从底图开始，循环结尾直接换）
        if self.loop != wanted:
            self.pending = lambda: self.start_loop(wanted)
            return

        # 工作一阵子，做点别的（拼命打字时不起身，只偶尔伸个懒腰）
        if self.loop in ("type", "type_fast") and now >= self.next_break:
            activity = self.pick_break()
            self.pending = lambda: self.play(activity, then=self.back_to_work)
            self.next_break = now + 9999        # 等 back_to_work 重新排

    def pick_break(self):
        """按情况挑一段小剧情"""
        if self.loop == "type_fast":
            return "stretch"
        level = self.usage_level()
        hour = time.localtime().tm_hour
        weights = {"stretch": 2, "exercise": 2, "coffee": 2, "think": 1}
        if hour >= 21 or hour < 6:
            weights["coffee"] = 5              # 晚上更想喝咖啡
        if level is not None and 50 <= level < 80:
            weights["think"] = 5               # 用量过半：问题难，在拼命想
        names = [n for n in weights if n in self.clips] or ["stretch"]
        return random.choices(names, [weights[n] for n in names])[0]

    def queue_story(self, name, wait=False):
        """插队播放一段剧情（等当前循环回到底图姿势）。
        正在播别的或在睡觉时：wait=True 就排队等会儿再播，否则放弃"""
        if name not in self.clips:
            return False
        if self.anim or self.pending or self.loop == "sleep":
            if wait and name not in self.story_queue:
                self.story_queue.append(name)
            return False
        self.pending = lambda: self.play(name, then=self.back_to_work)
        return True

    # ===== 绘制 =====
    def current_frame(self):
        if self.anim:
            clip = self.clips[self.anim["name"]]
            i = int((time.time() - self.anim["start"]) * clip["fps"])
            return clip["frames"][min(i, len(clip["frames"]) - 1)]
        return self.clips[self.loop]["frames"][int(self.loop_position())]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        if self.panel_on:
            self.draw_panel(p)

        current = self.current_frame()
        fade = (time.time() - self.fade_start) / FADE
        if self.fade_from is not None and fade < 1:
            # 衔接：旧画面完整画出，新画面在上面淡入
            p.drawPixmap(self.scene_rect, self.fade_from, QRectF(self.fade_from.rect()))
            p.setOpacity(fade)
        p.drawPixmap(self.scene_rect, current, QRectF(current.rect()))
        p.setOpacity(1.0)
        self.last_drawn = current

    def draw_panel(self, p):
        x0 = self.win_w - PANEL_W
        rect = QRectF(x0 + 1, 1, PANEL_W - 2, PANEL_H - 2)
        p.setPen(QPen(CLAY, 1.5))
        p.setBrush(PANEL_BG)
        p.drawRoundedRect(rect, 14, 14)

        # 头像
        face = self.current_face()
        av = QRectF(x0 + 12, 16, 58, 58)
        clip = QPainterPath()
        clip.addEllipse(av)
        p.save()
        p.setClipPath(clip)
        p.drawPixmap(av, self.faces[face], QRectF(self.faces[face].rect()))
        p.restore()
        p.setPen(QPen(CLAY, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(av)

        # 两条用量
        bx, bw = x0 + 80, PANEL_W - 92
        self.draw_bar(p, bx, 10, bw, "5 小时", *self.window_info("five_hour"))
        self.draw_bar(p, bx, 54, bw, "本周", *self.window_info("seven_day"))

        # 底部一行：台词 或 更新时间
        p.setFont(make_font(11))
        if time.time() < self.speech_until:
            p.setPen(INK)
            text = self.speech
        else:
            upd = self.usage.get("updated_at")
            p.setPen(CLAY if self.is_stale() else MUTED)
            text = fmt_ago(time.time() - upd) if upd else "还没有数据，右键 → 刷新用量"
        p.drawText(QRectF(x0 + 10, 97, PANEL_W - 20, 20), Qt.AlignmentFlag.AlignCenter, text)

    def draw_bar(self, p, x, y, w, label, pct, left):
        p.setFont(make_font(11, bold=True))
        p.setPen(INK)
        p.drawText(QRectF(x, y, w, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        p.drawText(QRectF(x, y, w, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   "—" if pct is None else f"{pct:.0f}%")

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BAR_BG)
        p.drawRoundedRect(QRectF(x, y + 17, w, 6), 3, 3)
        if pct:
            color = CLAY if pct < 80 else QColor("#C2410C") if pct < 95 else QColor("#B91C1C")
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, y + 17, w * min(pct, 100) / 100, 6), 3, 3)

        p.setFont(make_font(10))
        p.setPen(MUTED)
        if left is None and pct is None:
            sub = ""
        elif left == 0:
            sub = "已重置，等待刷新"
        else:
            sub = fmt_left(left) if left is not None else ""
        p.drawText(QRectF(x, y + 25, w, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)

    # ===== 鼠标：拖动整个场景；单击互动；双击收起面板；右键菜单 =====
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.press_pos = e.globalPosition().toPoint() - self.pos()
            self.press_global = e.globalPosition().toPoint()
            self.dragged = False

    def mouseMoveEvent(self, e):
        if self.press_pos is None:
            return
        g = e.globalPosition().toPoint()
        if (g - self.press_global).manhattanLength() > 4:
            self.dragged = True
        if self.dragged:
            self.move(g - self.press_pos)

    def mouseReleaseEvent(self, e):
        if self.press_pos is not None and not self.dragged:
            self.on_click()
        self.press_pos = None

    def mouseDoubleClickEvent(self, e):
        self.toggle_panel()

    def toggle_panel(self):
        self.panel_on = not self.panel_on
        self.update_mask()

    def on_click(self):
        mood = self.current_face()
        self.set_face("shy", 1.5)
        # 她注意到你：抬头、走过来挥挥手（1 分钟内只演一次）
        if time.time() - self.last_notice > 60 and self.queue_story("notice"):
            self.last_notice = time.time()
        self.say(STALE_LINE if self.is_stale() else random.choice(LINES.get(mood, LINES["smile"])), 4)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        items = [
            ("刷新用量（打开 Claude Code 发一句话）", self.refresh_via_claude),
            ("打开 claude.ai 用量页面", lambda: webbrowser.open("https://claude.ai/settings/usage")),
            ("隐藏面板" if self.panel_on else "显示面板", self.toggle_panel),
            ("退出", QApplication.quit),
        ]
        for text, fn in items:
            act = QAction(text, menu)
            act.triggered.connect(lambda _=False, f=fn: f())
            menu.addAction(act)
        menu.exec(e.globalPos())

    def refresh_via_claude(self):
        """在终端里打开 Claude Code，用 Haiku 发一句很短的话；回复后状态栏脚本就会写入最新用量"""
        cmd = "claude --model haiku '只回复 ok 两个字母'"
        if sys.platform == "darwin":
            subprocess.Popen(["osascript",
                              "-e", f'tell application "Terminal" to do script "{cmd}"',
                              "-e", 'tell application "Terminal" to activate'])
            self.say("等它回复完，关掉终端就好～", 6)
        else:
            self.say("请在终端运行：" + cmd, 8)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = Pet()
    pet.show()
    sys.exit(app.exec())
