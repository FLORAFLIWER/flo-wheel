@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   FLO 快捷轮盘 - 发布到 GitHub
echo ============================================================
echo.
echo 接下来会提示你粘贴 Personal Access Token（输入时不显示，属正常）。
echo 如果没有 token，先去生成一个（勾选 repo 权限）：
echo   https://github.com/settings/tokens/new?scopes=repo&description=FLO-Wheel
echo.
pause

set "PY=%LOCALAPPDATA%\MouseWheel\venv\Scripts\python.exe"
set "ZIP=%LOCALAPPDATA%\MouseWheel\build\dist\FLO-Wheel-v0.1.0-win64.zip"

if not exist "%PY%" (
  echo [错误] 找不到 Python 环境：%PY%
  goto end
)

"%PY%" tools\publish_github.py --zip "%ZIP%"

:end
echo.
echo ============================================================
echo 以上输出可以整段复制发给助手，我帮你核对结果。
echo ============================================================
pause
