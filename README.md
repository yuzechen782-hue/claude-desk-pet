# Claude 桌宠

一个陪你干活的 macOS 桌宠：Claude 坐在桌前敲电脑，偶尔起身续杯咖啡、活动筋骨；
头顶的小面板实时显示你的 **Claude 订阅 5 小时 / 每周用量**，她的状态也跟着用量变化。

![展示](docs/showcase.gif)

> 非官方粉丝项目，与 Anthropic 无关。

## 她会做什么

| 用量 | 她的状态 |
|---|---|
| 低于 50% | 不紧不慢地打字；时不时起身：续咖啡（晚上更常见）、活动筋骨、伸懒腰 |
| 50–80% | 更常"卡住了"：皱眉，起身踱两步想问题，想通了快步回来 |
| 80–95% | 埋头飞快地打字，不再起身 |
| 95% 以上 | 打瞌睡，趴在桌上睡着 |
| 额度重置 | 醒来，"好消息！"小小欢呼一下 |

- **单击她**：抬头看你，走过来挥挥手（1 分钟内一次）
- **拖动**：移动整个场景　**双击**：收起 / 显示面板　**右键**：刷新用量、打开 claude.ai 用量页、退出
- 所有动作都从同一个坐姿开始、回到同一个坐姿，并且只在姿势对上时才切换，衔接处不会跳。

## 用量数据从哪来

Claude Code 每次回复后，会把订阅额度（`rate_limits`）交给状态栏脚本 `statusline.py`，
脚本把它写进 `usage.json`，桌宠读这个文件。

- Claude App 和 Claude Code **共用同一个额度池**，但数字只在 Claude Code 回复时刷新；
  平时主要用 App 的话，右键 →「刷新用量」会打开终端，用 Haiku 发一句很短的话来刷新（会用掉一点点额度）。
- 重置倒计时是本地实时计算的。
- 需要 Claude **Pro / Max 订阅**，并且 Claude Code 用订阅账号登录（`/status` 里不能是 API key）。

## 安装（macOS）

需要：macOS、Python 3.10+、[Claude Code](https://code.claude.com)。

```bash
git clone https://github.com/yuzechen782-hue/claude-desk-pet.git
cd claude-desk-pet

# 1. 登记状态栏脚本（会先备份 ~/.claude/settings.json）
python3 install.py

# 2. 打开 claude，随便发一句话，usage.json 就有数据了
claude

# 3. 双击 start.command 启动
#    第一次会自动建虚拟环境、装依赖、从 anim/ 的视频切帧，要等几分钟
```

想要桌面图标：`.venv/bin/python make_app.py`，桌面会出现「Claude 桌宠.app」，双击启动、不开终端。
开机自启：系统设置 → 通用 → 登录项 → 加上这个 App。

## 文件说明

| 文件 | 作用 |
|---|---|
| `pet.py` | 桌宠本体 |
| `statusline.py` / `install.py` | 读取订阅用量的状态栏脚本 / 把它登记到 Claude Code |
| `video_to_frames.py` / `build_assets.sh` | 绿幕视频 → 透明帧（去重复帧、自动对齐、量身高） |
| `make_app.py` | 生成桌面 App |
| `make_showcase.py` | 把所有动画串成展示视频和 GIF |
| `make_base.py` / `make_scene.py` | （可选）用自己的 API key 重新生成底图和动画 |
| `anim/` | 动画源视频（绿幕） |

## 重新生成动画（可选）

`make_scene.py` 通过 [fal](https://fal.ai) 调用 Seedance 2.0 图生视频，需要自己的 `FAL_KEY`。
提醒：同一个模型，不同平台价格差很多——fal 上 720p 约 0.30 美元/秒，
字节官方的火山引擎大约 1 元人民币/秒，便宜一半左右。

## 致谢与授权

- **设计与制作**：Asuna
- **角色原画**：[ai-chan-sheets](https://github.com/lmy414/ai-chan-sheets)，作者 胖次狐（ZipZipPipe），整理 lmy414
- **动画生成**：Seedance 2.0（ByteDance）

代码以 **MIT** 协议发布（见 `LICENSE`）。
所有图片和视频改编自上述原画，以 **CC BY-NC-SA 4.0** 发布（见 `LICENSE-ASSETS.md`）：需署名、不得商用、改编需以相同协议共享。
