"""站点扫描器: 从被测应用代码目录自动生成站点说明书 (SITE_SPEC)。

功能: 扫描 Python 路由 + HTML 模板控件, 结合用户提供的业务规则,
自动生成"站点说明书"提示词 (写入 agent/site_spec.py), 供 generate/chat 使用,
避免 LLM 因不知道控件的选择器而生成错误的测试用例。

用法:
    python agent/agent.py spec --code-dir webapp --rules "业务规则文本"
    python agent/agent.py spec --code-dir ./my_app --rules-file rules.txt
"""
import json
import re
from pathlib import Path

TEST_SCRIPT_REQUIREMENTS = """测试脚本要求:
1. 使用 Python + pytest + playwright.sync_api
2. 浏览器 fixture 已由 Script/conftest.py 统一提供, 每个测试函数直接声明 page 参数
   即可使用(conftest 已提供 browser / page / base_url 三个 fixture, 会话级只启动一次浏览器),
   **禁止在脚本里重复定义 browser 或 page fixture**
3. 基础地址使用环境变量 SMOKE_BASE_URL 或 base_url fixture
4. 每个用例为普通 def test_xxx, 允许定义辅助函数
5. 断言必须使用 playwright.sync_api.expect 的自动等待断言(如 expect(locator).to_be_visible(),
   to_have_text(), to_have_count() 等), 禁止用 is_visible()/inner_text() 直接断言,
   避免点击后立即断言导致的时序问题
6. 导航/交互后如需等待, 使用 page.wait_for_load_state("networkidle") 或 expect 自动等待
7. 每个用例函数名必须与 cases 中的 func 字段一一对应
"""

# 真实 LLM 模式: 让 LLM 基于代码摘要提炼更准确的业务规则
SPEC_LLM_PROMPT = """【任务】站点说明书-业务规则提炼
你是资深测试开发工程师。请基于被测应用的代码摘要与补充规则, 提炼出完整的业务规则清单,
供 AI 自动生成测试用例时参考(例如未登录访问保护页面会怎样、表单必填校验、错误提示、
条件渲染元素出现的时机、成功后的跳转等)。

【被测应用代码摘要】
{routes}
{controls}

【用户补充规则】
{user_rules}

请只输出一个 JSON 对象(不要输出 markdown 代码块标记), 格式:
{{
  "rules": ["1. 规则一", "2. 规则二", ...]
}}
每条规则要具体、可执行(包含具体选择器与预期行为)。"""


def scan_python_routes(code_dir: Path) -> list[dict]:
    """提取 Flask 路由 -> [{path, methods, view, template, file}]"""
    routes = []
    for py in sorted(code_dir.rglob("*.py")):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(
            r'@\w+\.route\(\s*[\'"]([^\'"]+)[\'"]\s*(?:,\s*methods=\s*\[([^\]]*)\])?\s*\)',
            text):
            path = m.group(1)
            methods = [x.strip().strip('"\'')
                       for x in (m.group(2) or "GET").split(",") if x.strip()]
            # 视图函数体: 从 def 起到下一个顶格 def/@路由/class/if __name__
            vm = re.search(r'\ndef\s+(\w+)\s*\(', text[m.end():])
            view = vm.group(1) if vm else ""
            body = ""
            if vm:
                body_start = m.end() + vm.end()
                body_end_m = re.search(
                    r'\n(?=def\s+|@\w+\.route|class\s+|if __name__)', text[body_start:])
                body = text[body_start:body_start + body_end_m.start()] if body_end_m else ""
            tm = re.search(r'render_template\(\s*[\'"]([^\'"]+)[\'"]', body)
            template = tm.group(1) if tm else ""
            routes.append({"path": path, "methods": methods, "view": view,
                           "template": template, "file": py.name})
    return routes


def _attrs(tag: str) -> dict:
    return {k: v for k, v in re.findall(r'([a-zA-Z_-]+)="([^"]*)"', tag)}


def _conditional_marked(text: str) -> set:
    """找出 {% if %}/{% for %} 块内出现的 id/class, 用于标记条件渲染元素。"""
    marked = set()
    depth = 0
    pattern = re.compile(
        r'\{%\s*(if|for|with)\b|\{%\s*(endif|endfor|endwith)\b'
        r'|<([a-z]+)\b[^>]*\s(id|class)="([^"]*)"')
    for m in pattern.finditer(text):
        if m.group(1):
            depth += 1
        elif m.group(2):
            depth = max(0, depth - 1)
        elif m.group(4) and depth > 0:
            if m.group(4) == "id":
                marked.add(f"#{m.group(5)}")
            else:
                for c in m.group(5).split():
                    if c and not c.startswith("{"):
                        marked.add(f".{c}")
    return marked


def scan_html_page(html_file: Path) -> dict:
    """提取单个 HTML 模板的页面标题、控件选择器、class 与条件渲染标记。"""
    text = html_file.read_text(encoding="utf-8", errors="ignore")
    cond = _conditional_marked(text)

    labels = {m.group(1): m.group(2).strip()
              for m in re.finditer(r'<label[^>]*for="([^"]+)"[^>]*>([^<]*)</label>', text)}

    controls = []
    # 表单控件 (input/textarea/select)
    for m in re.finditer(r'<(input|textarea|select)\b[^>]*>', text):
        a = _attrs(m.group(0))
        cid = a.get("id") or a.get("name")
        if not cid:
            continue
        sel = f"#{a.get('id') or cid}"
        desc = labels.get(a.get("id", ""), "") or labels.get(a.get("name", ""), "")
        kind = a.get("type", "") or m.group(1)
        controls.append({
            "sel": sel, "desc": desc, "kind": kind,
            "required": "required" in m.group(0),
            "placeholder": a.get("placeholder", ""),
            "cond": "条件渲染" if sel in cond else "",
        })
    # 按钮
    for m in re.finditer(r'<button\b[^>]*>([^<]*)</button>', text):
        a = _attrs(m.group(0))
        if a.get("id"):
            sel = f"#{a['id']}"
            controls.append({"sel": sel, "desc": _clean_text(m.group(1)), "kind": "button",
                             "required": "", "placeholder": "",
                             "cond": "条件渲染" if sel in cond else ""})
    # 链接 (带 id)
    for m in re.finditer(r'<a\b[^>]*>([^<]*)</a>', text):
        a = _attrs(m.group(0))
        if a.get("id"):
            sel = f"#{a['id']}"
            controls.append({"sel": sel, "desc": _clean_text(m.group(1)), "kind": "link",
                             "required": "", "placeholder": "",
                             "cond": "条件渲染" if sel in cond else ""})
    # 表单
    for m in re.finditer(r'<form\b[^>]*>', text):
        a = _attrs(m.group(0))
        if a.get("id"):
            controls.append({"sel": f"#{a['id']}", "desc": f"form(method={a.get('method', '')})",
                             "kind": "form", "required": "", "placeholder": "",
                             "cond": ""})
    # 带 id 的区域 (id 前必须是空白, 排除 data-product-id 等 data-* 属性)
    seen = {c["sel"] for c in controls}
    for m in re.finditer(r'<(div|span|main|section|p|strong|h\d)\b[^>]*\sid="([^"]+)"[^>]*>', text):
        sel = f"#{m.group(2)}"
        if sel in seen:
            continue
        controls.append({"sel": sel, "desc": f"{m.group(1)}区域", "kind": "area",
                         "required": "", "placeholder": "",
                         "cond": "条件渲染" if sel in cond else ""})
        seen.add(sel)
    # class 选择器 (静态值)
    classes = []
    for m in re.finditer(r'class="([^"]+)"', text):
        for c in m.group(1).split():
            if c.startswith("{"):
                continue
            sel = f".{c}"
            if sel not in classes and sel not in seen:
                classes.append(sel)
                seen.add(sel)

    # 页面标题: 取第一个 h1, 回退到模板文件名
    h1 = re.search(r'<h1[^>]*>([^<]+)</h1>', text)
    title = h1.group(1).strip() if h1 else html_file.stem
    return {"file": html_file.name, "title": title,
            "controls": controls, "classes": classes}


def extract_business_rules(code_dir: Path, user_rules: str) -> list[str]:
    """静态启发式提取业务规则 (账号/提示信息/未登录跳转/404/必填校验), 合并用户规则。"""
    rules = []
    texts = [f.read_text(encoding="utf-8", errors="ignore")
             for f in sorted(code_dir.rglob("*.py"))]
    joined = "\n".join(texts)
    # 演示账号
    m = re.search(r'(USERS|users|ACCOUNTS|accounts)\s*=\s*\{(.*?)\}', joined, re.S)
    if m:
        pairs = re.findall(r'[\'"]([^\'"]+)[\'"]\s*:\s*[\'"]([^\'"]+)[\'"]', m.group(2))
        if pairs:
            rules.append("演示账号: " + ", ".join(f"{u}/{p}" for u, p in pairs))
    # flash 提示信息
    for fm in re.findall(r'flash\(\s*[\'"]([^\'"]+)[\'"]', joined):
        rules.append(f"页面提示信息: {fm}")
    # 未登录跳转
    if re.search(r'if\s+["\']user["\']\s+not\s+in\s+session', joined):
        rules.append("未登录访问受保护页面会跳转到登录页")
    # 404
    for m in re.finditer(r'return\s+"([^"]+)",\s*404', joined):
        rules.append(f"访问不存在的资源返回 404: {m.group(1)}")
    # 必填校验
    if re.search(r'if\s+not\s+(\w+)\s+or\s+not\s+\w+', joined):
        rules.append("关键表单字段未填写时给出提示并停留在当前页")
    # 登录成功跳转
    if re.search(r'session\[["\']user["\']\]\s*=\s*\w+', joined):
        rules.append("登录成功后写入 session 并跳转首页")
    # 用户补充规则
    if user_rules.strip():
        rules.append(user_rules.strip())
    return rules


def _fmt_control(c: dict) -> str:
    parts = []
    if c.get("desc"):
        parts.append(c["desc"])
    parts.append(c["kind"])
    if c.get("required"):
        parts.append("必填")
    if c.get("placeholder"):
        parts.append(f"placeholder={c['placeholder']}")
    if c.get("cond"):
        parts.append(c["cond"])
    return f"{c['sel']}({', '.join(parts)})"


def _clean_text(raw: str) -> str:
    """去掉标签文本中的 Jinja 动态表达式, 保留静态文本。"""
    cleaned = re.sub(r"\{\{.*?\}\}", "", raw, flags=re.S)
    return re.sub(r"\s+", " ", cleaned).strip()


def build_site_spec_text(site_name: str, base_url: str,
                         routes: list[dict], pages: dict, rules: list[str],
                         layout: dict | None = None) -> str:
    """把扫描结果组装成站点说明书文本。

    layout: 公共布局模板(如 base.html)的扫描结果, 其控件作为"公共导航"列出。
    """
    lines = [f"被测系统: {site_name}",
             f"基础地址: {base_url} (由环境变量 SMOKE_BASE_URL 提供, 脚本中读取)"]
    if layout and layout.get("controls"):
        cdesc = "; ".join(_fmt_control(c) for c in layout["controls"][:15])
        lines.append(f"公共导航(所有页面继承): {cdesc}")
    lines += ["", "页面与路由:"]
    for r in routes:
        line = f"- {','.join(r['methods'])} {r['path']} ({r['file']})"
        if r["template"] and r["template"] in pages:
            pg = pages[r["template"]]
            parts = [pg["title"]]
            if pg["controls"]:
                parts.append("控件: " + "; ".join(
                    _fmt_control(c) for c in pg["controls"][:15]))
            if pg["classes"]:
                parts.append("可用class: " + ", ".join(pg["classes"][:10]))
            line += f": {'; '.join(parts)}"
        lines.append(line)

    lines += ["", "业务规则:"]
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. {rule}")
    lines += ["", TEST_SCRIPT_REQUIREMENTS]
    return "\n".join(lines)


def code_summary_for_llm(routes: list[dict], pages: dict) -> str:
    """组装给 LLM 的代码摘要 (路由 + 控件), 供真实模式提炼业务规则。"""
    route_lines = [f"- {','.join(r['methods'])} {r['path']} -> {r['view']} (render: {r['template']})"
                   for r in routes]
    control_lines = []
    for name, pg in pages.items():
        cdesc = "; ".join(_fmt_control(c) for c in pg["controls"][:15])
        control_lines.append(f"[{name}] 标题: {pg['title']}; {cdesc}")
    return "\n".join(route_lines) + "\n\n" + "\n".join(control_lines)


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


def write_site_spec(spec_text: str, site_spec_path: Path) -> None:
    """把生成的说明书写入 agent/site_spec.py (带安全转义)。"""
    header = ('"""站点说明书 (由 spec 命令自动生成, 可手工编辑)。"""\n\n'
              'SITE_SPEC = ')
    if '"""' in spec_text:
        body = repr(spec_text) + "\n"
    else:
        body = f'"""{spec_text}"""\n'
    site_spec_path.write_text(header + body, encoding="utf-8")
