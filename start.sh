#!/bin/bash
# 招聘自动化系统启动脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=============================="
echo "  招聘自动化系统 启动中..."
echo "=============================="

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi

# 检查 Node
if ! command -v node &> /dev/null; then
    echo "错误: 未找到 node，请先安装 Node.js 18+"
    exit 1
fi

# 安装后端依赖
echo ""
echo ">> 安装后端依赖..."
cd "$SCRIPT_DIR/backend"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt -q

# 安装前端依赖
echo ""
echo ">> 安装前端依赖..."
cd "$SCRIPT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    npm install
fi

# 启动后端
echo ""
echo ">> 启动后端服务 (端口 8000)..."
cd "$SCRIPT_DIR/backend"
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# 等后端启动
sleep 2

# 启动前端
echo ">> 启动前端开发服务器 (端口 3000)..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=============================="
echo "  系统已启动！"
echo "  前端: http://localhost:3000"
echo "  后端: http://localhost:8000"
echo "  API文档: http://localhost:8000/docs"
echo "=============================="
echo ""
echo "按 Ctrl+C 停止所有服务"

cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

wait
