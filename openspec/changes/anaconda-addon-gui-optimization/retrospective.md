# Retrospective: anaconda-addon-gui-optimization

> Written: 2026-07-14 (after verify passed with warnings)
> Commit range: `64d9231c..6b19ff64`
> Worktree: /home/zcq/Github/VDI (feat/anaconda-addon 分支)

---

## 0. Evidence

- **Commit range**: `64d9231c..6b19ff64` (5 commits)
- **Diff size**: +1299 / -501 lines across 14 files
- **Tasks done**: 31/31 (`grep -cE '^\s*- \[x\]' tasks.md` → 31)
- **Active hours**: ~3h（含两轮 VNC 实测迭代）
- **Subagent dispatches**: n/a（全程主线执行）
- **New external dependencies**: none（校验用 Python 标准库 ipaddress）
- **Bugs encountered post-merge**: none（未推送，本地验证）
- **OpenSpec validate state at archive**: pass
- **Test coverage signal**: n/a（无自动化测试，VNC 人工 smoke 覆盖）

Commit chain (时序):

```
1f6750ef feat(addon): D-Bus 层新增 role/server_url/token/data_disk 属性
ae319226 feat(addon): kickstart 层新增 role/server_url/token/data-disk 参数
307cf667 feat(addon): installation 层适配 role 分流与数据盘指定
47f06e29 feat(addon): GUI Spoke 重构——4 分组 Frame + 实时校验 + 改名
6b19ff64 docs(openspec): 新增 anaconda-addon-gui-optimization 变更工件
```

---

## 1. Wins

- [evidence: 47f06e29 vdi_install_config.py:277-293] 实时校验三层纯函数（_is_valid_ipv4/_is_valid_cidr/_is_valid_netmask）+ _validation_errors Set 聚合，驱动 completed，错误前置到输入阶段，一次设计到位
- [evidence: 1f6750ef + 307cf667] D-Bus 属性三层贯通（interface→service→kickstart→installation→GUI）一次对齐，跨层字段名核对无返工
- [evidence: 47f06e29 git mv] 文件改名用 git mv 保留历史，rename 与内容改动分离提交，blame 可追溯
- [evidence: 热重载实测] 第二轮迭代用 hot-reload-addon 秒级注入而非重建 ISO，省去数分钟 ISO 重建

## 2. Misses

- 🔴 [blocking | evidence: 第一轮 VNC 实测"界面全揉在一起"] 自建 GtkScrolledWindow 包裹 4 Frame，Viewport 与 Anaconda Spoke 窗口高度协商失败，内容塌缩。修复：去掉 ScrolledWindow 回归 Box+Frame 直排（D9）
- 🟡 [painful | evidence: qemu 三次退出] nohup/setsid/run_in_background 启动的 qemu 均被会话回收，最终用 `sudo systemd-run --unit=vdi-qemu` 作为 transient service 才稳定驻留
- 🟡 [painful | evidence: CLAUDE.md 过时记录] "anaconda 安装环境 SSH 不可用"记录已过时，实测可用 vdi123 密码连入，hot-reload 脚本因不带密码报 Permission denied 误导排查
- 📌 [nit | evidence: verify §7] VNC 实测为人工 smoke，无等价自动化测试，GUI 布局/校验逻辑无回归保护

## 3. Plan deviations

| Plan task | What changed | Why |
|-----------|--------------|-----|
| D6 root 密码兜底 | 改为 D7 全删 | 实测发现 Anaconda 自带密码 Spoke，重复设置无必要 |
| 问题3 ScrolledWindow | 改为 D9 去 ScrolledWindow | ScrolledWindow 塌缩致界面揉在一起，回归直排 |
| 原计划范围 | 新增 Task 7（5 个实测反馈问题） | 第一轮 VNC 验证暴露原计划未覆盖的 UX 问题 |

## 4. Skill / workflow compliance

| Skill                                            | Used |
|--------------------------------------------------|------|
| superpowers:brainstorming                        | ✗ |
| superpowers:writing-plans                        | ✗ |
| superpowers:using-git-worktrees                  | ✗ |
| superpowers:subagent-driven-development          | ✗ |
| (transitive) superpowers:test-driven-development | ✗ |
| (transitive) superpowers:requesting-code-review  | ✗ |
| superpowers:finishing-a-development-branch       | ✗ |

### Deliberately Skipped Skills

- **superpowers:brainstorming / writing-plans**
  - **What was skipped**: 整个 brainstorm 与 plan 工件（本变更为事后补文档，代码已实现）
  - **Why this cycle**: 变更代码在 OpenSpec 工件链创建前已由前序会话实现完成，本次 cycle 是补齐文档而非正向规划；brainstorm/writing-plans 要求交互式决策链，对已实现代码属冗余
  - **How to prevent recurrence**: `scope-judgment rule` — 事后补文档场景，工件链从 design/tasks/plan 开始回写已实现决策，跳过 brainstorm；正向开发 cycle 必须完整走 brainstorm→plan

- **using-git-worktrees / subagent-driven-development**
  - **What was skipped**: worktree 隔离与 subagent 分发
  - **Why this cycle**: 改动集中在 6 个强耦合文件，D-Bus 属性必须三层同步，subagent 并行反而引入一致性风险；worktree 对单分支小改动无收益
  - **How to prevent recurrence**: `scope-judgment rule` — 强耦合三层同步改动用主线顺序执行，避免并行一致性陷阱

- **test-driven-development**
  - **What was skipped**: TDD 红绿循环
  - **Why this cycle**: Anaconda Addon 在安装环境运行，GUI/安装任务无本地可跑的单元测试框架，TDD 缺执行环境
  - **How to prevent recurrence**: `CLAUDE.md trigger` — 项目 CLAUDE.md 应记录 addon 测试策略（VNC smoke + ast.parse 静态检查），明确 TDD 不适用的边界

- **requesting-code-review / finishing-a-development-branch**
  - **What was skipped**: 代码审查与分支收尾
  - **Why this cycle**: 本地验证阶段，未到 PR/merge 节点
  - **How to prevent recurrence**: `one-off — schema boundary case`，verify 阶段未推送，finishing 留待归档后

## 5. Surprises

- **ScrolledWindow 在 Anaconda Spoke 里塌缩**：本以为加 vexpand + min_content_height 能撑开，实测 Viewport 与 Spoke 容器高度协商不可控，内容全揉在一起——GTK 容器嵌套在第三方窗口框架里的尺寸协商比预期脆弱
- **安装环境 SSH 可用**：CLAUDE.md 明确记录"SSH 不可用（banner exchange 超时）"，实测端口 2222 + vdi123 密码完全可连，hot-reload 可用——文档认知与实际状态偏差
- **qemu daemonize 仍被回收**：`-daemonize` 本应脱离父进程，但 nohup/setsid/run_in_background 包装下仍被会话清理，只有 systemd-run transient service 稳定

## 6. Promote candidates → long-term learning

- [x] 🟡 **改 addon 代码用热重载，不重建 ISO** → **Promote to memory** (type: feedback) — 已写入 [[addon-hot-reload-ssh]]
  > **Why**: 重建 ISO 需解包 BCLinux DVD 耗时数分钟，hot-reload-addon 秒级注入；CLAUDE.md"SSH 不可用"记录过时
  > **How to apply**: 改 addon Python/glade 代码 → dev-cycle reload；仅构建脚本/ISO 结构/kickstart 变更才重建 ISO

- [ ] 🔴 **qemu 用 systemd-run 启动才稳定驻留** → **Promote to project CLAUDE.md** (测试命令段)
  > **Why**: nohup/setsid/run_in_background 启动的 qemu 均被会话回收，反复退出浪费排查时间
  > **How to apply**: 长驻 qemu 用 `sudo systemd-run --unit=vdi-qemu ... qemu-test-ks`，dev-cycle start 适合一次性短测

- [ ] 🟡 **GTK 容器嵌套在 Anaconda Spoke 里慎用 ScrolledWindow** → **Promote to memory** (type: feedback)
  > **Why**: ScrolledWindow/Viewport 与 Spoke 容器高度协商失败致内容塌缩
  > **How to apply**: Anaconda Addon Spoke 布局优先 Box+Frame 直排，需要滚动时验证 Viewport 高度协商，避免自建滚动容器

- [ ] 📌 **Addon GUI 缺自动化测试** → **One-off** (记录 follow-up)
  > **Why**: GUI 布局/校验逻辑无回归保护，每次改动靠 VNC 人工 smoke
  > **How to apply**: follow-up——探索 Gtk 测试或校验函数单元测试，至少覆盖 _is_valid_* 纯函数
