"""AI 冒烟测试智能体 - 主入口。

子命令:
    spec "代码目录"            提交被测应用代码目录 + 业务规则, 自动生成站点说明书提示词
    generate "需求描述"        首次生成冒烟测试脚本, 生成后暂停供人工检查
    chat "继续补充/修改指令"    基于已有脚本连续对话, 完善用例
    run                       并发执行 Script 下全部脚本, 汇总结果并回填 Excel 台账

示例:
    python agent/agent.py spec --code-dir webapp --rules "下单前必须登录"
    python agent/agent.py generate "测试从登录到下单结算的完整冒烟流程"
    python agent/agent.py chat "把登录用例补充一条空密码被拦截的用例"
    python agent/agent.py chat "在结算用例里增加地址为空时给出错误提示的检查"
    python agent/agent.py run
    python agent/agent.py run --workers auto

环境变量:
    ARK_API_KEY  火山方舟 API Key (必填, 不填则进入 MOCK 演示模式)
    ARK_MODEL    模型名 (默认 doubao-seed-2-1-pro-260628)
"""
import argparse
import os
import sys

# 保证以 `python agent/agent.py` 方式运行时也能导入 agent 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.generator import SCRIPT_DIR, XLSX_FILE, apply_result
from agent.llm import LLMClient


def check_server(base_url: str) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(base_url, timeout=3)
        return True
    except Exception:
        return False


def cmd_spec(client: LLMClient, code_dir: str, rules: str, rules_file: str | None,
              base_url: str, site_name: str) -> int:
    """提交代码目录 + 业务规则 -> 自动生成站点说明书提示词 (agent/site_spec.py)。"""
    from pathlib import Path
    from agent import scanner

    code_path = Path(code_dir)
    if not code_path.is_dir():
        print(f"[错误] 代码目录不存在: {code_dir}")
        return 1

    user_rules = rules
    if rules_file:
        rf = Path(rules_file)
        if not rf.is_file():
            print(f"[错误] 业务规则文件不存在: {rules_file}")
            return 1
        user_rules = (user_rules + "\n" + rf.read_text(encoding="utf-8")).strip()

    print("=" * 60)
    print("步骤0: 自动生成站点说明书提示词 (供 generate/chat 使用)")
    print("=" * 60)
    print(f"[智能体] 正在扫描代码目录: {code_path}")

    routes = scanner.scan_python_routes(code_path)
    html_files = sorted(code_path.rglob("*.html"))
    pages = {f.name: scanner.scan_html_page(f) for f in html_files}
    # 公共布局模板(如 base.html)单独提取为"公共导航", 不当作独立页面
    layout = pages.pop("base.html", None)
    static_rules = scanner.extract_business_rules(code_path, user_rules)

    print(f"  - 路由: {len(routes)} 个")
    print(f"  - HTML模板: {len(pages)} 个" + (" (含公共布局 base.html)" if layout else ""))
    print(f"  - 规则: {len(static_rules)} 条")

    # 真实 LLM 模式: 基于代码摘要提炼更准确的业务规则
    if not client.mock:
        print("[智能体] 正在调用 LLM 提炼业务规则 ...")
        summary = scanner.code_summary_for_llm(routes, pages)
        messages = [
            {"role": "system",
             "content": "你是资深测试开发工程师, 负责根据被测应用代码生成业务规则清单。"},
            {"role": "user", "content": scanner.SPEC_LLM_PROMPT.format(
                routes=summary, controls="", user_rules=user_rules or "无")},
        ]
        try:
            content = client.chat(messages, temperature=0.1, max_tokens=3000)
            data = scanner.extract_json(content)
            if data.get("rules"):
                static_rules = data["rules"]
                print(f"  - LLM 提炼规则: {len(static_rules)} 条")
        except Exception as e:
            print(f"  - LLM 提炼失败(使用静态规则): {e}")

    spec_text = scanner.build_site_spec_text(
        site_name, base_url, routes, pages, static_rules, layout)

    site_spec_path = Path(__file__).resolve().parent / "site_spec.py"
    scanner.write_site_spec(spec_text, site_spec_path)

    print(f"\n[智能体] 站点说明书已生成并写入: {site_spec_path}")
    print(f"  - 站点: {site_name}")
    print(f"  - 基础地址: {base_url}")
    print(f"  - 控件选择器已从模板提取, 条件渲染元素已标注")
    print("\n下一步: 发送本次测试需求给智能体:")
    print('  python agent/agent.py generate "你的测试需求描述"')
    return 0


def cmd_generate(client: LLMClient, requirement: str) -> int:
    print("=" * 60)
    print("步骤1/2: 生成冒烟测试脚本 (生成后暂停, 请人工检查)")
    print("=" * 60)
    result = apply_result(client, requirement, first=True)
    print("\n[智能体] 生成完成:")
    print(f"  - 动作: {result['action']}")
    print(f"  - 脚本: {SCRIPT_DIR.name}/{result['script_name']}")
    print(f"  - 说明: {result['summary']}")
    print(f"  - 用例数: {len(result['cases'])}")
    print(f"\n请检查以下文件, 确认无误后执行下一步:")
    print(f"  1. 脚本: {SCRIPT_DIR}")
    print(f"  2. 台账: {XLSX_FILE}")
    print("\n下一步: python agent/agent.py run   # 执行全部用例并回填结果")
    print("或继续完善: python agent/agent.py chat \"补充...\"")
    return 0


def cmd_chat(client: LLMClient, instruction: str) -> int:
    print("=" * 60)
    print("步骤1/2: 连续对话, 完善冒烟测试脚本 (生成后暂停, 请人工检查)")
    print("=" * 60)
    if not SCRIPT_DIR.exists() or not any(SCRIPT_DIR.glob("test_smoke_*.py")):
        print("[错误] Script 目录为空, 请先运行: python agent/agent.py generate \"需求描述\"")
        return 1
    result = apply_result(client, instruction, first=False)
    print("\n[智能体] 更新完成:")
    print(f"  - 动作: {result['action']}")
    print(f"  - 脚本: {SCRIPT_DIR.name}/{result['script_name']}")
    print(f"  - 说明: {result['summary']}")
    print(f"  - 用例数: {len(result['cases'])}")
    print("\n下一步: python agent/agent.py run   # 执行全部用例并回填结果")
    return 0


def cmd_run(base_url: str, workers: str | None) -> int:
    print("=" * 60)
    print("步骤2/2: 并发执行 Script 目录下全部脚本 -> 汇总结果 -> 回填 Excel 台账")
    print("=" * 60)
    if not SCRIPT_DIR.exists() or not any(SCRIPT_DIR.glob("test_smoke_*.py")):
        print("[错误] Script 目录为空, 请先生成脚本: python agent/agent.py generate \"需求描述\"")
        return 1
    if not check_server(base_url):
        print(f"[错误] 被测站点 {base_url} 不可达, 请先启动电商网站: python webapp/app.py")
        return 1

    from agent.executor import run_all_tests
    from agent.reporter import build_result_map, parse_pytest_output
    from agent.sheet_writer import build_ledger

    # 1. 并发执行全部脚本
    exit_code, output = run_all_tests(base_url, workers)

    # 2. 解析结果
    parsed = parse_pytest_output(output)
    result_map = build_result_map(parsed)

    # 3. 回填 Excel 台账
    build_ledger(SCRIPT_DIR, XLSX_FILE, result_map)

    # 4. 汇总输出
    passed = sum(1 for v in result_map.values() if v[0] == "通过")
    failed = sum(1 for v in result_map.values() if v[0] == "失败")
    print("\n" + "=" * 60)
    print(f"【智能体最终输出】共 {passed + failed} 个用例: 通过 {passed} / 失败 {failed}")
    for func, (result, detail) in result_map.items():
        print(f"  - {func}: {result}" + (f" | {detail[:60]}" if detail else ""))
    print(f"台账已更新: {XLSX_FILE}")
    print("=" * 60)
    return 0 if exit_code == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 冒烟测试智能体")
    sub = parser.add_subparsers(dest="command", required=True)

    p_spec = sub.add_parser("spec", help="从代码目录自动生成站点说明书提示词")
    p_spec.add_argument("--code-dir", required=True, help="被测应用代码目录(含路由py与HTML模板)")
    p_spec.add_argument("--rules", default="", help="业务规则文本")
    p_spec.add_argument("--rules-file", default=None, help="业务规则文本文件路径")
    p_spec.add_argument("--base-url", default="http://127.0.0.1:5000", help="被测站点基础地址")
    p_spec.add_argument("--site-name", default="被测站点", help="站点名称")

    p_gen = sub.add_parser("generate", help="首次生成冒烟测试脚本")
    p_gen.add_argument("requirement", help="用自然语言描述要测试的需求/流程")

    p_chat = sub.add_parser("chat", help="连续对话完善用例")
    p_chat.add_argument("instruction", help="继续补充/修改用例的指令")

    p_run = sub.add_parser("run", help="并发执行全部脚本并回填 Excel 台账")
    p_run.add_argument("--base-url", default="http://127.0.0.1:5000", help="被测电商站点地址")
    p_run.add_argument("--workers", default="auto",
                       help="并发 worker 数: auto=按 CPU 核数, 或指定数字如 4")

    args = parser.parse_args()
    client = LLMClient()

    if args.command == "spec":
        return cmd_spec(client, args.code_dir, args.rules, args.rules_file,
                        args.base_url, args.site_name)
    if args.command == "generate":
        return cmd_generate(client, args.requirement)
    if args.command == "chat":
        return cmd_chat(client, args.instruction)
    if args.command == "run":
        return cmd_run(args.base_url, args.workers)
    return 1


if __name__ == "__main__":
    sys.exit(main())
