# 鼠标轮盘 (MouseWheel) · 设计规格

一个 Windows 11 托盘常驻小工具：按住鼠标侧键 → 光标旁弹出环形菜单 → 划到扇区 → 松手执行。
每个扇区可绑定快捷键、文本、程序、网址、媒体键或系统动作。开机自启动。

## 1. 目标 / 非目标

**目标**
- 按住触发键 ≥ `long_press_ms`（默认 180ms）立即弹出轮盘，移动选择，松手执行
- 快击触发键 (< `long_press_ms`) 保留系统原有功能（如 X1 = 浏览器后退），自动重放真实点击
- 触发键、扇区内容、外观、行为全部可在设置界面自定义，改完立即生效
- 开机静默自启动（当前用户，普通权限，无 UAC）
- 全程不抢前台焦点：动作永远发给触发前的前台窗口

**非目标（明确不做）**
- 不支持以管理员身份自启，也不解决"给管理员窗口发按键"（UIPI 限制，会在界面提示）
- 不支持独占全屏游戏内的稳定工作（提供托盘暂停开关）
- 不做云同步、账号、遥测

## 2. 交互规格

| 项 | 默认 | 范围 / 说明 |
|---|---|---|
| 触发键 `trigger.button` | `x1` | `x1` `x2` `middle` `right` `left` `none`(仅键盘) |
| 键盘触发 `trigger.key` | 空 | 组合键，如 `Ctrl+Alt+Space`；与鼠标键可同时启用 |
| 触发模式 `trigger.mode` | `hold` | `hold`（按住拖动）/ `toggle`（按一下开，再按一下关） |
| 长按阈值 | 180 ms | 80–600 |
| 快击放行 | 开 | 关闭则触发键完全被接管，原有功能失效 |
| 扇区数 | 8 | 4 / 6 / 8 / 12 |
| 内径 / 外径 | 72 / 230 px | 逻辑像素，按屏幕 DPI 换算 |
| 死区 | 24 px | 光标离中心小于此值不选中 |
| 出现位置 | 光标处 | 可改屏幕中心 |
| 动画 | 120 ms 淡入 + 0.9→1.0 | 0 = 关闭 |
| 取消 | Esc / 回死区松手 | 回死区松手 = 什么都不执行 |
| 多屏 | 跟随光标所在屏幕 | Per-Monitor V2 |
| 快速连按 | 忽略松开后 40ms 内的重复 down | 防抖动误触 |

视觉：深色圆环（默认 `#1B1D22E6` / 主色 `#4C8DFF`），选中扇区填充主色并 1.04 倍放大，
扇区文字居中偏外，轮盘中心显示当前选中项名称。

## 3. 架构

```
hook thread (ctypes, WH_MOUSE_LL / WH_KEYBOARD_LL)
   │ 只做：读消息 → 打标记过滤 → 丢进 Qt 队列（不画、不 IO、不 SendInput）
   ▼
UI thread (Qt)
   TriggerController ── 长按/快击/切换 状态机
        ├─ WheelOverlay  ── 16ms 轮询光标，geometry 命中 → 重绘
        └─ ActionRunner  ── 线程池执行，SendInput 前校正前台窗口
```

**铁律**
1. 钩子回调里绝不调用 `SendInput`（会重入），一律投递到 UI 线程
2. 钩子回调里绝不做耗时操作（超 `LowLevelHooksTimeout` 会被系统静默摘钩）
3. 注入事件统一带 `dwExtraInfo = 0x1CEB00DA`，钩子见到即放行，避免自吞
4. 轮盘窗口 `WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW`，不抢焦点不吃点击

## 4. 模块

| 模块 | 职责 |
|---|---|
| `platform/win/winapi.py` | ctypes 常量、结构体、函数原型 |
| `platform/win/dpi.py` | Per-Monitor V2 声明（Qt 初始化前） |
| `platform/win/single_instance.py` | 命名 Mutex + 本机 TCP 唤醒已运行实例 |
| `platform/win/autostart.py` | HKCU Run 注册/注销/读回校验 |
| `input/mouse_hook.py` | WH_MOUSE_LL 线程，只投递事件 |
| `input/key_hook.py` | WH_KEYBOARD_LL 线程，供热键录制使用 |
| `input/trigger.py` | 纯逻辑状态机（可单测，不依赖 Qt） |
| `input/inject.py` | SendInput：按键序列、文本、鼠标点击重放 |
| `input/hotkey_spec.py` | `"Ctrl+Shift+S"` ⇄ VK 序列 |
| `wheel/geometry.py` | 角度→扇区、死区、滞回（纯函数，可单测） |
| `wheel/renderer.py` | QPainter 绘制圆环 |
| `wheel/overlay.py` | 透明窗口 + 生命周期 + 光标轮询 |
| `config/model.py` | dataclass 模型 + 版本迁移 |
| `config/store.py` | 原子写、备份、损坏回退 |
| `actions/*` | 动作实现，注册表按 `type` 分派 |
| `ui/tray.py` | 托盘：暂停/设置/重载/退出 |
| `ui/settings_window.py` | 扇区表 + 预览 + 外观 + 自启动 |
| `ui/hotkey_recorder.py` | 按键录制控件 |
| `ui/sector_editor.py` | 单扇区编辑对话框 |

## 5. 配置

位置 `%APPDATA%\MouseWheel\config.json`（exe 同目录存在 `portable.flag` 时改为便携模式），
UTF-8，原子写（`.tmp` + `os.replace`），每次保存前备份为 `config.json.bak`，最多保留 5 份。

```json
{
  "schema": 1,
  "trigger": {
    "button": "x1",
    "key": "",
    "mode": "hold",
    "long_press_ms": 180,
    "fast_click_passthrough": true
  },
  "wheel": {
    "sectors": 8,
    "inner_radius": 72,
    "outer_radius": 230,
    "dead_zone": 24,
    "animate_ms": 120,
    "center_on": "cursor",
    "theme": { "bg": "#1B1D22E6", "accent": "#4C8DFF", "text": "#FFFFFF", "border": "#FFFFFF33" }
  },
  "pages": [
    {
      "name": "main",
      "items": [
        { "label": "复制", "icon": "copy", "action": { "type": "hotkey", "keys": "Ctrl+C" } }
      ]
    }
  ],
  "startup": { "enabled": true, "delay_s": 5 }
}
```

动作类型（`action.type`）：

| type | 字段 | 说明 |
|---|---|---|
| `hotkey` | `keys`, `repeat`(默认1), `delay_ms`(默认15) | 组合键，支持 `Win+Shift+S` |
| `text` | `text`, `restore_clipboard`(默认true) | 走剪贴板粘贴，中文稳定 |
| `launch` | `path`, `args`[], `cwd` | 程序/文件/文件夹/URI |
| `url` | `url` | 默认浏览器 |
| `media` | `key`, `repeat` | VOLUME_UP/DOWN/MUTE/PLAY_PAUSE/NEXT/PREV |
| `system` | `cmd` | lock / screenshot / sleep / showdesktop / taskmgr / explorer |
| `script` | `command`, `shell`(pwsh/cmd), `hidden` | 执行脚本 |
| `none` | — | 空扇区（仅显示） |

## 6. 开机自启动

- 只使用 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，值名 `MouseWheel`，
  数据 `"<exe 路径>" --autostart`
- `--autostart`：延迟 `startup.delay_s` 秒（默认 5）后进入托盘，不显示窗口
- 每次启动校验注册表值与自身真实路径，不一致自动修正（防"以为自启了其实失效"）
- 设置页开关读回真实注册表状态，而不是只记布尔值

## 7. 验收标准

1. 按住 X1 180ms 内无窗口；超时后轮盘出现在光标处，透明度正常，8 扇区正确渲染
2. 划到不同扇区高亮正确（8/12 扇区边界误差 < 1°），死区内不选中
3. 松手执行动作；Esc 取消；回死区松手不执行
4. 快击 X1 → 浏览器后退仍然工作，且不会残留 modifier
5. 轮盘显示期间前台窗口标题不变（不抢焦点）
6. 两个 2560 宽显示器上，各自 DPI 下轮盘尺寸与位置正确
7. 设置里换触发键/扇区内容 → 保存后立即生效，无需重启
8. 重启电脑后 5–8 秒内托盘出现，钩子可用
9. 钩子回调平均耗时 < 1ms（日志记录最大值）
10. `python -m pytest` 全绿

## 8. 进度

- [x] 环境：独立 venv（`%LOCALAPPDATA%\MouseWheel\venv`），不污染 DSH 运行时
- [x] **M0** Win32 底座、鼠标钩子线程、触发状态机、透明轮盘窗口、几何命中
- [x] **M1** 配置驱动 + 8 种动作 + SendInput 注入 + 快击放行
- [x] **M2** 设置窗口（扇区/触发/外观/关于）+ 托盘 + 热键录制
- [x] **M3** 注册表自启动 + 单实例 + 打包（onedir 96.7MB）+ 安装 + 快捷方式
- [x] 单元测试 49 项全绿；端到端脚本 `tools/e2e_test.py` 验证整条链路
- [ ] M4 动画精修、多页翻页、按前台程序切换配置、图标库（后续）

### 实测记录

| 项 | 结果 |
|---|---|
| 钩子安装 | 成功，回调平均耗时 < 0.1ms |
| 长按 180ms 弹轮盘 | 通过（注入中键 → 日志「轮盘弹出」） |
| 打包版启动 | 通过（96.7MB onedir，无控制台） |
| 开机自启动写入 | 通过（HKCU Run 已生效） |
| 注入 XBUTTON 模拟侧键 | **不可行** —— Windows 过滤注入的 XBUTTON，侧键须人工实测 |
