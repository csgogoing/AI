"""智能体第二步: 并发执行 tests/generated/Script 下所有冒烟测试脚本。"""
import importlib.util
import os
import subprocess
import sys

from agent.generator import GENERATED_DIR


def _resolve_chromium_path() -> str | None:
    """优先使用系统自带 chromium, 避免依赖 playwright 浏览器下载。"""
    for candidate in ("/usr/local/bin/chromium", "/usr/bin/chromium",
                      "/usr/bin/chromium-browser"):
        if os.path.exists(candidate):
            return candidate
    return None


def build_pytest_cmd(workers: str | int | None) -> list[str]:
    """构造 pytest 命令: 自动禁用干扰插件, 可选并发 (-n) 加速。"""
    cmd = [sys.executable, "-m", "pytest"]
    # 禁用会干扰 Playwright Sync API 的 asyncio 类插件 (装有才禁用, 避免误伤)
    for plugin in ("anyio", "asyncio", "trio"):
        if importlib.util.find_spec(plugin):
            cmd += ["-p", f"no:{plugin}"]
    # 并发执行 (需要 pytest-xdist): auto=按 CPU 核数, 数字=指定 worker 数
    if workers is not None and workers not in ("", 1, "1"):
        cmd += ["-n", str(workers)]
    cmd += ["Script", "-v", "--tb=short"]
    return cmd


def run_all_tests(base_url: str, workers: str | int | None = None,
                  timeout: int = 600) -> tuple[int, str]:
    """在 tests/generated 下并发执行 pytest Script (自动收集所有 test_*.py)。

    返回 (pytest 退出码, 完整输出)。
    """
    env = os.environ.copy()
    env["SMOKE_BASE_URL"] = base_url
    chromium = _resolve_chromium_path()
    if chromium:
        env["CHROMIUM_PATH"] = chromium

    cmd = build_pytest_cmd(workers)
    print(f"\n[智能体] 开始并发执行冒烟测试: {' '.join(cmd)} (base_url={base_url})")
    proc = subprocess.run(cmd, cwd=str(GENERATED_DIR), env=env,
                          capture_output=True, text=True, timeout=timeout)
    output = proc.stdout + "\n" + proc.stderr
    print(output)
    return proc.returncode, output
