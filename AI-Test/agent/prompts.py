"""Prompt 模板: 智能体角色定义、站点说明书、任务 Prompt。

站点说明书 SITE_SPEC 由 agent/site_spec.py 提供:
- 默认内置"拾光小店"版本
- 运行 `python agent/agent.py spec --code-dir <应用目录>` 可基于被测应用代码自动生成
"""

from agent.site_spec import SITE_SPEC

JSON_PROTOCOL = """输出协议(重要): 你必须只输出一个 JSON 对象, 不要输出 markdown 代码块标记和任何其他文字, 格式如下:
{
  "action": "create 或 update",
  "script_name": "test_smoke_XXX_描述.py",
  "summary": "一句话说明本次生成/修改了什么",
  "script": "完整可运行的python测试脚本代码(字符串)",
  "cases": [
    {
      "func": "test_xxx",
      "title": "用例标题",
      "precondition": "前置条件",
      "steps": "测试步骤",
      "expected": "预期结果"
    }
  ]
}
说明: create 时 script_name 只写文件名(序号部分可写XXX占位, 系统自动分配);
update 时必须填写要修改的已存在脚本的完整文件名。"""

SYSTEM_PROMPT_AGENT = (
    "你是一名资深测试开发工程师, 负责为电商网站编写 Playwright 冒烟测试脚本, "
    "并支持通过连续对话与用户反复沟通、不断完善用例。\n\n"
    + SITE_SPEC + "\n" + JSON_PROTOCOL
)

USER_PROMPT_GENERATE = """【任务】生成冒烟测试脚本
【需求】{requirement}
【已有脚本】
{existing}
请根据需求生成或修改脚本。action 选择规则:
- 需求是新增的测试点/全新功能 -> action=create (script_name 用 XXX 占位, 系统自动分配序号)
- 需求涉及修改/修复**已有**脚本(需求中提到了已有脚本的文件名或用例标题、或说明某用例报错/失败/执行有问题) -> action=update 该脚本,
  script_name 必须填写已存在的完整文件名, 在该脚本基础上修改(只改动受影响的用例, 其余用例保持不变)
修复失败用例时, 结合需求中描述的失败现象判断根因, 常见根因与正确修法:
1) 表单控件带 HTML required 属性时, 留空/缺项提交会被浏览器原生校验拦截, 请求根本不会发出,
   服务端渲染的错误提示(如 #login-error)不会出现 —— 应改为断言输入框处于 :invalid 状态且页面未跳转
   (如 expect(page.locator("#password:invalid")).to_be_visible() 加 expect(page).to_have_url(登录页))
2) 断言了条件渲染元素(仅在特定条件出现, 如登录失败后才渲染 #login-error): 先构造满足条件的操作再断言,
   或按站点说明书标注的"条件渲染"调整断言时机
3) 选择器与页面实际不符: 改用站点说明书 SITE_SPEC 中给出的选择器
4) 时序问题(点击后立即断言): 使用 expect 自动等待或 page.wait_for_load_state("networkidle")"""
