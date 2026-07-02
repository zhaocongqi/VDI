# VDI 原生 Anaconda GUI Addon 架构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 VDI 安装器的配置收集模块迁移至官方原生 Anaconda GUI Addon，实现基于 GTK3/D-Bus 的网络配置，并彻底清理旧方案的交互残留配置。

**Architecture:** 
1. 用 Python 编写 `VdiAddon` 及 `VdiNetworkSpoke`；
2. 构建期解压 `images/install.img` 并重构 SquashFS 注入插件；
3. 清理 `ks.cfg` 内的 tmux 终端劫持，精简 Go 安装器 console/TUI 冗余代码。

**Tech Stack:** Python 3, PyGObject (GTK3), Anaconda DBus (NETWORK), xorriso, SquashFS-tools (unsquashfs/mksquashfs)

---

### Task 1: 创建 Python Addon 目录与核心包声明

**Files:**
- Create: `package/vdi-os/anaconda/addons/vdi/__init__.py`
- Create: `package/vdi-os/anaconda/addons/vdi/gui/__init__.py`
- Create: `package/vdi-os/anaconda/addons/vdi/gui/spokes/__init__.py`

- [ ] **Step 1: 编写核心入口 `vdi/__init__.py`**

创建并编写 [__init__.py](file:///home/zcq/Github/VDI/package/vdi-os/anaconda/addons/vdi/__init__.py)：
```python
from pyanaconda.addons import AnacondaAddon

class VdiAddon(AnacondaAddon):
    """VDI 平台定制化参数注册模型"""
    def __init__(self):
        super().__init__()
        self.interface = ""
        self.method = "static"
        self.ip = "192.168.10.10"
        self.netmask = "255.255.255.0"
        self.gateway = "192.168.10.1"
        self.dns = "8.8.8.8"
        self.vip = "192.168.10.100"

    def execute(self, storage, ksdata, instClass):
        pass
```

- [ ] **Step 2: 创建模块声明文件**

创建空白文件 [package/vdi-os/anaconda/addons/vdi/gui/__init__.py](file:///home/zcq/Github/VDI/package/vdi-os/anaconda/addons/vdi/gui/__init__.py) 与 [package/vdi-os/anaconda/addons/vdi/gui/spokes/__init__.py](file:///home/zcq/Github/VDI/package/vdi-os/anaconda/addons/vdi/gui/spokes/__init__.py)：
```python
# 标记包存在，保持空内容即可
```

- [ ] **Step 3: Commit**
```bash
git add package/vdi-os/anaconda/addons/vdi/
git commit -m "feat(addon): 初始化 Anaconda Addon 包结构与数据模型"
```

---

### Task 2: 编写 Glade 界面 XML 布局

**Files:**
- Create: `package/vdi-os/anaconda/addons/vdi/ui/vdi_network.glade`

- [ ] **Step 1: 编写 XML 布局**

创建并编写 [vdi_network.glade](file:///home/zcq/Github/VDI/package/vdi-os/anaconda/addons/vdi/ui/vdi_network.glade)：
```xml
<?xml version="1.0" encoding="UTF-8"?>
<interface>
  <requires lib="gtk+" version="3.20"/>
  <object class="GtkBox" id="vdi_network_box">
    <property name="visible">True</property>
    <property name="can_focus">False</property>
    <property name="orientation">vertical</property>
    <property name="spacing">10</property>
    <child>
      <object class="GtkLabel" id="title_label">
        <property name="visible">True</property>
        <property name="label" translatable="yes">VDI 管理网络配置 (VDI Management Network)</property>
        <attributes>
          <attribute name="weight" value="bold"/>
        </attributes>
      </object>
    </child>
    <child>
      <object class="GtkGrid" id="config_grid">
        <property name="visible">True</property>
        <property name="row_spacing">6</property>
        <property name="column_spacing">12</property>
        <child>
          <object class="GtkLabel" id="ip_label">
            <property name="visible">True</property>
            <property name="label" translatable="yes">IPv4 地址:</property>
          </object>
          <packing>
            <property name="left_attach">0</property>
            <property name="top_attach">0</property>
          </packing>
        </child>
        <child>
          <object class="GtkEntry" id="ip_entry">
            <property name="visible">True</property>
            <property name="text">192.168.10.10</property>
          </object>
          <packing>
            <property name="left_attach">1</property>
            <property name="top_attach">0</property>
          </packing>
        </child>
        <child>
          <object class="GtkLabel" id="vip_label">
            <property name="visible">True</property>
            <property name="label" translatable="yes">集群虚拟 IP:</property>
          </object>
          <packing>
            <property name="left_attach">0</property>
            <property name="top_attach">1</property>
          </packing>
        </child>
        <child>
          <object class="GtkEntry" id="vip_entry">
            <property name="visible">True</property>
            <property name="text">192.168.10.100</property>
          </object>
          <packing>
            <property name="left_attach">1</property>
            <property name="top_attach">1</property>
          </packing>
        </child>
      </object>
    </child>
  </object>
</interface>
```

- [ ] **Step 2: Commit**
```bash
git add package/vdi-os/anaconda/addons/vdi/ui/vdi_network.glade
git commit -m "feat(addon): 添加网卡与VIP配置的 Glade XML 界面文件"
```

---

### Task 3: 编写 Spoke 交互逻辑

**Files:**
- Create: `package/vdi-os/anaconda/addons/vdi/gui/spokes/vdi_network.py`

- [ ] **Step 1: 实现 Spoke 类逻辑**

创建并编写 [vdi_network.py](file:///home/zcq/Github/VDI/package/vdi-os/anaconda/addons/vdi/gui/spokes/vdi_network.py)：
```python
from pyanaconda.ui.gui.spokes import NormalSpoke
from pyanaconda.core.dbus import get_proxy
from pyanaconda.modules.common.constants.services import NETWORK

class VdiNetworkSpoke(NormalSpoke):
    """VDI 管理网络图形配置子页"""
    builderObjects = ["vdi_network_box", "ip_entry", "vip_entry"]
    mainWidgetName = "vdi_network_box"
    uiFile = "vdi_network.glade"
    title = "VDI Network"

    def __init__(self, data, storage, payload):
        super().__init__(data, storage, payload)
        self.network_proxy = get_proxy(NETWORK)

    def refresh(self):
        # 刷新界面各字段数据绑定
        self.ip_entry = self.builder.get_object("ip_entry")
        self.vip_entry = self.builder.get_object("vip_entry")
        
        self.ip_entry.set_text(self.data.addons.vdi.ip or "192.168.10.10")
        self.vip_entry.set_text(self.data.addons.vdi.vip or "192.168.10.100")

    def apply(self):
        # 从界面写回数据模型
        self.data.addons.vdi.ip = self.ip_entry.get_text()
        self.data.addons.vdi.vip = self.vip_entry.get_text()

    def execute(self):
        # 后台提交阶段执行
        pass
```

- [ ] **Step 2: Commit**
```bash
git add package/vdi-os/anaconda/addons/vdi/gui/spokes/vdi_network.py
git commit -m "feat(addon): 编写 VdiNetworkSpoke 控制器逻辑"
```

---

### Task 4: 更新构建脚本以注入插件到 SquashFS

**Files:**
- Modify: `scripts/package-vdi-iso`

- [ ] **Step 1: 在 ISO 打包脚本中加入 unsquashfs 与 mksquashfs 重构逻辑**

使用编辑器修改 [package-vdi-iso](file:///home/zcq/Github/VDI/scripts/package-vdi-iso#L107-L113) 注入段，加入对 `images/install.img` 的解包注入和重新打包操作：
```diff
 VDI_INSTALLER_BIN="${VDI_INSTALLER_BIN:-${TOP_DIR}/bin/vdi-installer}"
-if [ -x "${VDI_INSTALLER_BIN}" ]; then
-    echo "  打包 vdi-installer 进 ISO"
-    mkdir -p "${ISO_ROOTFS}/vdi"
-    cp -f "${VDI_INSTALLER_BIN}" "${ISO_ROOTFS}/vdi/vdi-installer"
-    chmod +x "${ISO_ROOTFS}/vdi/vdi-installer"
-else
-    echo "ERROR: 找不到 vdi-installer 二进制: ${VDI_INSTALLER_BIN}，请先编译。" >&2
-    exit 1
-fi
+
+echo ">>> 解压并重构 install.img (注入 VDI Addon)"
+rm -rf ${CACHE_DIR}/install-rootfs
+unsquashfs -d ${CACHE_DIR}/install-rootfs ${ISO_ROOTFS}/images/install.img
+mkdir -p ${CACHE_DIR}/install-rootfs/usr/share/anaconda/addons
+cp -r ${TOP_DIR}/package/vdi-os/anaconda/addons/vdi ${CACHE_DIR}/install-rootfs/usr/share/anaconda/addons/
+rm -f ${ISO_ROOTFS}/images/install.img
+mksquashfs ${CACHE_DIR}/install-rootfs ${ISO_ROOTFS}/images/install.img -comp xz
+rm -rf ${CACHE_DIR}/install-rootfs
```

- [ ] **Step 2: Commit**
```bash
git add scripts/package-vdi-iso
git commit -m "feat(build): 构建流程集成 unsquashfs 重新打包机制注入 Anaconda 插件"
```

---

### Task 5: 清理过时交互与冗余 TUI 代码

**Files:**
- Modify: `package/vdi-os/ks/ks.cfg`
- Modify: `pkg/console/console.go`

- [ ] **Step 1: 精简 ks.cfg 中的 %pre，删去 tmux 劫持及前台阻塞逻辑**

修改 [ks.cfg](file:///home/zcq/Github/VDI/package/vdi-os/ks/ks.cfg#L17-L107)：
```diff
 %pre --interpreter=/bin/bash
-
-# 1. 确保挂载 ISO 介质以访问 vdi-installer 二进制与离线安装包
-ISO_MOUNT="/run/install/repo"
-if [ ! -d "${ISO_MOUNT}/vdi" ]; then
-    echo "正在尝试挂载 ISO 安装介质..."
-    mkdir -p ${ISO_MOUNT}
-    mount -t iso9660 -o ro /dev/sr0 ${ISO_MOUNT} || mount -t iso9660 -o ro /dev/cdrom ${ISO_MOUNT} || true
-fi
-
-INSTALLER_BIN="${ISO_MOUNT}/vdi/vdi-installer"
-ALT_BIN=$(find ${ISO_MOUNT} -name vdi-installer -print -quit)
-
-# 2. 判断是否是全自动化安装模式（从 /proc/cmdline 检测 vdi.install.automatic=true）
-if grep -q "vdi.install.automatic=true" /proc/cmdline; then
-    echo ">>> [pre] 检测到自动化安装参数，静默渲染安装配置" > /dev/ttyS0
-    # 显式 --auto-install 强制走 AutoInstall（不依赖二进制自检 cmdline），输出重定向串口诊断
-    if [ -x "${INSTALLER_BIN}" ]; then
-        echo ">>> [pre] 调用 ${INSTALLER_BIN} --auto-install" > /dev/ttyS0
-        "${INSTALLER_BIN}" --auto-install --ks-out /tmp/ks-include.cfg > /dev/ttyS0 2>&1
-        echo ">>> [pre] vdi-installer 退出码 $?, ks-include 存在: $([ -f /tmp/ks-include.cfg ] && echo yes || echo no)" > /dev/ttyS0
-    elif [ -n "${ALT_BIN}" ] && [ -x "${ALT_BIN}" ]; then
-        "${ALT_BIN}" --auto-install --ks-out /tmp/ks-include.cfg > /dev/ttyS0 2>&1
-    else
-        vdi-installer --auto-install --ks-out /tmp/ks-include.cfg > /dev/ttyS0 2>&1
-    fi
-else
-    # 3. 交互式 TUI 安装模式
-    # 关键：在 anaconda 自有 tmux 调试会话内开新 window 跑 vdi-installer。
-    # tmux pane 是独立 pty slave，termbox open 它后是唯一 reader（无键盘竞争），
-    # 且不动 tmux/getty/logind/VT → 不破坏 anaconda → 无死循环。
-    # 历史踩坑：曾用 chvt + stop getty + pkill tmux 清场，破坏 anaconda 基础设施
-    # 导致 %pre 死循环（55 次/7分钟）；grabTTY 也无法夺走 shell 已 open 的 tty fd。
-    # 用户按 Ctrl+Alt+F1 进 anaconda tmux，切到 vdi window 操作配置 TUI。
-    TMUX_SESS=$(tmux ls -F '#{session_name}' 2>/dev/null | head -1)
-    if [ -n "${TMUX_SESS}" ] && command -v tmux >/dev/null; then
-        echo ">>> [pre] 在 tmux 会话 ${TMUX_SESS} 开 vdi window" > /dev/ttyS0
-        rm -f /tmp/vdi-done
-        # vdi-installer 退出后显示配置完成提示并挂起 pane（避免 tmux 显示 "Pane is dead"
-        # 让用户误以为出错）。echo 退出码到 /tmp/vdi-done 解除 %pre 阻塞，随后 pane 用
-        # read 挂起保留"正在装机"提示，直到 anaconda 装机完成触发 reboot（pane 随进程树销毁）。
-        tmux new-window -t "${TMUX_SESS}" -n vdi \
-            "env TTY=\$(tty) TERM=linux ${INSTALLER_BIN}; echo \$? > /tmp/vdi-done; clear; echo '============================================'; echo ' VDI 配置已完成，Anaconda 正在安装系统...'; echo ' 请勿操作，等待安装完成自动重启。'; echo ' 安装进度切回 anaconda 主界面查看（Ctrl+Alt+F1）'; echo '============================================'; sleep 86400"
-        {
-            echo "============================================"
-            echo " VDI 交互配置已启动（tmux window: vdi）"
-            echo " 按 Ctrl+Alt+F1 进入 anaconda tmux"
-            echo " 按 Ctrl+B 再按 W 选 vdi window 操作配置"
-            echo "============================================"
-        } > /dev/tty1 2>/dev/null
-        echo ">>> [pre] 请按 Ctrl+Alt+F1 进 tmux，切到 vdi window 操作 TUI" > /dev/ttyS0
-        # 阻塞至 vdi-installer 退出（生成 /tmp/vdi-done），保证 %include 时序
-        while [ ! -f /tmp/vdi-done ]; do sleep 1; done
-        rm -f /tmp/vdi-done
-    else
-        # 兜底（无 tmux，如 qemu 自动路径或异常环境）：退化为直接前台跑
-        echo ">>> [pre] 无 tmux，直接前台跑 vdi-installer" > /dev/ttyS0
-        export TERM=linux
-        "${INSTALLER_BIN}"
-    fi
-fi
-
-# 4. 兜底保护：如果因未完成交互或环境异常未能生成 ks-include.cfg，则在此利用 --auto-install 生成默认配置
-if [ ! -f /tmp/ks-include.cfg ]; then
-    echo "未检测到动态安装配置，正在使用默认配置进行兜底安装..."
-    if [ -x "${INSTALLER_BIN}" ]; then
-        "${INSTALLER_BIN}" --auto-install --ks-out /tmp/ks-include.cfg || true
-    elif [ -n "${ALT_BIN}" ] && [ -x "${ALT_BIN}" ]; then
-        "${ALT_BIN}" --auto-install --ks-out /tmp/ks-include.cfg || true
-    else
-        vdi-installer --auto-install --ks-out /tmp/ks-include.cfg || true
-    fi
-fi
-
-# 确认文件存在
-if [ ! -f /tmp/ks-include.cfg ]; then
-    echo "ERROR: 无法生成任何 Kickstart 配置段！装机无法继续。"
-    exit 1
-fi
-
-# 5. 调试诊断：将 vdi-installer 运行日志输出到物理串口，便于无人值守时排查
-if [ -f /var/log/console.log ]; then
-    echo "--- vdi-installer 日志输出 (ttyS0) ---" > /dev/ttyS0
-    cat /var/log/console.log > /dev/ttyS0 || true
-    echo "--- vdi-installer 日志输出结束 (ttyS0) ---" > /dev/ttyS0
-fi
-
-echo "配置收集完成，正在切回安装器界面，接下来将由 Anaconda 接管安装..."
-sleep 2
-clear
+echo ">>> [pre] VDI 预检开始" > /dev/ttyS0
+# 仅生成最基础的默认 kickstart 配置段做 Anaconda 兜底启动
+echo "autostep --check" > /tmp/ks-include.cfg
+echo ">>> [pre] VDI 预检结束" > /dev/ttyS0
 %end
```

- [ ] **Step 2: 清理 Go 代码中过时的 console/TUI 包引用**

修改 [console.go](file:///home/zcq/Github/VDI/pkg/console/console.go#L85-L118) 将 RunConsole 设为空操作或精简版，并删除 UI 包引用：
```diff
 func RunConsole() error {
-	if tty := os.Getenv("TTY"); tty != "" && os.Getenv("TMUX") == "" {
-		if err := grabTTY(tty); err != nil {
-			dbgSerial("grabTTY(%s) 失败: %v（键盘可能仍被 shell 抢）", tty, err)
-		} else {
-			dbgSerial("grabTTY OK: 已抢 %s 前台独占键盘", tty)
-		}
-	}
-	c, err := NewConsole()
-	if err != nil {
-		return err
-	}
-	if err := initLogs(); err != nil {
-		return err
-	}
-
-	if w, h := c.Gui.Size(); w < 80 || h < 24 {
-		return fmt.Errorf("terminal size %dx%d too small for TUI (need >= 80x24); ensure start-installer.sh sets winsize via stty", w, h)
-	}
-
-	err = c.doRun()
-	if err != nil {
-		logrus.Errorf("console.doRun() failed: %v", err)
-	}
-	return err
+	return nil
 }
```

- [ ] **Step 3: 运行 Go 测试确认无编译报错**
```bash
go test ./pkg/...
```

- [ ] **Step 4: Commit**
```bash
git add package/vdi-os/ks/ks.cfg pkg/console/console.go
git commit -m "refactor(cleanup): 移除旧方案的 tmux 拦截及控制台 gocui 模块"
```
