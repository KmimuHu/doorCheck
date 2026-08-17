#!/bin/sh

ADV_DURATION=${1:-0}  # 0 表示持续运行，其他值表示运行指定秒数
TOOL_CMD="sparklinkctrl"
DAEMON_CMD="sparklinkd"

# 信号处理函数 - 用于优雅退出
cleanup() {
    echo ""
    echo "=== 收到退出信号，正在停止星闪广播 ==="
    
    # 停止广播
    if [ -n "$TOOL_PID" ] && kill -0 "$TOOL_PID" 2>/dev/null; then
        # 发送停止命令到已有的 sparklinkctrl 进程
        kill "$TOOL_PID" 2>/dev/null
    fi
    
    # 启动新的 sparklinkctrl 来发送停止命令
    (
        echo "AT+SLESTOPADV=$ADV_HANDLE"
        sleep 1
        echo "AT+SLEDISABLE"
        sleep 1
        echo "quit"
    ) | $TOOL_CMD &
    sleep 2
    
    pkill -x "$TOOL_CMD" 2>/dev/null
    if [ -n "$DAEMON_PID" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        kill "$DAEMON_PID"
        wait "$DAEMON_PID" 2>/dev/null
    fi
    echo ">> 星闪服务已停止"
    exit 0
}

# 设置信号处理
trap cleanup INT TERM

echo "=== 检查并终止已存在的 $DAEMON_CMD 进程 ==="
if pgrep -x "$DAEMON_CMD" > /dev/null; then
    echo ">> 发现运行中的 $DAEMON_CMD，正在终止..."
    pkill -x "$DAEMON_CMD"
    sleep 1  # 等待进程退出
    # 强制 kill（如果未退出）
    if pgrep -x "$DAEMON_CMD" > /dev/null; then
        echo ">> 未正常退出，发送 SIGKILL..."
        pkill -9 -x "$DAEMON_CMD"
        sleep 1
    fi
    echo ">> 已清理旧进程。"
else
    echo ">> 未发现运行中的 $DAEMON_CMD。"
fi

# === 设备名称配置 ===
DEVICE_NAME="SLETEST"
NAME_LEN=${#DEVICE_NAME}  # 自动计算长度 → 7

# === 广播数据（可自定义，这里用简单标识）===
ANNOUNCE_DATA="aabbccddeeff11223344"      # 10 字节
ANNOUNCE_LEN=$((${#ANNOUNCE_DATA} / 2))

# === 扫描响应：留空，让系统自动使用设备名（或手动填入）===
# 方案 A：留空，依赖模块自动填充名称（如果支持）
SEEK_RSP_DATA="11224455"                  # 4 ......
SEEK_RSP_LEN=$((${#SEEK_RSP_DATA} / 2))   # ... 4

# 方案 B（更可靠）：手动构造包含名称的 Scan Response（TLV）
# SEEK_RSP_DATA="0809$(echo -n "$DEVICE_NAME" | xxd -p)"  # 08 09 + name hex
# SEEK_RSP_LEN=$((${#SEEK_RSP_DATA} / 2))

ADV_HANDLE=1

echo "=== 星闪广播启动（含设备名称）==="
echo "Device Name     : $DEVICE_NAME ($NAME_LEN 字节)"
echo "Adv Data        : $ANNOUNCE_DATA ($ANNOUNCE_LEN 字节)"
echo "Scan Rsp Data   : (自动或空)"
echo "运行模式        : $([ "$ADV_DURATION" -eq 0 ] && echo "持续运行" || echo "${ADV_DURATION}秒后停止")"

$DAEMON_CMD &
DAEMON_PID=$!
sleep 2

(
    echo "AT+SLEENABLE"
    sleep 2

    # 👇 关键：设置设备名称
    echo "AT+SLESETNAME=$NAME_LEN,$DEVICE_NAME"
    sleep 1

    # 设置广播参数
    echo "AT+SLESETADVPAR=1,3,200,200,0,000000000000,0,000000000000"
    sleep 1

    # 设置广播数据（Scan Response 留空，看模块是否自动填名称）
    echo "AT+SLESETADVDATA=$ADV_HANDLE,$ANNOUNCE_LEN,$SEEK_RSP_LEN,$ANNOUNCE_DATA,$SEEK_RSP_DATA"
    sleep 1

    echo "AT+SLESTARTADV=$ADV_HANDLE"
    
    if [ "$ADV_DURATION" -eq 0 ]; then
        echo ">> 广播已启动，持续运行模式（按 Ctrl+C 停止）..."
        # 持续运行模式 - 保持管道开启
        while true; do
            sleep 60
            echo ">> 星闪服务运行中... ($(date))"
            # 发送空命令保持连接
            echo ""
        done
    else
        echo ">> 广播已启动，持续 ${ADV_DURATION} 秒..."
        sleep $ADV_DURATION
        
        echo "AT+SLESTOPADV=$ADV_HANDLE"
        sleep 1
        echo "AT+SLEDISABLE" 
        sleep 1
        echo "quit"
        echo "exit"
    fi
) | $TOOL_CMD &
TOOL_PID=$!

# 清理 (仅在定时模式下执行)
if [ "$ADV_DURATION" -ne 0 ]; then
    wait $TOOL_PID
    pkill -x "$TOOL_CMD" 2>/dev/null
    if kill -0 $DAEMON_PID 2>/dev/null; then
        kill $DAEMON_PID
        wait $DAEMON_PID 2>/dev/null
    fi
    echo ">> 星闪广播已停止"
else
    # 持续运行模式下，等待信号处理或进程退出
    echo ">> 星闪服务持续运行中，按 Ctrl+C 停止"
    wait $TOOL_PID 2>/dev/null || wait $DAEMON_PID 2>/dev/null
fi