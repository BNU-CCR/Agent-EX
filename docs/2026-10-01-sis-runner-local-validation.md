# SIS 六条件运行与本地核验边界（2026-10-01）

工作分支：`codex/social-identity-network-2x3`。旧实验与共享存储语义保留。

## 已接入的接口

`agent_ex.identity_network.runner.run_study_cells_prefix` 接受六格canonical顺序的
storage/journal tuple、显式stop ordinal、adapter factory和clock。调用者必须已经
持有全部lease。这是有界执行原语，不是经过人工批准的云端启动入口。

运行前统一核验六格共同输入、封存初态、独立文件及已有失败；每事件依次保存
PENDING、发送意向、响应、终态与derived状态。已完成前缀不再请求，已保存响应
可本地收口；未决发送停止而非重发。失败停止全族，不隐式重试或改动研究参数。

## 无模型、无云端的只读命令

在安装平台依赖的环境中，设置 `PYTHONPATH=platform/src` 后执行：

```text
python -m agent_ex.identity_network.runner report --index /path/to/archive/index.json
python -m agent_ex.identity_network.runner verify --index /path/to/archive/index.json
```

`report`可输出部分进度；`verify`要求六格完整且没有未决dispatch。成功返回0，
证据不完整/冲突返回2，不输出输入内容或响应文本。不要把这两个命令当作run命令。

索引需在归档根目录内，schema为`paper1.identity-network.archive-index.v1`，
顶层仅`schema_version`与`cells`。cells为六项，顺序如下：

```text
SIS-A0-B0, SIS-A0-B1, SIS-A0-B2, SIS-A1-B0, SIS-A1-B1, SIS-A1-B2
```

每项仅包含`manifest`（完整原始RunManifest.to_payload()，不是摘要或hash）、
`database`及`dispatch_journal`。两个路径都相对于索引所在目录，不得越界、
使用绝对路径或经符号链接。六个数据库必须已存在且独立；日志也须独立。
无尝试的部分归档可没有journal文件。入口不创建缺失数据库或发送请求。

报告包含完成计数、状态、意向/响应收口计数、证据hash及私人立场分布，不含
reason或raw response。仍标记`preliminary / not_frozen`、
`formal_parameter_authority=false`、`transport_provenance=unattested`。
结构完整不证明真实模型来源，也不意味着正式研究参数已冻结。

## 尚未完成与上云顺序

候选人口/注意/发布输入的来源物化、独立真实启动receipt与服务所有权交接、
可移植真实run CLI/运行卡、失败重试授权以及真实identity manipulation check
仍待接入。先完成这些入口，准备候选制品及审批，再请用户开启云服务器。
先检验纯Blue/Green操纵，再按批准规则决定六条件真实小pilot；不以合成测试
数据代替模型结果，不填未决正式N/T/seeds/primary outcome。
