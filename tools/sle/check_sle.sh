#!/bin/bash

IPC_IP="${1}"
IPC_USER="root"
IPC_PASS="weidian_2025"
SLE_SCRIPT="/userdata/sle.sh"
DEBUG="${2:-0}"  # 第二个参数为1时开启调试

if [ -z "$IPC_IP" ]; then
    echo "用法: $0 <IPC_IP> [debug]"
    exit 1
fi

echo "=== 检查 IPC($IPC_IP) 星闪服务状态 ==="

# 使用 expect 通过 telnet 登录并检查进程
CHECK_RESULT=$(expect -c "
set timeout 10
log_user 0
spawn telnet $IPC_IP
expect \"login:\"
send \"$IPC_USER\r\"
expect \"Password:\"
send \"$IPC_PASS\r\"
expect \"#\"
send \"pgrep -x sparklinkd\r\"
expect \"#\"
set output \$expect_out(buffer)
send \"exit\r\"
expect eof

if {[regexp {[0-9]+} \$output]} {
    puts \"RUNNING\"
} else {
    puts \"NOT_RUNNING\"
}
" 2>&1)

if [ "$DEBUG" = "1" ]; then
    echo "[DEBUG] CHECK_RESULT: $CHECK_RESULT"
fi

# 检查返回状态
if echo "$CHECK_RESULT" | grep -q "^RUNNING$"; then
    echo ">> 星闪服务已运行"
    exit 0
else
    echo ">> 星闪服务未运行，正在启动..."
    
    # 启动星闪服务
    expect -c "
set timeout 30
log_user 0
spawn telnet $IPC_IP
expect \"login:\"
send \"$IPC_USER\r\"
expect \"Password:\"
send \"$IPC_PASS\r\"
expect \"#\"
send \"nohup sh $SLE_SCRIPT > /dev/null 2>&1 &\r\"
sleep 3
expect \"#\"
send \"exit\r\"
expect eof
" > /dev/null 2>&1
    
    echo ">> 星闪服务启动命令已发送"
    
    # 等待5秒后再次检查
    sleep 5
    CHECK_AGAIN=$(expect -c "
set timeout 10
log_user 0
spawn telnet $IPC_IP
expect \"login:\"
send \"$IPC_USER\r\"
expect \"Password:\"
send \"$IPC_PASS\r\"
expect \"#\"
send \"pgrep -x sparklinkd\r\"
expect \"#\"
set output \$expect_out(buffer)
send \"exit\r\"
expect eof

if {[regexp {[0-9]+} \$output]} {
    puts \"RUNNING\"
} else {
    puts \"NOT_RUNNING\"
}
" 2>&1)
    
    if [ "$DEBUG" = "1" ]; then
        echo "[DEBUG] CHECK_AGAIN: $CHECK_AGAIN"
    fi
    
    if echo "$CHECK_AGAIN" | grep -q "^RUNNING$"; then
        echo ">> 星闪服务启动成功"
    else
        echo ">> 警告：启动命令已执行，但未检测到进程，请手动检查"
    fi
fi
