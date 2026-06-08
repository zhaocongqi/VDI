# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

本仓库是一个自研云桌面 (VDI) 平台的全栈技术集合，包含五个独立的 Kubernetes 子项目，每个子项目拥有独立的 Git 仓库。顶层架构文档 `云桌面产品技术架构图.md` 描述了七层技术栈。

**七层架构**：
- L1 客户端层：Web 客户端、Tauri 原生客户端
- L2 媒体/接入层：Coturn TURN、Pion WebRTC、GStreamer
- L3 业务编排层：云桌面控制台、Session Broker
- L4 云桌面交付：Linux 容器 Pod、Windows VM
- L5 K8s 工作负载：KubeVirt、Longhorn、Kube-OVN、Prometheus Operator
- L6 K8s 编排：Kubernetes 控制平面
- L7 基础设施：物理服务器、网络、存储

## 子项目与组件关系

| 子项目 | 定位 | 语言 |
|--------|------|------|
| `kagent/` | CNCF：Kubernetes 原生 AI Agent 框架 | Go, Python, TypeScript |
| `kubekey/` | KubeSphere：K8s 集群生命周期管理工具 | Go |
| `kube-ovn/` | CNCF Sandbox：基于 OVN 的网络虚拟化 | Go |
| `kubevirt/` | CNCF：Kubernetes VM 管理插件 | Go |
| `longhorn/` | CNCF Incubating：分布式块存储 | Go (代码在其他仓库) |

**组件协作关系**：KubeKey 负责集群部署 → Kube-OVN 提供网络层 → Longhorn 提供存储层 → KubeVirt 运行 Windows 桌面 VM → kagent 提供 AI 驱动的监控与自愈能力。

## 各子项目构建命令速查

### kagent (`cd kagent`)
```bash
make build              # 构建所有组件镜像
make build-cli          # 构建 kagent CLI
make lint               # Go + Python 代码检查
make test               # 运行全部测试
make -C go generate     # 生成 CRD 代码
make -C go e2e          # 端到端测试
make create-kind-cluster  # 创建本地 Kind 集群
make helm-install       # 构建镜像 + 加载到 Kind + Helm 部署
make helm-test          # 渲染 Helm 模板并运行 helm unittest
```

### kubekey (`cd kubekey`)
```bash
make kk                 # 构建 kk 二进制
make generate           # 生成 deepcopy、manifests、modules、goimports
make lint               # golangci-lint
make test               # 单元测试 + 集成测试 (setup-envtest)
make verify             # 全部校验检查
```

### kube-ovn (`cd kube-ovn`)
```bash
make build-go           # 编译 Go 二进制 (linux/amd64)
make gen-crd            # 从 kubebuilder 注解重新生成 CRD YAML
make lint               # golangci-lint + Go "modernize"
make ut                 # 单元测试 (Ginkgo + go test with coverage)
make install-chart      # Helm 安装
make local-dev          # 完整本地开发环境搭建
```

### kubevirt (`cd kubevirt`)
```bash
make all                # 格式化 + bazel-build + manifests
make go-all             # Go build + manifests (不用 bazel)
make generate           # 生成代码、manifests、protobuf
make lint               # golangci-lint + license 检查
make test               # 运行测试
make functest           # 功能测试
make cluster-up         # 启动 CI 集群
```

### longhorn (`cd longhorn`)
本仓库仅包含 Helm chart、部署文档和增强提案。核心代码分布在 longhorn-manager、longhorn-engine 等其他仓库中。

## 关键技术栈

- **主要语言**：Go (所有子项目)、Python (kagent Agent 运行时)、TypeScript (kagent UI)
- **构建系统**：Make (通用)、Bazel (kubevirt)、Docker Buildx (kagent)
- **代码检查**：golangci-lint (Go)、Ruff (Python)
- **测试框架**：Ginkgo/Gomega (kube-ovn, kubevirt)、envtest (kubekey, kagent)、pytest (kagent Python)、Jest/Vitest (kagent UI)
- **部署方式**：Helm Charts (kagent, kubekey, kube-ovn, longhorn)、Operator 模式 (kubevirt)
- **Go 版本**：1.24.0 ~ 1.26.4 (各子项目不同)

## 部署目录结构

`deploy/` 目录包含完整的集群部署自动化：

```
deploy/
├── env-config.sh          # 共享环境配置（用户名、网段、VIP、版本号）
├── hosts.template         # Ansible 清单模板（实际 hosts 已 gitignore）
├── skills/                # AI Skill 定义（按组件拆分）
│   ├── os-init/           # OS 初始化（swap/内核/防火墙/依赖）
│   ├── kubekey-deploy-k8s/# K8s 集群部署
│   ├── kubevip-deploy/    # API Server VIP（HA static Pod）
│   ├── kubeovn-deploy/    # Kube-OVN CNI
│   ├── longhorn-deploy/   # Longhorn 分布式存储
│   ├── kubevirt-deploy/   # KubeVirt 虚拟化
│   └── kagent-deploy/     # kagent AI Agent 框架
├── kagent/                # kagent Agent CRD 定义
│   └── agents/            # VDI 专用 Agent（cluster-doctor/vm-manager/storage-ops/network-debug）
├── k8s/                   # KubeKey 配置和 inventory
├── kube-vip/              # kube-vip manifest 和脚本
├── kube-ovn/              # Kube-OVN 本地 Helm chart + values
├── longhorn/              # Longhorn values.yaml + 脚本
└── kubevirt/              # KubeVirt 脚本
```

**部署顺序**：os-init → kubekey-deploy-k8s → kubevip-deploy → kubeovn-deploy → longhorn-deploy → kubevirt-deploy → kagent-deploy

**关键约定**：
- `deploy/env-config.sh` 是所有部署参数的唯一来源，脚本和 skill 统一 `source` 引用
- `deploy/hosts` 和 `deploy/k8s/inventory.yaml` 含敏感信息，已在 `.gitignore` 排除，仅保留 `.template` 模板
- kube-vip 使用 static Pod 模式分发到每个控制平面节点，不使用 `kubectl apply`

## 子项目独立 CLAUDE.md

各子项目可能包含自己的 CLAUDE.md 文件，提供更细粒度的开发指南：
- `kagent/CLAUDE.md` — 架构详解、语言约定、测试模式
- `kube-ovn/CLAUDE.md` — 项目结构、构建命令、编码规范

工作时请先进入对应子项目目录，再参考其本地 CLAUDE.md。
