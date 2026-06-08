---
name: kagent-deploy
description: 部署 kagent AI Agent 框架到 K8s 集群。当用户提到"部署 kagent"、"安装 kagent"、"AI Agent"、"智能运维"、"kagent"时触发。支持多种 LLM Provider（OpenAI/Anthropic/Ollama），内置 K8s 运维工具。
---

# kagent AI Agent 框架部署

在 Kubernetes 集群上部署 kagent，提供 AI 驱动的集群运维和 VM 管理能力。

## 前置条件

- K8s 集群已就绪（节点 Ready）
- CNI 已部署（如 Kube-OVN）
- 存储已部署（如 Longhorn）
- `kubectl` 和 `helm` 命令可用
- kagent 源码位于 `/home/zcq/Github/kagent/`

## 执行流程

### Step 0: 环境检查

```bash
# 加载共享配置
source deploy/env-config.sh

# 检查 helm
if ! command -v helm &>/dev/null; then
  echo "错误: helm 未安装" >&2
  exit 1
fi

# 检查集群状态
kubectl get nodes -o wide

# 检查 kagent 源码目录
if [ ! -d "/home/zcq/Github/kagent/helm" ]; then
  echo "错误: kagent 源码目录不存在" >&2
  exit 1
fi
```

### Step 1: 准备 Helm Chart

kagent 的 Chart.yaml 是模板文件，需要先生成：

```bash
KAGENT_SRC="/home/zcq/Github/kagent"
VERSION="0.9.6"  # 使用发布版本

# 生成 Chart.yaml
cat > "${KAGENT_SRC}/helm/kagent-crds/Chart.yaml" <<EOF
apiVersion: v2
name: kagent-crds
description: CRDs for kagent
type: application
version: ${VERSION}
EOF

cat > "${KAGENT_SRC}/helm/kagent/Chart.yaml" <<EOF
apiVersion: v2
name: kagent
description: A Helm chart for kagent, built with Google ADK
type: application
version: ${VERSION}
dependencies:
  - name: kagent-tools
    version: 0.1.3
    repository: oci://ghcr.io/kagent-dev/tools/helm
    condition: kagent-tools.enabled
  - name: grafana-mcp
    version: ${VERSION}
    repository: file://../tools/grafana-mcp
    condition: grafana-mcp.enabled, observability-agent.enabled
  - name: querydoc
    version: ${VERSION}
    repository: file://../tools/querydoc
    condition: querydoc.enabled
  - name: k8s-agent
    version: ${VERSION}
    repository: file://../agents/k8s
    condition: k8s-agent.enabled
  - name: helm-agent
    version: ${VERSION}
    repository: file://../agents/helm
    condition: helm-agent.enabled
EOF

# 生成子 chart 的 Chart.yaml
for dir in helm/agents/k8s helm/agents/helm helm/tools/grafana-mcp helm/tools/querydoc; do
  if [ -f "${KAGENT_SRC}/${dir}/Chart-template.yaml" ]; then
    VERSION=${VERSION} envsubst < "${KAGENT_SRC}/${dir}/Chart-template.yaml" > "${KAGENT_SRC}/${dir}/Chart.yaml"
  fi
done

# 更新依赖
helm dependency update "${KAGENT_SRC}/helm/kagent"
```

### Step 2: 安装 kagent CRDs

```bash
helm install kagent-crds "${KAGENT_SRC}/helm/kagent-crds/" \
  -n kagent \
  --create-namespace
```

验证 CRD 安装：
```bash
kubectl get crd | grep kagent.dev
```

### Step 3: 安装 kagent

```bash
helm install kagent "${KAGENT_SRC}/helm/kagent/" \
  -n kagent \
  --set registry=ghcr.io \
  --set tag=${VERSION} \
  --set oauth2-proxy.enabled=false \
  --set builtInAgents.k8s-agent.enabled=true \
  --set builtInAgents.helm-agent.enabled=true \
  --set builtInAgents.istio-agent.enabled=false \
  --set builtInAgents.kgateway-agent.enabled=false \
  --set builtInAgents.promql-agent.enabled=false \
  --set builtInAgents.observability-agent.enabled=false \
  --set builtInAgents.argo-rollouts-agent.enabled=false \
  --set builtInAgents.cilium-policy-agent.enabled=false \
  --set builtInAgents.cilium-manager-agent.enabled=false \
  --set builtInAgents.cilium-debug-agent.enabled=false
```

### Step 4: 创建占位 Secret

Agent 启动需要 API Key Secret，先创建占位值，后续在 UI 中替换：

```bash
kubectl create secret generic kagent-openai \
  -n kagent \
  --from-literal=OPENAI_API_KEY=placeholder-replace-in-ui
```

### Step 5: 验证部署

```bash
# 检查 Pod 状态（所有 Pod 应为 Running）
kubectl get pods -n kagent -o wide

# 检查 Agent 状态
kubectl get agents -n kagent -o wide

# 访问 UI（本地端口转发）
kubectl port-forward -n kagent svc/kagent-ui 8080:8080
# 浏览器打开 http://localhost:8080
```

**预期状态**：
- kagent-controller: Running
- kagent-ui: Running
- kagent-postgresql: Running（内置数据库）
- kagent-tools: Running（MCP 工具服务）

### Step 6: 配置 LLM Provider

部署完成后，在 Web UI 中添加 LLM Provider：

1. 打开 `http://localhost:8080`
2. 进入 **Models** 页面
3. 点击 **New Model**
4. 选择 Provider（OpenAI / Anthropic / Ollama 等）
5. 填写 API Key 和模型名称
6. 保存

### Step 7: 部署 VDI 专用 Agent

```bash
kubectl apply -f deploy/kagent/agents/
```

验证 Agent 创建：
```bash
kubectl get agents -n kagent -o wide
```

## 镜像清单

| 镜像 | 来源 | 说明 |
|------|------|------|
| `ghcr.io/kagent-dev/kagent/controller:0.9.6` | ghcr.io | 控制器 |
| `ghcr.io/kagent-dev/kagent/ui:0.9.6` | ghcr.io | Web UI |
| `ghcr.io/kagent-dev/kagent/tools:0.1.3` | ghcr.io | MCP 工具集 |
| `ghcr.io/kagent-dev/doc2vec/mcp:1.1.14` | ghcr.io | 文档查询 |
| `docker.io/library/postgres:18.3-alpine` | Docker Hub | 内置数据库 |

> ⚠️ 默认 registry 是 `cr.kagent.dev`，国内网络可能无法访问。部署时需指定 `--set registry=ghcr.io`。

## 部署文件说明

| 文件 | 说明 |
|------|------|
| `deploy/kagent/agents/vdi-cluster-doctor.yaml` | 集群健康诊断 Agent |
| `deploy/kagent/agents/vdi-vm-manager.yaml` | VM 管理 Agent |
| `deploy/kagent/agents/vdi-storage-ops.yaml` | 存储运维 Agent |
| `deploy/kagent/agents/vdi-network-debug.yaml` | 网络诊断 Agent |

## 常见问题

### 1. Pod CreateContainerConfigError

**原因**：Agent 依赖的 Secret（如 `kagent-openai`）不存在。

**解决**：
```bash
kubectl create secret generic kagent-openai \
  -n kagent \
  --from-literal=OPENAI_API_KEY=placeholder-replace-in-ui
```

### 2. 镜像拉取失败

**原因**：默认 registry `cr.kagent.dev` 国内不可达。

**解决**：部署时指定 `--set registry=ghcr.io --set tag=0.9.6`

### 3. Agent 创建报 strict decoding error

**原因**：Agent CRD 的 tools 字段格式错误。

**正确格式**：
```yaml
tools:
  - mcpServer:
      apiGroup: kagent.dev
      kind: RemoteMCPServer
      name: kagent-tool-server
      toolNames:
        - k8s_get_resources
        - k8s_describe_resource
    type: McpServer
```

## 后续步骤

kagent 部署完成后，可继续：
- 在 UI 中创建自定义 Agent
- 配置 MCP 工具服务器
- 集成 Prometheus/Grafana 监控
- 配置 OTEL tracing
