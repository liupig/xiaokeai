@echo off
rem Companion Studio 一键启动：后端 8600 + 前端 5175
setlocal
cd /d %~dp0

if not exist backend\.venv (
  echo [1/3] 创建后端虚拟环境并安装依赖...
  python -m venv backend\.venv
  backend\.venv\Scripts\pip install -r backend\requirements.txt
)

if not exist frontend\node_modules (
  echo [2/3] 安装前端依赖...
  pushd frontend
  call npm install --legacy-peer-deps
  popd
)

echo [3/3] 启动服务...
start "companion-backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8600"
start "companion-frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 4 /nobreak >nul
start http://localhost:5175/
echo 已启动：前端 http://localhost:5175  后端 http://127.0.0.1:8600
endlocal
