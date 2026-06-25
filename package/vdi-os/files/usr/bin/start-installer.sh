#!/bin/bash -e

if [ -z "$TTY" ]; then
    export TTY=$(tty)
fi

export TERM=linux

vdi-installer
# Do not allow bash prompt if the installer doesn't exit with status 0

# We're not starting /bin/login, so we need to set $HOME manually
export HOME=/root
bash -l
