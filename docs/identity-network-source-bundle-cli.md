# 独立源码 bundle 核验（不上云、不启动）

入口：`python -m agent_ex.identity_network.source_cli verify`。
它只核验显式批准记录与 pinned bundle 内容，不上传、checkout、导入原仓库、启动服务
或发送模型请求。输出为脱敏 JSON（commit/tree/bundle hashes及绑定的intent/receipt）。

## 输入

`--request` 指向完整 JSON，仅含三个顶层字段：

- `candidate`：六格候选 ArtifactEnvelope 完整记录；
- `intent`：独立 service launch intent 完整记录；
- `approval`：针对该intent、scope为service_start的真实人类批准receipt完整记录。

构造receipt只是记录批准，不等于得到批准。当前没有可直接上云的真实request样本；
不能复制专项测试的合成receipt作为实际批准。

`--bundle` 指向已经批准大小/SHA-256的实际Git bundle；上限256MiB为读取安全边界，
不是研究参数。当前只接40位SHA-1 Git提交，bundle v2/v3；不伪装支持SHA-256仓库。
`--prerequisite-repo` 为可信本地Git仓库（也可以是linked worktree）。增量bundle需要
它实际具有所有prerequisite objects；新服务器缺base时会拒绝，而不是访问网络补拉。

PowerShell（从项目目录执行，路径变量须指向真实已批准文件）：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'platform/src'
python -m agent_ex.identity_network.source_cli verify --request $requestPath --bundle $bundlePath --prerequisite-repo $baseRepoPath
```

Linux（设置三个变量为真实已批准文件/仓库后）：

```bash
PYTHONPATH=platform/src python -m agent_ex.identity_network.source_cli verify \
  --request "$request_path" --bundle "$bundle_path" --prerequisite-repo "$base_repo_path"
```

返回0才表示该内容核验通过；拒绝返回2并输出错误类别，不把源码、配置文本或Git内部
stderr带入对话。JSON输出本身仍不是真实服务/模型、运行checkout身份或dispatch授权。

## 比单独 Git bundle verify 多验证什么

先检查完整candidate/intent/receipt与bundle字节大小/hash，再检查Git头部/prerequisites
与exact advertised source commit。将pack导入**新建临时bare repo**；只从base仓库
导出明确声明的prerequisite commits之reachable graph，不用整个仓库作alternates。
核对目标commit实际存在于本次导入pack的index，然后严格校验reachable graph/tree；
原仓库不写objects/refs。头部正确但pack换成无关合法pack、或省略未声明tree/blob都会拒绝。
临时目录仅包含本次pinned bundle与核验objects，结束清理，不删除用户文件或研究证据。

受信任目录、Git程序与base仓库是边界：不是恶意并发目录沙箱，不修复损坏/缺失base，
不自动fetch。bundle verify可接受头部但不能独立证明pack字节完整，必须保留后半段检查。

真实启动仍须：实际运行checkout clean commit核对、现场service ownership/vacancy/环境
观察、start身份桥、独立最终dispatch receipt与受控运行器。该命令不替代这些步骤。
