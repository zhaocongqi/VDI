#!/bin/bash -e

if [ -z "$TTY" ]; then
    export TTY=$(tty)
fi

export TERM=linux
export COLUMNS=${COLUMNS:-120}
export LINES=${LINES:-40}

# 设置终端尺寸（gocui 需要 >= 80x24）
if command -v stty &>/dev/null; then
    stty rows $LINES cols $COLUMNS 2>/dev/null || true
fi

vdi-installer
# Do not allow bash prompt if the installer doesn't exit with status 0

# We're not starting the shell using /bin/login, so we need to set $HOME manually
export HOME=/root
bash -l
