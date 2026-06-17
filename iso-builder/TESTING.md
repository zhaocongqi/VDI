# VDI ISO 引导测试指南

## 问题背景

**原始问题**：VMware装机完成后，移除CDROM重启，提示"找不到操作系统"，进入PXE。

**根本原因**：GPT分区表缺少BIOS Boot分区（1MB, ef02），导致`grub-install --target=i386-pc`失败。

**修复内容**：
- 在分区时添加BIOS Boot分区（第1分区，1MB，类型ef02）
- 优化grub-install参数（添加--force和--recheck）
- 完善chroot环境（添加/dev/disk挂载）

## 测试步骤

### 前置条件

1. **构建修复后的ISO**
   ```bash
   cd iso-builder
   sudo make clean
   sudo make iso
   ```

2. **检查ISO文件**
   ```bash
   ls -lh dist/vdi-offline-v1.0.0.iso
   ```

### 测试方案1：快速引导测试（推荐）

使用QEMU快速验证ISO是否能正常引导：

```bash
cd iso-builder
./scripts/quick-test-boot.sh both
```

**预期输出**：
- 看到"✓ 检测到 GRUB 引导"
- 看到"✓ 检测到 Linux 内核启动"
- 看到"✓ 检测到 Live 环境启动"

### 测试方案2：完整装机测试（BIOS模式）

模拟VMware默认的BIOS引导模式：

```bash
cd iso-builder
./scripts/test-qemu-boot.sh bios
```

**测试要点**：
1. 启动后应看到GRUB菜单
2. 选择"Install VDI Cluster"
3. 完成装机流程
4. 重启后应该从磁盘引导（不进入PXE）

### 测试方案3：完整装机测试（UEFI模式）

测试UEFI引导兼容性：

```bash
cd iso-builder
./scripts/test-qemu-boot.sh uefi
```

**测试要点**：
1. 启动后应看到GRUB UEFI菜单
2. 选择"Install VDI Cluster"
3. 完成装机流程
4. 重启后应该从磁盘UEFI引导（不进入PXE）

### 测试方案4：VMware实际测试

1. **创建新VMware虚拟机**
   - 选择"稍后安装操作系统"
   - 客户机操作系统：Linux，Ubuntu 64位
   - 硬盘：20GB
   - 内存：4GB
   - 网络：NAT或桥接

2. **挂载ISO**
   - 编辑虚拟机设置
   - CD/DVD → 使用ISO镜像文件 → 选择`dist/vdi-offline-v1.0.0.iso`
   - 设备状态：勾选"启动时连接"

3. **启动并装机**
   - 启动虚拟机
   - 选择部署模式（1/2/3）
   - 完成配置
   - 等待装机完成

4. **验证修复**
   - 装机完成后，提示"Remove CD-ROM"
   - **关键步骤**：关闭虚拟机 → 编辑设置 → CD/DVD → 取消勾选"启动时连接"或断开ISO
   - 重新启动虚拟机
   - **预期结果**：从磁盘引导，不进入PXE

## 验证分区布局

装机完成后，可以在Live环境或安装后的系统中检查分区：

```bash
# 查看分区表
sudo sgdisk -p /dev/sda

# 预期输出（4个分区）：
# Number  Start (sector)    End (sector)  Size       Code  Name
#    1            2048            4095   512.0 KiB   EF02  BIOS Boot
#    2            4096         1052671   512.0 MiB   EF00  EFI System
#    3         1052672        17829887   8.0 GiB     8200  Linux Swap
#    4        17829888       41943006   11.5 GiB    8300  Linux Root
```

## 常见问题

### Q1: QEMU测试时提示"找不到OVMF固件"

**解决方案**：
```bash
sudo apt install ovmf
```

### Q2: QEMU启动后没有看到GRUB菜单

**可能原因**：
- ISO构建失败
- ISO文件损坏
- QEMU参数错误

**解决方案**：
1. 重新构建ISO：`sudo make clean && sudo make iso`
2. 检查ISO完整性：`file dist/vdi-offline-v1.0.0.iso`
3. 查看QEMU输出日志

### Q3: VMware测试时仍然进入PXE

**检查清单**：
1. 确认使用的是新构建的ISO（包含修复）
2. 确认装机流程完成（看到"OS Installation Phase 1 Complete!"）
3. 确认已移除/断开ISO
4. 确认虚拟机设置为BIOS引导（默认）

**调试步骤**：
1. 在装机完成后，切换到tty2（Ctrl+Alt+F2）
2. 检查分区：
   ```bash
   sgdisk -p /dev/sda
   ```
3. 检查GRUB安装：
   ```bash
   ls -la /mnt/target/boot/grub/
   ls -la /mnt/target/boot/efi/EFI/
   ```

### Q4: 构建ISO失败

**常见原因**：
- 权限不足：使用`sudo`
- Docker未运行：`sudo systemctl start docker`
- 磁盘空间不足：`df -h`

**解决方案**：
```bash
# 清理并重新构建
sudo make distclean
sudo make iso
```

## 技术细节

### 为什么需要BIOS Boot分区？

GPT（GUID Partition Table）是现代磁盘分区表格式，但传统的BIOS引导方式（MBR）无法直接从GPT磁盘引导。

**解决方案**：
- 在GPT磁盘上创建一个特殊的"BIOS Boot分区"（类型ef02）
- GRUB将`core.img`（第二阶段引导程序）写入这个分区
- BIOS从MBR代码跳转到BIOS Boot分区，再加载完整的GRUB

**分区布局**：
```
GPT磁盘 + BIOS引导：
├── BIOS Boot分区 (1MB, ef02) ← GRUB core.img
├── EFI分区 (512MB, ef00) ← UEFI引导（可选）
├── Swap分区 (8GB, 8200)
└── Root分区 (剩余空间, 8300)
```

### 为什么UEFI不需要这个分区？

UEFI固件直接从EFI系统分区（ESP）加载引导程序，不需要传统的MBR和BIOS Boot分区。

## 测试结果记录

### 测试1：快速引导测试
- 日期：
- 结果：
- 备注：

### 测试2：BIOS完整装机
- 日期：
- 结果：
- 备注：

### 测试3：UEFI完整装机
- 日期：
- 结果：
- 备注：

### 测试4：VMware实际测试
- 日期：
- VMware版本：
- 结果：
- 备注：
