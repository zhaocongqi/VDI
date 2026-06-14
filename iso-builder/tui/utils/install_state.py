"""装机状态管理

install-state.json 是两阶段部署的核心纽带：
  Phase 1 (Live 环境): 收集配置 → 装机 → 写入 phase=os-installed → 重启
  Phase 2 (硬盘环境): 检测 phase=os-installed → 恢复配置 → 继续 VDI 部署 → phase=deployed
"""
import json
import os
import logging

logger = logging.getLogger("vdi-installer")

STATE_DIR = "/etc/vdi"
STATE_FILE = os.path.join(STATE_DIR, "install-state.json")


def load_state():
    """读取装机状态，无状态文件返回 None"""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取状态文件失败: {e}")
        return None


def save_state(phase, mode, config):
    """写入/更新装机状态

    Args:
        phase: "configuring" | "os-installing" | "os-installed" | "deploying" | "deployed"
        mode: 部署模式 (1=Master, 2=Worker)
        config: TUI 收集的配置字典
    """
    global STATE_DIR, STATE_FILE
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
    except PermissionError:
        STATE_DIR = os.path.expanduser("~/vdi-config")
        STATE_FILE = os.path.join(STATE_DIR, "install-state.json")
        os.makedirs(STATE_DIR, exist_ok=True)

    state = {
        "phase": phase,
        "mode": mode,
        "config": config,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info(f"装机状态已保存: phase={phase} mode={mode}")


def update_phase(phase):
    """仅更新 phase 字段（不覆盖 config）"""
    state = load_state()
    if state is None:
        logger.warning("无状态文件可更新")
        return
    state["phase"] = phase
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info(f"装机状态已更新: phase={phase}")


def is_resumable():
    """检测是否处于可续跑状态（os-installed，需要继续部署）"""
    state = load_state()
    if state is None:
        return False
    return state.get("phase") == "os-installed"


def clear_state():
    """部署完成后清除状态"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        logger.info("装机状态已清除")
