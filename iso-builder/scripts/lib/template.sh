#!/bin/bash
# 模板渲染函数库

render_template() {
    local template="$1"
    local output="$2"
    shift 2

    cp "$template" "$output"

    for pair in "$@"; do
        local key="${pair%%=*}"
        local val="${pair#*=}"
        sed -i "s|\${${key}}|${val}|g" "$output"
    done
}

render_template_env() {
    local template="$1"
    local output="$2"
    shift 2

    if [ $# -gt 0 ]; then
        envsubst "$(printf '${%s} ' "$@")" < "$template" > "$output"
    else
        envsubst < "$template" > "$output"
    fi
}
