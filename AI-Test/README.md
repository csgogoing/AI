# AI 冒烟测试智能体（拾光小店电商站 + LLM 智能体）

一个端到端可运行的演示项目：**对智能体用自然语言描述需求 → 智能体自动生成可执行的
pytest+Playwright 冒烟脚本 → 人工检查确认 → 一键并发执行 → 汇总结果并自动回填 Excel 用例台账**。
支持与智能体**连续对话**，检查用例后可继续对话补充、修正用例。

LLM 使用火山引擎方舟（Volcengine Ark）Chat Completions API。

## 项目结构

```
smoke-test-ai-agent/
├── webapp/                 # 拾光小店：一个简单的 Flask 电商网站（内存态数据）
│   ├── app.py              # 网站入口: python webapp/app.py  -> http://127.0.0.1:5000
│   ├── templates/          # 首页/登录/购物车/结算/订单页
│   └── static/style.css
├── agent/                  # AI 冒烟测试智能体
│   ├── agent.py            # 主入口 CLI: spec / generate / chat / run
│   ├── scanner.py          # spec：扫描代码目录自动生成站点说明书（路由+控件选择器）
│   ├── site_spec.py        # 站点说明书 SITE_SPEC（spec 生成，可手工编辑）
│   ├── llm.py              # 火山方舟 Ark API 封装（无 Key 时自动进入 MOCK 模式）
│   ├── prompts.py          # Prompt 模板：从 site_spec 读取 SITE_SPEC + 生成提示词
│   ├── generator.py        # generate/chat：LLM 生成或修改脚本，落盘 Script + meta + 会话
│   ├── executor.py         # run：并发执行 Script 目录下全部脚本（pytest-xdist）
│   ├── reporter.py         # run：解析 pytest 结果并汇总（通过/失败 + 失败摘要）
│   └── sheet_writer.py     # 生成/更新 Excel 用例台账（openpyxl）
├── tests/generated/        # 智能体工作目录
│   ├── Script/             # 全部用例脚本 + 同名 .meta.json + conftest.py（共享浏览器fixture）
│   ├── conversation.json   # 连续对话历史
│   └── test_cases.xlsx     # 用例台账（8列：序号/脚本/标题/前置/步骤/预期/结果/失败详情）
├── run_demo.sh             # 一键脚本（自动启停网站，透传子命令）
└── requirements.txt        # 依赖（flask / playwright / pytest / pytest-xdist / openpyxl）
```

## 工作流程（自动生成说明书 + 生成执行分离 + 连续对话）

```
⓪ spec --code-dir <应用代码目录>  --▶  扫描路由+HTML模板控件, 合并你提供的业务规则,
                                       自动生成"站点说明书"提示词(写入 agent/site_spec.py)
                                       关键控件选择器(id/class)与条件渲染元素自动标注
                                       有 API Key 时 LLM 会进一步提炼业务规则
① generate "需求描述"   ──▶  LLM 基于站点说明书生成 pytest+Playwright 冒烟脚本到 Script/
                             同时生成 test_cases.xlsx 台账（结果列=未执行）
                             生成后【暂停】，由你人工检查脚本和用例
② chat "补充/修正..."    ──▶  基于已有会话连续对话：新增用例 / 修正失败用例（update）
③ run                    ──▶  并发执行 Script 目录下所有 .py 脚本（含手动添加的）
                             执行 → 解析结果 → 汇总"通过/失败 + 失败摘要"
                             → 回填 Excel 台账的"测试结果/失败详情"两列
                             → 智能体输出汇总：通过数/失败数 + 每个用例结果
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置火山方舟 API Key（获取: https://console.volcengine.com/ark/region:cn-beijing/apiKey）
export ARK_API_KEY="你的key"
# 可选: export ARK_MODEL="doubao-seed-2-1-pro-260628"

# 3. 一键演示（自动启动网站 → 透传子命令 → 关闭网站）
./run_demo.sh spec --code-dir webapp --site-name "拾光小店" --rules "只有登录后才能下单结算"
./run_demo.sh generate "测试从登录到下单结算的完整冒烟流程"
./run_demo.sh chat "补充一个空密码登录被拦截的用例"
./run_demo.sh run

# 或者手动分步:
python webapp/app.py &                        # 终端1: 启动电商网站
python agent/agent.py spec --code-dir webapp --rules "业务规则"  # 终端2: 生成站点说明书
python agent/agent.py generate "只测试登录功能"   # 终端2: 生成用例（可反复 chat 完善）
python agent/agent.py run                      # 终端2: 执行全部用例并回填台账
```

> **没有 API Key 也能跑**：未设置 `ARK_API_KEY` 时，智能体自动进入 **MOCK 模式**，
> 用本地预置内容走完"生成→人工检查→执行→汇总→台账回填"全流程，且预置用例可真实执行；
> 设置 Key 后自动切换真实 LLM 调用。

## 自动生成站点说明书（spec）

LLM 生成用例报错最常见的原因是提示词里没有被测页面的控件选择器。`spec` 命令解决这个问题：
你提交**被测应用的代码目录**和**业务规则**，它会自动扫描出全部路由与控件选择器，生成站点说明书提示词。

```bash
# 代码目录 + 业务规则文本
python agent/agent.py spec --code-dir webapp --rules "只有登录后才能下单结算"

# 代码目录 + 业务规则文件（多条规则可写文件）
python agent/agent.py spec --code-dir ./my_app --rules-file rules.txt \
    --base-url http://127.0.0.1:8080 --site-name "我的应用"
```

扫描内容：
- **路由**：从 Python 源码提取 `@app.route(...)`，并定位其渲染的模板
- **控件选择器**：从 HTML 模板提取 `input/button/a/form/区域` 的 id、class、label、必填、placeholder；
  自动识别并标注**条件渲染**元素（如 `{% if %}` 块内的登录错误提示）
- **公共导航**：base 布局模板的导航控件（如 `#nav-user`）单独列出
- **业务规则**：静态提取演示账号、flash 提示、未登录跳转、404 等；有 API Key 时由 LLM 基于
  代码摘要进一步提炼更完整的规则；你的 `--rules` 始终并入

生成结果写入 `agent/site_spec.py`（可手工编辑），随后 `generate`/`chat` 会自动使用。

## 并发执行

`run` 默认并发执行（需要 `pytest-xdist`，已在 requirements 中）：

```bash
python agent/agent.py run                 # 默认 --workers auto（按 CPU 核数）
python agent/agent.py run --workers 4     # 指定 4 个并发 worker
python agent/agent.py run --workers 1     # 单进程串行
```

并发模式下每个 worker 独立进程启动自己的浏览器实例，脚本无需任何改动。

## 手动添加用例

`run` 会**自动遍历 Script 目录下所有 `test_smoke_*.py`**，因此你可以：

1. 直接把 `test_smoke_003_xxx.py` 放进 `tests/generated/Script/`（仿照已有脚本，
   用 `page` 参数，不重复定义 fixture）；
2. 同目录放一个同名 `.meta.json` 记录用例元数据（标题/前置/步骤/预期）；
3. 执行 `run` 时该用例会被自动收集执行，并回填进 Excel 台账。

```json
// test_smoke_003_xxx.meta.json 格式
{ "script_name": "test_smoke_003_xxx.py",
  "cases": [
    { "func": "test_smoke_xxx", "title": "用例标题", "precondition": "前置条件",
      "steps": "测试步骤", "expected": "预期结果" }
  ] }
```
## 单用例调试
PWDEBUG=1 python -m pytest tests/generated/Script/test_smoke_003_manual_product.py -v

## 设计要点

- **为什么用 Playwright**：与业界主流 AI 测试平台同栈（自然语言→用例→执行→结果分析）。
- **自动生成站点说明书（spec）**：把被测应用的代码目录 + 业务规则一键转成提示词，
  控件选择器、条件渲染、公共导航自动标注——从源头减少"提示词缺选择器导致用例报错"。
- **Prompt 内置"站点说明书"（SITE_SPEC）**：把所有页面路由、关键选择器、业务规则喂给
  LLM，让生成的脚本可执行率高——这是"AI 生成用例"落地的关键工程技巧。
- **共享浏览器 fixture（conftest.py）**：整个 pytest 会话只启动一次 Playwright，
  避免多模块重复创建导致 Sync API 与 asyncio 冲突。
- **生成与执行分离**：`generate`/`chat` 只生成脚本并暂停，由人工检查后 `run` 再执行，
  保证用例可审、可追溯。
- **Excel 台账**：脚本/用例/执行结果/失败详情一一对应，失败详情直接取自 pytest 报错摘要。
- **MOCK 模式**：无 Key 时用内置脚本演示全流程，Key 就绪后零改动切换真实模型。

## 参考

- Ark Chat API 文档: https://console.volcengine.com/ark/region:cn-beijing/docs/ark/chat-api?lang=zh
- Ark API Key: https://console.volcengine.com/ark/region:cn-beijing/apiKey
