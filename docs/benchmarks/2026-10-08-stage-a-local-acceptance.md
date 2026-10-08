# Stage-A 本地验收与上云操作交接

## 边界与当前状态

这是30个退休议题benchmark的身份操纵检验，不是正式2×3网络实验结果。
本轮只做本地合成HTTP/SQLite/统计测试，没有SSH、上传、启动服务或调用真实模型。
代码路径为`platform/src/agent_ex/identity_network/benchmark_*.py`，旧v1原样保留。
最终测试计数见progress.md的本轮验收记录；本文件的命令不代表运行已获批准。

具备离线物化与受控运行能力；**尚不能直接启动240项**。仍需实际runtime绑定、
Linux内核锁验收、独立两事件技术preflight及单独人类运行授权。
Stage-B精确文本已冻结，但所有当前入口拒绝Stage-B。

## 冻结与请求示例

- benchmark canonical hash：`9c2345580024523794a2d433500229d55e166414f18f5c0bd06baba893c8eb10`。
- renderer/runtime policy canonical hash：`5dc0b73a81f4e3bbff4a2e22810fcc4f00ba3e7ab92fb2fc3872ac283ca439c8`。
- 精确system canonical hash：`c034a6e4765a40d0f0fc94e82e69c84b14454115bfbb0c8562d2a4b57fdede15`。
- 五参数：0.7 / 0.8 / 20 / 0 / 512（temperature/top_p/top_k/min_p/max_tokens）。
- thinking在wire显式false；自历史空，pre-confidence缺失，不算confidence change。

完整renderer产物：`docs/benchmarks/2026-10-08-stage-a-request-examples.json`。
首个同组请求self=Blue/source=Blue；异组self=Blue/source=Green。两者展示同一句：
“我比较支持逐步提高法定退休年龄。我觉得慢慢调整，至少可以给受影响的人留些适应的时间。”
persona、focal中立4、事实卡、成员别名与seed=1663292628全部相同；不重复source_reason。
示例是实际编码的wire，但runtime尚未绑定，也未发出。真实runtime更换后重新物化并审阅packet。

runtime记录精确model revision、model files/tokenizer/chat template hashes、vLLM版本、
BF16、thinking=false、served model name和loopback endpoint。快照工具流式读取本地文件，
不加载模型；[官方8B config](https://huggingface.co/Qwen/Qwen3-8B/raw/main/config.json)中的
架构尺寸用于排除其他Qwen3尺寸。架构匹配不证明权重真实性或当前服务已加载该快照；
后者仍须核对下载revision/来源及真实服务进程与启动命令。SHA绑定实际字节，不冒称官方签名。

## 获批后服务器操作顺序（现在不要执行）

使用独立、干净的Git checkout；以下假定源码根为`/root/autodl-tmp/agent-ex-sis-mc`。
先确认服务器/GPU与8000端口所有权；旧服务若属于其他任务，不擅自停止或复用身份。
不要在开机后重新跑全仓pytest。先核验环境与下列最小Linux测试。

```bash
cd /root/autodl-tmp/agent-ex-sis-mc
export PYTHONPATH="$PWD/platform/src"
python -m pytest platform/tests/test_identity_network_manipulation_lock.py -q -k linux

# MODEL_PATH是已经核验下载来源的本地Qwen3-8B快照；REV是对应完整40位revision。
# 此处不填旧revision；SERVED须与runtime记录相同。
python -m agent_ex.identity_network.benchmark_cli runtime-snapshot \
  --model-dir "$MODEL_PATH" --revision "$REV" --served-model-name "$SERVED" \
  --out runtime.json

# 单独获准启动服务后执行；日志归档保存，不在聊天输出模型内容。
nohup vllm serve "$MODEL_PATH" --host 127.0.0.1 --port 8000 \
  --revision "$REV" --tokenizer-revision "$REV" --dtype bfloat16 \
  --generation-config vllm --served-model-name "$SERVED" \
  --default-chat-template-kwargs '{"enable_thinking":false}' \
  --enable-request-id-headers > service.log 2>&1 &
```

上述vLLM选项需在实际已安装版本核对；不静默替换模板或掉回thinking模式。
保存PID、启动命令、软件版本、服务身份与快照，核对服务使用同一目录/模板/served name。
使用独立MC归档，不将权重/原始响应提交Git。

```bash
BENCHMARK=platform/configs/identity-network/manipulation-retirement-20261008/benchmark.json
python -m agent_ex.identity_network.benchmark_cli materialize \
  --benchmark "$BENCHMARK" --runtime runtime.json --mode preflight --out preflight-packet.json
python -m agent_ex.identity_network.benchmark_cli materialize \
  --benchmark "$BENCHMARK" --runtime runtime.json --mode stage-a --out stage-a-packet.json
python -m agent_ex.identity_network.benchmark_cli inspect \
  --benchmark "$BENCHMARK" --runtime runtime.json --packet stage-a-packet.json
git rev-parse HEAD
```

输出两packet hash、runtime hash和source commit供用户另行批准。授权receipt须逐模式绑定：

```json
{
  "schema_version": "sis.stage-a.run-approval.v1",
  "packet_hash": "填写当前该模式的完整packet hash",
  "runtime_hash": "填写当前runtime canonical hash",
  "source_commit": "填写当前干净checkout的40位HEAD",
  "approved_by": "实际批准人",
  "decision": "approve",
  "expires_at": "填写明确且未到期的带时区ISO时间",
  "mode": "preflight"
}
```

这是字段示意，**不可运行的模板，不是已经批准的receipt**。Stage-A使用另一份receipt、mode=stage-a。
不自动写入用户批准；expiry续期保持原packet/runtime/source/mode，追加授权账本，不改初始证据。

```bash
mkdir preflight-store stage-a-store
python -m agent_ex.identity_network.benchmark_cli run \
  --benchmark "$BENCHMARK" --runtime runtime.json --packet preflight-packet.json \
  --root preflight-store --receipt preflight-receipt.json
python -m agent_ex.identity_network.benchmark_cli verify \
  --benchmark "$BENCHMARK" --runtime runtime.json --packet preflight-packet.json --root preflight-store

# 仅两项技术通过并另行批准240后；后台进程独立于Codex额度/连接。
nohup python -m agent_ex.identity_network.benchmark_cli run \
  --benchmark "$BENCHMARK" --runtime runtime.json --packet stage-a-packet.json \
  --root stage-a-store --receipt stage-a-receipt.json --preflight-root preflight-store \
  > stage-a-run.log 2>&1 &
```

只读检查用verify；退出不意味着可以重发。已保存响应可恢复解析；未决INTENT或timeout/5xx
歧义停下核对，不自动resume、不删除DB、不重新run。只有可恢复前缀使用原绑定和新有效receipt：

```bash
python -m agent_ex.identity_network.benchmark_cli resume \
  --benchmark "$BENCHMARK" --runtime runtime.json --packet stage-a-packet.json \
  --root stage-a-store --receipt stage-a-receipt.json --preflight-root preflight-store
python -m agent_ex.identity_network.benchmark_cli report \
  --benchmark "$BENCHMARK" --runtime runtime.json --packet stage-a-packet.json \
  --root stage-a-store --out stage-a-report.json
```

新输出文件不覆盖；DB保存原始证据，CLI/报告不打印原始response/public_reason。
两事件只做技术验收，不纳入240，不依其意见调整prompt。只有240全VALID才能实质判定；
不删case/改分母。仍以30case等权、六strata bootstrap10,000次95%CI和18/30方向判据为准。
完整有效但无信号也不能直接运行Stage-B；要保持预冻结framing并另行批准。
