@echo off
rem 启动本项目前端 nginx（8090 端口）
rem 依赖：前端已执行 npm run build（存在 frontend/dist/index.html）
set NGINX=C:\Users\35406\Desktop\redis_study\nginx-1.18.0\nginx.exe
set PREFIX=%~dp0.

if not exist "%PREFIX%\conf\mime.types" (
    echo [缺少 mime.types] 正在从 nginx 安装目录复制...
    copy "C:\Users\35406\Desktop\redis_study\nginx-1.18.0\conf\mime.types" "%PREFIX%\conf\mime.types"
)
if not exist "..\dist\index.html" (
    echo [缺少 dist] 请先到 frontend 目录执行: npm install ^&^& npm run build
    pause
    exit /b 1
)
"%NGINX%" -p "%PREFIX%"
echo 前端已启动: http://127.0.0.1:8090
pause