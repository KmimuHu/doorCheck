@echo off
echo ====================================
echo 门锁产测工具打包脚本
echo ====================================
echo.

echo [1/3] 检查依赖...
python -c "import PyQt5; import paho.mqtt.client; import zeroconf; import requests; import yaml; from Cryptodome.Cipher import AES" 2>nul
if errorlevel 1 (
    echo 错误: 缺少必要的Python依赖包
    echo 请运行: pip install -r requirements.txt
    pause
    exit /b 1
)
echo 依赖检查完成 √
echo.

echo [2/3] 开始打包...
pyinstaller --onefile ^
    --windowed ^
    --name "门锁产测工具" ^
    --add-data "config;config" ^
    --add-data "certs;certs" ^
    --hidden-import=zeroconf ^
    --hidden-import=paho.mqtt.client ^
    --hidden-import=PyQt5 ^
    --hidden-import=PyQt5.QtCore ^
    --hidden-import=PyQt5.QtGui ^
    --hidden-import=PyQt5.QtWidgets ^
    --hidden-import=requests ^
    --hidden-import=yaml ^
    --hidden-import=Cryptodome ^
    --hidden-import=Cryptodome.Cipher ^
    --hidden-import=Cryptodome.Cipher.AES ^
    --hidden-import=Cryptodome.Hash ^
    --hidden-import=Cryptodome.Hash.HMAC ^
    --hidden-import=Cryptodome.Hash.SHA256 ^
    --collect-all zeroconf ^
    --collect-all paho.mqtt ^
    main.py

if errorlevel 1 (
    echo.
    echo 错误: 打包失败！
    pause
    exit /b 1
)

echo.
echo [3/3] 打包完成 √
echo.
echo ====================================
echo 可执行文件位于: dist\门锁产测工具.exe
echo ====================================
echo.
echo 打包内容:
echo   - 配置文件: config\config.yaml
echo   - SSL证书: certs\*.crt, certs\*.key
echo   - Python依赖: 已内置所有依赖库
echo.
pause
