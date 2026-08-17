#!/bin/bash

# 星闪伴测脚本上传工具
# 用途：将 sle.sh 脚本上传到指定摄像头的 /userdata 目录并设置可执行权限

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查参数
if [ $# -lt 1 ]; then
    echo -e "${RED}错误: 缺少摄像头 IP 参数${NC}"
    echo "用法: $0 <摄像头IP> [debug]"
    echo "示例: $0 192.168.1.100"
    echo "      $0 192.168.1.100 1  # 开启调试模式"
    exit 1
fi

IPC_IP="$1"
IPC_USER="root"
IPC_PASS="weidian_2025"
DEBUG="${2:-0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_NAME="sle.sh"
SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_NAME"
TARGET_DIR="/userdata"
HTTP_PORT=8888
HTTP_SERVER_PID=""

# 清理函数
cleanup() {
    if [ -n "$HTTP_SERVER_PID" ] && kill -0 $HTTP_SERVER_PID 2>/dev/null; then
        echo -e "\n${YELLOW}>> 关闭 HTTP 服务...${NC}"
        kill $HTTP_SERVER_PID 2>/dev/null || true
        wait $HTTP_SERVER_PID 2>/dev/null || true
        echo -e "${GREEN}✓ HTTP 服务已关闭${NC}"
    fi
}

trap cleanup EXIT

# 检查必要工具
if ! command -v expect &> /dev/null; then
    echo -e "${RED}错误: 未找到 expect 命令${NC}"
    echo "请安装 expect: brew install expect (macOS) 或 apt-get install expect (Linux)"
    exit 1
fi

if ! command -v telnet &> /dev/null; then
    echo -e "${RED}错误: 未找到 telnet 命令${NC}"
    exit 1
fi

# 检查本地脚本是否存在
if [ ! -f "$SCRIPT_PATH" ]; then
    echo -e "${RED}错误: 找不到 $SCRIPT_NAME 文件${NC}"
    echo "请确保 $SCRIPT_NAME 与本脚本在同一目录下"
    exit 1
fi

echo -e "${GREEN}=== 星闪脚本上传工具 ===${NC}"
echo "目标摄像头: $IPC_IP"
echo "脚本路径: $SCRIPT_PATH"
echo "目标目录: $TARGET_DIR"

# 检查摄像头是否可达
echo -e "\n${YELLOW}>> 检查摄像头连接...${NC}"
if ! ping -c 1 -W 2 "$IPC_IP" &> /dev/null; then
    echo -e "${RED}警告: 无法 ping 通摄像头 $IPC_IP，继续尝试连接...${NC}"
fi

# 步骤1: 检查脚本是否已存在
echo -e "\n${YELLOW}>> 检查摄像头上是否已存在脚本...${NC}"
CHECK_RESULT=$(expect -c "
set timeout 10
log_user 0
spawn telnet $IPC_IP
expect \"login:\"
send \"$IPC_USER\r\"
expect \"Password:\"
send \"$IPC_PASS\r\"
expect \"#\"
send \"ls -l $TARGET_DIR/$SCRIPT_NAME\r\"
expect \"#\"
set output \$expect_out(buffer)
send \"exit\r\"
expect eof

if {[regexp {$SCRIPT_NAME} \$output]} {
    puts \"EXISTS\"
} else {
    puts \"NOT_EXISTS\"
}
" 2>&1)

if [ "$DEBUG" = "1" ]; then
    echo "[DEBUG] CHECK_RESULT: $CHECK_RESULT"
fi

if echo "$CHECK_RESULT" | grep -q "^EXISTS$"; then
    echo -e "${YELLOW}✓ 脚本已存在于摄像头 $TARGET_DIR 目录，跳过上传${NC}"
    exit 0
fi

# 步骤2: 启动本地 HTTP 服务器
echo -e "\n${YELLOW}>> 启动本地 HTTP 服务 (端口 $HTTP_PORT)...${NC}"
cd "$SCRIPT_DIR"
python3 -m http.server $HTTP_PORT &> /dev/null &
HTTP_SERVER_PID=$!
sleep 2

# 检查 HTTP 服务是否启动成功
if ! kill -0 $HTTP_SERVER_PID 2>/dev/null; then
    echo -e "${RED}错误: HTTP 服务启动失败，端口 $HTTP_PORT 可能被占用${NC}"
    exit 1
fi
echo -e "${GREEN}✓ HTTP 服务已启动 (PID: $HTTP_SERVER_PID)${NC}"

# 获取本机 IP（用于摄像头下载）
LOCAL_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n 1)
if [ -z "$LOCAL_IP" ]; then
    echo -e "${RED}错误: 无法获取本机 IP 地址${NC}"
    exit 1
fi
echo "本机 IP: $LOCAL_IP"

# 步骤3: 通过 telnet 下载脚本并设置权限
echo -e "\n${YELLOW}>> 通过 telnet 上传脚本到摄像头...${NC}"
UPLOAD_RESULT=$(expect -c "
set timeout 30
log_user $DEBUG
spawn telnet $IPC_IP
expect \"login:\"
send \"$IPC_USER\r\"
expect \"Password:\"
send \"$IPC_PASS\r\"
expect \"#\"

# 进入目标目录
send \"cd $TARGET_DIR\r\"
expect \"#\"

# 下载脚本
send \"wget http://$LOCAL_IP:$HTTP_PORT/$SCRIPT_NAME -O $SCRIPT_NAME\r\"
expect {
    \"saved\" {
        # wget 成功
    }
    \"100%\" {
        # wget 成功
    }
    timeout {
        puts \"DOWNLOAD_TIMEOUT\"
        send \"exit\r\"
        expect eof
        exit 1
    }
}
expect \"#\"

# 设置可执行权限
send \"chmod +x $SCRIPT_NAME\r\"
expect \"#\"

# 验证文件
send \"ls -l $SCRIPT_NAME\r\"
expect \"#\"
set output \$expect_out(buffer)

send \"exit\r\"
expect eof

if {[regexp {rwxr} \$output]} {
    puts \"UPLOAD_SUCCESS\"
} else {
    puts \"UPLOAD_FAILED\"
}
" 2>&1)

if [ "$DEBUG" = "1" ]; then
    echo "[DEBUG] UPLOAD_RESULT: $UPLOAD_RESULT"
fi

# 检查结果
if echo "$UPLOAD_RESULT" | grep -q "DOWNLOAD_TIMEOUT"; then
    echo -e "\n${RED}✗ 下载超时，请检查网络连接${NC}"
    exit 1
elif echo "$UPLOAD_RESULT" | grep -q "UPLOAD_SUCCESS"; then
    echo -e "\n${GREEN}✓ 脚本上传成功！${NC}"
    echo -e "${GREEN}✓ 已设置可执行权限${NC}"
    echo -e "\n可以通过以下命令在摄像头上运行："
    echo -e "  ${YELLOW}$SCRIPT_DIR/check_sle.sh $IPC_IP${NC}"
    exit 0
elif echo "$UPLOAD_RESULT" | grep -q "UPLOAD_FAILED"; then
    echo -e "\n${RED}✗ 脚本上传失败或权限设置失败${NC}"
    exit 1
else
    echo -e "\n${YELLOW}警告: 无法确认上传状态${NC}"
    echo "输出信息:"
    echo "$UPLOAD_RESULT"
    exit 1
fi
