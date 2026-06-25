#!/bin/bash
# 参考 Harvester 的 setup-installer.sh
# 创建 systemd drop-in unit，在第一个控制台 TTY 上运行安装器
# 替代默认的 login 提示

create_drop_in()
{
  DROP_IN_DIRECTORY=$1

  echo "Create installer drop-in in ${DROP_IN_DIRECTORY}..."
  mkdir -p ${DROP_IN_DIRECTORY}
  cat > "${DROP_IN_DIRECTORY}/override.conf" <<"EOF"
[Service]
# 不在该 TTY 上显示内核消息
ExecStartPre=/usr/bin/setterm --msg off

# 启动安装器前禁用 systemd 消息
ExecStartPre=/usr/bin/kill -s 55 1

# 安装器退出后恢复 systemd 消息
ExecStopPost=/usr/bin/kill -s 54 1

# 清除原始 getty 命令
ExecStart=

# 用 agetty 启动安装器
ExecStart=-/sbin/agetty -n -l /usr/bin/start-installer.sh %I $TERM
EOF
}

echo "Remove the getty service..."
rm -rf /etc/systemd/system/getty*

echo "Remove the serial-getty service..."
rm -rf /etc/systemd/system/serial-getty*

# 获取活跃的 TTY 列表
read -r -a tty_list < /sys/class/tty/console/active

for TTY in "${tty_list[@]}"; do
  tty_num=${TTY#tty}

  # 跳过非数字 TTY
  if [[ ! $tty_num =~ ^[0-9]+$ ]]; then
    continue
  fi

  # 检查是否是串口控制台
  tty_type=$(cat "/sys/class/tty/${TTY}/type")
  if [ "x${tty_type}" = "x0" ]; then
    # 串口控制台
    create_drop_in "/etc/systemd/system/serial-getty@${TTY}.service.d"
  else
    # VGA 控制台
    create_drop_in "/etc/systemd/system/getty@${TTY}.service.d"
  fi
  break
done

# 重新加载 systemd 并重启 getty 以应用 override
echo "Reload systemd and restart getty..."
systemctl daemon-reload

for TTY in "${tty_list[@]}"; do
  tty_num=${TTY#tty}
  if [[ ! $tty_num =~ ^[0-9]+$ ]]; then
    continue
  fi
  tty_type=$(cat "/sys/class/tty/${TTY}/type")
  if [ "x${tty_type}" = "x0" ]; then
    systemctl restart "serial-getty@${TTY}.service" 2>/dev/null || true
  else
    systemctl restart "getty@${TTY}.service" 2>/dev/null || true
  fi
  break
done
