#!/bin/bash

# 生成CA根证书
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt \
  -subj "/C=CN/ST=Beijing/L=Beijing/O=Weidian/OU=IoT/CN=Weidian Root CA"

# 生成服务器私钥
openssl genrsa -out mqtt_server.key 2048

# 创建服务器证书签名请求配置
cat > server.cnf << 'CONF'
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = CN
ST = Beijing
L = Beijing
O = Weidian
OU = IoT
CN = mqtt.weidian.local

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = mqtt.weidian.local
DNS.2 = *.weidian.local
DNS.3 = localhost
DNS.4 = *.local
IP.1 = 127.0.0.1
CONF

# 生成服务器证书签名请求
openssl req -new -key mqtt_server.key -out mqtt_server.csr -config server.cnf

# 使用CA签发服务器证书
openssl x509 -req -in mqtt_server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out mqtt_server.crt -days 3650 -sha256 -extensions v3_req -extfile server.cnf

# 清理临时文件
rm -f mqtt_server.csr server.cnf

echo "证书生成完成:"
echo "  CA证书: ca.crt (需要安装到设备端)"
echo "  服务器证书: mqtt_server.crt"
echo "  服务器私钥: mqtt_server.key"
