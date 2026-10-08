"""智能体第三步: 解析 pytest 结果并汇总 (通过/失败 + 失败摘要)。"""
import re


def parse_pytest_output(output: str) -> dict:
    """解析 pytest 输出 -> {func: {"node": nodeid, "status": ..., "trace": "..."}}

    兼容两种输出格式:
    - 单进程:   Script/xxx.py::test_xxx PASSED
    - xdist并发: [gw2] [ 20%] PASSED Script/xxx.py::test_xxx  或 summary 行 FAILED Script/xxx.py::test_xxx
    """
    results: dict = {}
    # 格式1: nodeid 在前, 状态词在后 (单进程)
    for m in re.finditer(r"(Script/[^\s]+\.py::(test_\w+))\s+(PASSED|FAILED|ERROR)",
                         output):
        nodeid, func, status = m.group(1), m.group(2), m.group(3)
        results[func] = {"node": nodeid, "status": status, "trace": ""}
    # 格式2: 状态词在前, nodeid 在后 (pytest-xdist 进度行 / short summary 行)
    for m in re.finditer(r"(PASSED|FAILED|ERROR)\s+(Script/[^\s]+\.py::(test_\w+))",
                         output):
        status, nodeid, func = m.group(1), m.group(2), m.group(3)
        results.setdefault(func, {"node": nodeid, "status": status, "trace": ""})

    # 提取失败段 traceback (pytest --tb=short 的 "______ test_xxx ______" 段)
    for fm in re.finditer(r"_{15,}\s*(test_\w+)\s*_{15,}", output):
        func = fm.group(1)
        if func not in results:
            continue
        seg = output[fm.end():]
        end_m = re.search(r"_{15,}\s*test_\w+\s*_{15,}|={15,}|short test summary", seg)
        block = seg[:end_m.start()] if end_m else seg[:600]
        results[func]["trace"] = block.strip()[:800]
    return results


def _extract_failure_summary(trace: str) -> str:
    """从 pytest 失败段提取简洁摘要: 文件定位行 + E 开头错误行, 过滤 xdist 头部与页面快照噪声。"""
    lines = [l.strip() for l in trace.splitlines() if l.strip()]
    loc = next((l for l in lines if re.match(r"Script/[^\s]+\.py:\d+", l)), "")
    e_lines = [l[2:].strip() for l in lines if l.startswith("E   ")]
    if e_lines:
        parts = ([loc] if loc else []) + e_lines[:8]
        return "\n".join(parts)
    return (loc + "\n" + trace[:300]).strip()


def build_result_map(parsed: dict) -> dict:
    """合并执行结果 -> {func: (测试结果, 失败详情)}

    失败详情取 pytest 报错摘要 (不经过 LLM), 便于直接在 Excel 台账中定位失败原因。
    """
    rmap: dict = {}
    for func, info in parsed.items():
        if info["status"] == "PASSED":
            rmap[func] = ("通过", "")
        else:
            detail = _extract_failure_summary(info["trace"]) or "执行失败, 未获取到失败详情"
            rmap[func] = ("失败", detail)
    return rmap
