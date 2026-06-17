# 快速测试指南 - BIOS/UEFI 引导修复验证

## 🎯 修复内容
- **问题**：GPT分区缺少BIOS Boot分区 → grub-install失败 → 重启进PXE
- **修复**：添加1MB BIOS Boot分区（类型ef02）

## ⚡ 快速测试（QEMU）

### 1. 等待构建完成
```bash
# 检查构建状态
docker ps | grep vdi-iso-builder

# 构建完成后检查ISO
ls -lh dist/vdi-offline-v1.0.0.iso
```

### 2. 运行快速引导测试
```bash
cd iso-builder
./scripts/quick-test-boot.sh both
```

**预期输出**：
```
[INFO] ✓ QEMU 启动成功（输出 xxx 行）
[INFO] ✓ 检测到 GRUB 引导
[INFO] ✓ 检测到 Linux 内核启动
[INFO] ✓ 检测到 Live 环境启动
```

### 3. 详细测试（可选）

**BIOS模式测试**：
```bash
./scripts/test-qemu-boot.sh bios
```

**UEFI模式测试**：
```bash
./scripts/test-qemu-boot.sh uefi
```

## 🖥️ VMware 测试

### 测试步骤
1. **创建新虚拟机**
   - 操作系统：Linux → Ubuntu 64位
   - 硬盘：20GB，内存：4GB
   - **不要**挂载ISO（稍后挂载）

2. **配置虚拟机**
   - 编辑设置 → CD/DVD
   - 选择"使用ISO镜像文件"
   - 浏览到 `dist/vdi-offline-v1.0.0.iso`
   - 勾选"启动时连接"

3. **启动并装机**
   - 启动虚拟机
   - 选择模式 1/2/3
   - 完成配置向导
   - 等待装机完成

4. **关键验证步骤**
   - 看到 "OS Installation Phase 1 Complete!"
   - 关闭虚拟机（不要重启）
   - 编辑设置 → CD/DVD → **取消勾选**"启动时连接"
   - 启动虚拟机

5. **验证结果**
   - ✅ **成功**：从磁盘引导，看到登录提示或继续Phase 2
   - ❌ **失败**：显示"No bootable device"或进入PXE

## 🔍 验证分区布局

在装机过程中或完成后检查：

```bash
# 切换到tty2 (Ctrl+Alt+F2)
sudo sgdisk -p /dev/sda

# 预期看到4个分区：
# Number  Start      End        Size       Code  Name
#    1     2048       4095       512.0 KiB  EF02  BIOS Boot  ← 关键！
#    2     4096       1052671    512.0 MiB  EF00  EFI System
#    3     1052672    17829887   8.0 GiB    8200  Linux Swap
#    4     17829888   41943006   11.5 GiB   8300  Linux Root
```

## 🐛 故障排除

### 问题1：QEMU测试无输出
**原因**：ISO可能未正确构建
**解决**：
```bash
sudo make clean && sudo make iso
```

### 问题2：VMware仍进入PXE
**检查**：
1. 确认使用新ISO（检查构建时间）
2. 确认已断开ISO（不是删除，是取消勾选"启动时连接"）
3. 确认虚拟机是BIOS模式（默认）

**调试**：
```bash
# 在装机完成后的Live环境中检查
ls -la /mnt/target/boot/grub/i386-pc/
# 应该有 core.img 文件

ls -la /mnt/target/boot/efi/EFI/
# 应该有 VDI 和 BOOT 目录
```

### 问题3：找不到OVMF固件（UEFI测试）
**解决**：
```bash
sudo apt install ovmf
```

## 📋 测试检查清单

### BIOS模式测试
- [ ] ISO能正常启动
- [ ] 看到GRUB菜单
- [ ] 选择安装后进入Live环境
- [ ] TUI安装器正常运行
- [ ] 装机流程完成
- [ ] 重启后从磁盘引导（不进PXE）

### UEFI模式测试
- [ ] ISO能正常启动（UEFI模式）
- [ ] 看到GRUB UEFI菜单
- [ ] 选择安装后进入Live环境
- [ ] TUI安装器正常运行
- [ ] 装机流程完成
- [ ] 重启后从磁盘UEFI引导（不进PXE）

### 分区验证
- [ ] 包含BIOS Boot分区（1MB, ef02）
- [ ] 包含EFI分区（512MB, ef00）
- [ ] 包含Swap分区（可选）
- [ ] 包含Root分区

### VMware验证
- [ ] 虚拟机设置正确（BIOS模式）
- [ ] ISO挂载并能启动
- [ ] 装机完成后断开ISO
- [ ] 重启后从磁盘引导

## 🎉 成功标志

如果测试通过，你应该看到：

1. **QEMU测试**：
   ```
   [INFO] ✓ 检测到 GRUB 引导
   [INFO] ✓ 检测到 Linux 内核启动
   ```

2. **VMware测试**：
   - 装机后重启，不再显示"No bootable device"
   - 不再进入PXE引导
   - 直接从磁盘启动系统

## 📞 需要帮助？

如果测试失败：
1. 查看详细日志：`/var/log/vdi-deploy/installer.log`
2. 检查分区布局：`sudo sgdisk -p /dev/sda`
3. 验证GRUB安装：`ls -la /mnt/target/boot/grub/`
4. 参考完整文档：`TESTING.md`
