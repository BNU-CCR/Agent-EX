# 独立 Stage-A 预检命令

此命令尚不运行操纵检验；它只冷读取完整证据，再执行只读source/runtime/live预检。
不需要现在开启服务器，未来Linux环境与精确批准制品就绪后使用：

```bash
cd /absolute/path/approved-agent-ex-checkout
PYTHONPATH=platform/src /absolute/path/approved-python -m agent_ex.identity_network.preflight_cli \
  --request /absolute/path/manipulation-preflight-request.json \
  --bundle /absolute/path/approved-source.bundle \
  --runtime-repo /absolute/path/approved-agent-ex-checkout
```

stdout仅观察JSON；成功0、拒绝2，stderr仅异常类别，无payload/HTTP body/模型响应。
JSON必须是bounded regular文件，拒绝重复键/非有限值和symlink/reparse路径。继承
candidate reader现有32MiB上限，不是对恶意并发目录替换的隔离沙箱。

## 请求制品

生产函数`build_preflight_request(auth, receipt, evidence)`不创造人类批准或新观察。
schema为`paper1.identity-network.manipulation-preflight-request.v1`，精确字段：

- schema_version、authorization、receipt、evidence。
- evidence：candidate、source_pack、preregistration、bridge、service_evidence。
- service_evidence：intent、approval、environment_lock、current_environment、inspection、
  vacancy、new_start、current_host_identity_hash、observed_at。

candidate只保存一份，解析时用同一typed candidate接入service evidence。旧环境锁
保持原authorization含义；current_environment为本次intent绑定的EnvironmentLock，
其packages/artifacts使用既有canonical排序，再还原验证过的EnvironmentObservation。
冷重建不要求原观察的非规范数组顺序一致，但完整canonical环境锁必须完全相同。
额外字段/错误schema/改hash后仍不符的current intent授权均拒绝。

parser不等于完整派生核验；CLI随后执行preflight全重放，不能只调用parser宣称获批。
请求文件可能含人口persona、初态和source理由，是受控输入，不应粘贴到对话输出。
不得用测试fixture或程序自行create的receipt冒充实际研究输入/人类批准。

## 目前边界

本地正例使用real tiny Git、完整typed来源与mock procfs/health；真正独立Python进程
已验证错误receipt在任何现场HTTP之前拒绝。不是Linux现场服务验收或实验结果。
现有v1仍是一case四trial体系，不能替代待确认240请求重复和统计版本。

尚缺：独立run/dispatch/resume入口、执行代码origin核对、fresh archive与durable intent
接线、实际benchmark/240设计细节、真实当前环境采集及服务交接。详见
`identity-network-manipulation-preflight.md`。预检输出始终dispatch_authorized=false。
