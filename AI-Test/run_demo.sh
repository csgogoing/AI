#!/usr/bin/env bash
# 一键演示: 启动电商网站 -> 透传子命令给智能体 -> 关闭网站
# 用法:
#   ./run_demo.sh generate "测试从登录到下单结算的完整冒烟流程"
#   ./run_demo.sh chat "补充一个空密码登录被拦截的用例"
#   ./run_demo.sh run
set -e
cd "$(dirname "$0")"

echo ">>> 启动电商网站 (拾光小店) http://127.0.0.1:5000"
python webapp/app.py &
WEB_PID=$!
sleep 2
trap 'kill $WEB_PID 2>/dev/null || true' EXIT

echo ">>> 运行 AI 冒烟测试智能体: $*"
python agent/agent.py "$@"
