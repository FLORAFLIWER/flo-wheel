"""配置读写：原子写 + 备份 + 损坏自愈。

写文件用 ``临时文件 → os.replace``，避免程序被强杀时留下半截 JSON。
每次保存前把旧文件轮转成 ``config.json.bak``、``.bak2``…最多保留 5 份。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from . import defaults
from .model import AppConfig

__all__ = ["ConfigStore", "LoadResult", "ConfigError"]

MAX_BACKUPS = 5


class ConfigError(OSError):
    pass


@dataclass
class LoadResult:
    config: AppConfig
    created: bool = False
    recovered: bool = False
    warnings: list[str] = field(default_factory=list)


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else paths.config_path()

    # ---- 读 --------------------------------------------------------------

    def load(self) -> LoadResult:
        if not self.path.exists():
            cfg = defaults.default_config()
            result = LoadResult(config=cfg, created=True)
            try:
                self.save(cfg)
            except ConfigError as exc:
                result.warnings.append(f"无法写入默认配置：{exc}")
            return result

        try:
            raw_text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            return LoadResult(
                config=defaults.default_config(),
                recovered=True,
                warnings=[f"读取配置失败，已回退默认值：{exc}"],
            )

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            self._quarantine()
            return LoadResult(
                config=defaults.default_config(),
                recovered=True,
                warnings=[f"配置文件损坏（{exc}），已另存并恢复默认值"],
            )

        result = LoadResult(config=AppConfig.from_dict(data))
        if isinstance(data, dict) and data.get("schema") != AppConfig().schema:
            result.warnings.append(
                f"配置来自 schema {data.get('schema')}，已升级到 {AppConfig().schema}"
            )
        return result

    # ---- 写 --------------------------------------------------------------

    def save(self, config: AppConfig) -> None:
        config.normalize()
        data = config.to_dict()
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if self.path.exists():
            self._rotate_backups()

        fd, tmp_name = tempfile.mkstemp(
            prefix="cfg-", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
        except OSError as exc:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise ConfigError(f"保存配置失败：{exc}") from exc

    # ---- 内部 ------------------------------------------------------------

    def _rotate_backups(self) -> None:
        try:
            for i in range(MAX_BACKUPS - 1, 0, -1):
                src = self.path.with_name(self.path.name + (".bak" if i == 1 else f".bak{i}"))
                if not src.exists():
                    continue
                dst = self.path.with_name(f"{self.path.name}.bak{i + 1}")
                if i + 1 > MAX_BACKUPS:
                    src.unlink(missing_ok=True)
                else:
                    os.replace(src, dst)
            shutil.copy2(self.path, self.path.with_name(self.path.name + ".bak"))
        except OSError:
            # 备份失败不该阻断保存
            pass

    def _quarantine(self) -> None:
        try:
            os.replace(self.path, self.path.with_name(self.path.name + ".broken"))
        except OSError:
            pass
