"""智能体第一步: 根据需求生成/完善冒烟测试脚本 (生成后暂停, 供人工检查)。

目录结构 (tests/generated/):
    Script/            # 所有用例 py 脚本 + 同名 .meta.json
    conversation.json  # 连续对话历史
    test_cases.xlsx    # 用例台账 (由 sheet_writer 维护)
"""
import json
import re
from pathlib import Path

from agent.llm import LLMClient
from agent.prompts import SYSTEM_PROMPT_AGENT, USER_PROMPT_GENERATE

GENERATED_DIR = Path(__file__).resolve().parent.parent / "tests" / "generated"
SCRIPT_DIR = GENERATED_DIR / "Script"
CONVERSATION_FILE = GENERATED_DIR / "conversation.json"
XLSX_FILE = GENERATED_DIR / "test_cases.xlsx"


def next_script_number() -> int:
    """扫描 Script 目录已有 test_smoke_XXX_*.py, 返回下一个序号。"""
    max_n = 0
    if SCRIPT_DIR.exists():
        for f in SCRIPT_DIR.glob("test_smoke_*.py"):
            m = re.match(r"test_smoke_(\d+)", f.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def meta_path(script_name: str) -> Path:
    return SCRIPT_DIR / (Path(script_name).stem + ".meta.json")


def read_conversation() -> list[dict]:
    if CONVERSATION_FILE.exists():
        return json.loads(CONVERSATION_FILE.read_text(encoding="utf-8"))
    return []


def write_conversation(messages: list[dict]) -> None:
    CONVERSATION_FILE.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")


def list_scripts() -> str:
    """已有脚本清单文本, 作为连续对话时给 LLM 的上下文。"""
    if not SCRIPT_DIR.exists():
        return "无"
    lines = []
    for f in sorted(SCRIPT_DIR.glob("test_smoke_*.py")):
        mp = meta_path(f.name)
        if mp.exists():
            cases = json.loads(mp.read_text(encoding="utf-8")).get("cases", [])
            titles = "、".join(c.get("title", "") for c in cases)
            lines.append(f"- {f.name}: {titles}")
        else:
            lines.append(f"- {f.name}: (无元数据)")
    return "\n".join(lines) if lines else "无"


def extract_json(content: str) -> dict:
    """从 LLM 输出中提取 JSON 对象 (兼容 markdown 代码块围栏)。"""
    content = content.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
    if m:
        content = m.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM 输出中未找到 JSON 对象")
    return json.loads(content[start:end + 1])


def apply_result(client: LLMClient, requirement: str, first: bool) -> dict:
    """调用 LLM 生成/修改脚本并落盘, 返回摘要。

    first=True  首次生成(重置会话); first=False 连续对话(读取已有会话历史)。
    """
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    if first:
        messages = [{"role": "system", "content": SYSTEM_PROMPT_AGENT}]
    else:
        messages = read_conversation()
        if not messages:
            messages = [{"role": "system", "content": SYSTEM_PROMPT_AGENT}]

    existing = "" if first else list_scripts()
    messages.append({"role": "user", "content": USER_PROMPT_GENERATE.format(
        requirement=requirement, existing=existing)})

    print("\n[智能体] 正在调用 LLM 生成/完善冒烟测试脚本 ...")
    content = client.chat(messages, temperature=0.2, max_tokens=8000)
    result = extract_json(content)

    action = result.get("action", "create")
    cases = result.get("cases", [])
    script_code = result.get("script", "")
    script_name = result.get("script_name", "").strip()
    if not script_code:
        raise ValueError("LLM 未返回脚本代码")

    # 确定性兜底: chat 指令中明确提到已有脚本文件名时, 强制 update 到该脚本,
    # 避免 LLM 误判为新增用例 (即使 LLM 返回 create 也纠正为 update)
    if not first:
        named = re.search(r"(test_smoke_\d+_[a-zA-Z0-9_]+\.py)", requirement)
        if named and (SCRIPT_DIR / named.group(1)).exists():
            action = "update"
            script_name = named.group(1)

    if action == "update":
        target = SCRIPT_DIR / script_name
        if not target.exists():
            raise ValueError(f"update 目标脚本不存在: {script_name}")
    else:
        num = next_script_number()
        if "XXX" in script_name:
            script_name = script_name.replace("XXX", f"{num:03d}")
        else:
            script_name = f"test_smoke_{num:03d}_{script_name}"
        target = SCRIPT_DIR / script_name

    target.write_text(script_code, encoding="utf-8")
    meta_path(target.name).write_text(
        json.dumps({"script_name": target.name, "cases": cases}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # 记录本轮对话, 支持连续对话
    messages.append({"role": "assistant", "content": content})
    write_conversation(messages)

    # 更新 Excel 台账 (本轮结果列暂记为"未执行")
    from agent.sheet_writer import build_ledger
    build_ledger(SCRIPT_DIR, XLSX_FILE)

    return {
        "action": action,
        "script_name": target.name,
        "summary": result.get("summary", ""),
        "cases": cases,
    }
