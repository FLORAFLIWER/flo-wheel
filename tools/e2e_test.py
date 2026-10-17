"""端到端测试：启动程序 → 注入真实按键 → 截图 → 松开 → 收日志。

默认用**中键**而不是 X1：Windows 会过滤掉 SendInput 注入的 XBUTTON 事件
（见 tools/inject_mouse.py 的说明），而中键走的代码路径与侧键完全一样。

用法::

    python tools/e2e_test.py                  # 用中键测长按弹轮盘
    python tools/e2e_test.py --button x1      # 只用于人工实机测试
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SHOTS = ROOT / "_shots"
PY = sys.executable
LOGFILE = Path(os.environ.get("LOCALAPPDATA", "")) / "MouseWheel" / "logs" / "mousewheel.log"

ENV = dict(os.environ, PYTHONPATH=str(SRC), PYTHONIOENCODING="utf-8")
sys.path.insert(0, str(SRC))


def screenshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            "$vs=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
            "$bmp=New-Object System.Drawing.Bitmap $vs.Width,$vs.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($vs.Left,$vs.Top,0,0,$bmp.Size);"
            "$g.Dispose();"
            f"$bmp.Save('{path}',[System.Drawing.Imaging.ImageFormat]::Png);"
            "$bmp.Dispose()",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def inject(button: str, mode: str, hold_ms: int = 0) -> None:
    args = [PY, str(ROOT / "tools" / "inject_mouse.py"), "--button", button, f"--{mode}"]
    if mode == "hold":
        args += ["--hold", str(hold_ms)]
    subprocess.run(args, env=ENV, check=True, stdout=subprocess.DEVNULL)


def set_trigger(button: str) -> None:
    from mousewheel.config.store import ConfigStore

    store = ConfigStore()
    result = store.load()
    result.config.trigger.button = button
    store.save(result.config)
    print(f"触发键已设为 {button}（{store.path}）")


def tail(lines: int = 30) -> str:
    try:
        data = LOGFILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"<读取日志失败: {exc}>"
    return "\n".join(data[-lines:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--button", default="middle")
    parser.add_argument("--restore", action="store_true", help="测试结束后把触发键改回 x1")
    args = parser.parse_args(argv)

    set_trigger(args.button)

    out_file = SHOTS / "app_stdout.txt"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            [PY, "-m", "mousewheel", "--log-level", "DEBUG"],
            env=ENV,
            cwd=str(ROOT),
            stdout=fh,
            stderr=subprocess.STDOUT,
        )

    try:
        time.sleep(2.6)
        if proc.poll() is not None:
            print(f"! 程序提前退出，返回码 {proc.returncode}")
            print(tail(40))
            return 1

        print(f"注入 {args.button} 按下 …")
        inject(args.button, "down")
        time.sleep(0.9)
        hold_shot = SHOTS / "e2e_hold.png"
        screenshot(hold_shot)
        print(f"已截图 {hold_shot.name}")

        time.sleep(0.2)
        print(f"注入 {args.button} 松开 …")
        inject(args.button, "up")
        time.sleep(0.8)
        screenshot(SHOTS / "e2e_released.png")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if args.restore:
            set_trigger("x1")

    print("\n--- 日志（末尾） ---")
    print(tail(30))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
