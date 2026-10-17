"""把项目发布到 GitHub：创建仓库、上传代码、创建 Release 并附上 exe 压缩包。

不需要安装 git：直接走 GitHub REST API（Git Data API 生成一个完整 commit）。

需要一枚 Personal Access Token：
- 最省事：classic token，勾选 `repo`（能创建仓库 + 上传 Release）
- 页面上生成：https://github.com/settings/tokens/new?scopes=repo&description=FLO-Wheel

用法::

    python tools/publish_github.py --zip dist/FLO-Wheel-v0.1.0-win64.zip
    # token 从环境变量 GITHUB_TOKEN 读，读不到就提示输入（不回显）

    python tools/publish_github.py --token ghp_xxx --repo-name flo-wheel
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"

#: 不进入仓库的路径片段
IGNORE_DIRS = {
    "__pycache__", ".git", ".pytest_cache", ".venv", "venv",
    "build", "dist", ".idea", ".vscode",
}
IGNORE_SUFFIXES = {".pyc", ".pyo", ".log", ".spec", ".tmp"}
#: 这些只在本机有意义，不要进公开仓库
IGNORE_FILES = {
    "config.json",
    "portable.flag",
    "icon.png",
    "probe.png",
    "发布到GitHub.cmd",
}


class GitHubError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:400]}")
        self.status = status
        self.body = body


def request(method: str, path: str, token: str, payload=None, raw: bytes | None = None,
            content_type: str = "application/json"):
    url = path if path.startswith("http") else API + path
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "FLO-Wheel-Publisher",
    }
    data = None
    if raw is not None:
        data = raw
        headers["Content-Type"] = content_type
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise GitHubError(exc.code, body) from None


def collect_files() -> list[tuple[str, bytes]]:
    """按 .gitignore 的精神挑出要上传的文件。"""
    files: list[tuple[str, bytes]] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(ROOT)
            if path.suffix.lower() in IGNORE_SUFFIXES:
                continue
            if name in IGNORE_FILES:
                continue
            if name.startswith("icon_") and name.endswith(".png"):
                continue
            if path.stat().st_size > 2_000_000:  # 单文件 2MB 上限，防止误传大文件
                print(f"  跳过（超过 2MB）: {rel}")
                continue
            files.append((rel.as_posix(), path.read_bytes()))
    files.sort(key=lambda item: item[0])
    return files


def ensure_repo(token: str, owner: str, repo: str, description: str, private: bool) -> dict:
    try:
        status, data = request("GET", f"/repos/{owner}/{repo}", token)
        print(f"仓库已存在：{data['html_url']}")
        return data
    except GitHubError as exc:
        if exc.status != 404:
            raise
    print(f"创建仓库 {owner}/{repo} …")
    payload = {
        "name": repo,
        "description": description,
        "private": private,
        "has_issues": True,
        "has_wiki": False,
        "auto_init": False,
    }
    _, data = request("POST", "/user/repos", token, payload)
    print(f"已创建：{data['html_url']}")
    return data


def current_head(token: str, owner: str, repo: str, branch: str) -> str | None:
    try:
        _, data = request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token)
        return data["object"]["sha"]
    except GitHubError as exc:
        if exc.status in (404, 409):
            return None
        raise


def ensure_initial_commit(token: str, owner: str, repo: str, branch: str) -> str | None:
    """Git Data API 在**空仓库**上用不了（创建 blob 会 409 Git Repository is empty）。

    所以先用 Contents API 写一个 README 把仓库"点亮"，拿到第一个 commit 的 sha。
    """
    head = current_head(token, owner, repo, branch)
    if head:
        return head

    print("仓库还是空的，先创建一个初始提交 …")
    readme = ROOT / "README.md"
    content = readme.read_bytes() if readme.exists() else b"# FLO-Wheel\n"
    try:
        request(
            "PUT", f"/repos/{owner}/{repo}/contents/README.md", token,
            {
                "message": "chore: bootstrap repository",
                "content": base64.b64encode(content).decode("ascii"),
                "branch": branch,
            },
        )
    except GitHubError as exc:
        if exc.status not in (409, 422):
            raise
        print(f"  初始提交创建被拒绝（{exc.status}），继续尝试")
    return current_head(token, owner, repo, branch)


def commit_files(token: str, owner: str, repo: str, branch: str, message: str) -> str:
    files = collect_files()
    print(f"上传 {len(files)} 个文件 …")

    ensure_initial_commit(token, owner, repo, branch)

    tree = []
    for i, (rel, data) in enumerate(files, 1):
        _, blob = request(
            "POST", f"/repos/{owner}/{repo}/git/blobs", token,
            {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
        )
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        if i % 10 == 0 or i == len(files):
            print(f"  blob {i}/{len(files)}")

    _, tree_data = request("POST", f"/repos/{owner}/{repo}/git/trees", token, {"tree": tree})

    parent = ensure_initial_commit(token, owner, repo, branch)
    payload = {"message": message, "tree": tree_data["sha"], "parents": [parent] if parent else []}
    _, commit = request("POST", f"/repos/{owner}/{repo}/git/commits", token, payload)

    if parent:
        request("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{branch}", token,
                {"sha": commit["sha"], "force": False})
    else:
        request("POST", f"/repos/{owner}/{repo}/git/refs", token,
                {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    print(f"已提交 {commit['sha'][:8]} 到 {branch}")
    return commit["sha"]


def set_default_branch(token: str, owner: str, repo: str, branch: str) -> None:
    try:
        request("PATCH", f"/repos/{owner}/{repo}", token, {"default_branch": branch})
    except GitHubError:
        pass


def create_release(token: str, owner: str, repo: str, tag: str, name: str, body: str,
                   zip_path: Path | None) -> str:
    try:
        _, release = request("POST", f"/repos/{owner}/{repo}/releases", token, {
            "tag_name": tag,
            "name": name,
            "body": body,
            "draft": False,
            "prerelease": False,
        })
    except GitHubError as exc:
        if exc.status != 422:  # 422 = tag 已存在
            raise
        _, release = request("GET", f"/repos/{owner}/{repo}/releases/tags/{tag}", token)
        print(f"Release {tag} 已存在，复用")

    if zip_path and zip_path.exists():
        asset_name = zip_path.name
        existing = {a["name"] for a in release.get("assets", [])}
        if asset_name in existing:
            print(f"资产 {asset_name} 已存在，跳过上传")
        else:
            print(f"上传 {asset_name}（{zip_path.stat().st_size / 1024 / 1024:.1f} MB）…")
            url = f"{UPLOADS}/repos/{owner}/{repo}/releases/{release['id']}/assets?name={asset_name}"
            request("POST", url, token, raw=zip_path.read_bytes(),
                    content_type="application/zip")
            print("  上传完成")
    return release["html_url"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--repo-name", default="flo-wheel")
    parser.add_argument("--description", default="FLO 快捷轮盘：按住鼠标侧键弹出环形快捷菜单（Windows）")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--tag", default="v0.1.0")
    parser.add_argument("--zip", default="")
    parser.add_argument("--message", default="FLO 快捷轮盘 v0.1.0")
    parser.add_argument("--skip-upload", action="store_true", help="只创建 Release，不传代码")
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except GitHubError as exc:
        print()
        if exc.status == 401:
            print("✗ token 无效或已过期。请重新生成一个（注意别复制到多余的空格）。")
        elif exc.status == 403:
            print("✗ token 权限不够。生成时一定要勾选 `repo` 这一整项。")
        elif exc.status == 422:
            print("✗ 请求被拒绝（422）。通常是仓库名已被别的账号占用，换一个 --repo-name 再试。")
        else:
            print(f"✗ GitHub 返回错误：{exc}")
        return 1
    except urllib.error.URLError as exc:
        print(f"\n✗ 网络不通，无法连接 GitHub：{exc.reason}")
        return 1
    except KeyboardInterrupt:
        print("\n已取消。")
        return 1


def _run(args) -> int:
    token = args.token.strip()
    if not token:
        print("需要 GitHub Personal Access Token（勾选 repo 权限）。")
        print("生成地址：https://github.com/settings/tokens/new?scopes=repo&description=FLO-Wheel")
        print()
        try:
            token = getpass.getpass("粘贴 token 后按回车（输入时不显示）：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n没有输入 token，退出。")
            return 1
    if not token:
        print("没有 token，退出。")
        return 1

    _, user = request("GET", "/user", token)
    owner = user["login"]
    print(f"已登录：{owner}")

    repo_info = ensure_repo(token, owner, args.repo_name, args.description, args.private)
    if not args.skip_upload:
        commit_files(token, owner, args.repo_name, args.branch, args.message)
        set_default_branch(token, owner, args.repo_name, args.branch)

    zip_path = Path(args.zip) if args.zip else None
    if zip_path is not None and not zip_path.exists():
        print(f"! 找不到 {zip_path}，跳过上传安装包（代码仍然会传上去）")
        zip_path = None

    release_url = create_release(
        token, owner, args.repo_name, args.tag,
        f"FLO 快捷轮盘 {args.tag}",
        "Windows 10/11 免安装版。解压后双击 `FLO-Wheel.exe` 即可运行。\n\n"
        "首次运行会自动写入开机自启（可在 设置 → 关于 里关闭），"
        "配置保存在 `%APPDATA%\\MouseWheel\\`。",
        zip_path,
    )

    print("\n" + "=" * 62)
    print(f"仓库地址 : {repo_info['html_url']}")
    print(f"Release  : {release_url}")
    print("=" * 62)
    print("\n别忘了去 https://github.com/settings/tokens 删掉刚才那个 token。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
