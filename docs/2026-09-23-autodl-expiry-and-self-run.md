# AutoDL 到期、迁移与自主运行清单（2026-09-23）

> 本文是操作交接，不是 Phase 0B 的运行授权。当前真实 N=20/T=2、12-cell、480-event 诊断运行器尚未完成；不要把旧的单 Agent 占位入口当作正式网络实验运行。所有 Phase 0B 输出仍应标为 `preliminary / diagnostic / not_frozen`，不得声称正式主实验已完成。

## 一、先判断是否真的要明天换机器

AutoDL 官方说明：普通容器实例的包年包月到期**本身不清空数据**；实例连续关机 15 天后释放，释放时所有数据不可恢复。主机下架、主动释放或磁盘故障是另外的风险。到期后付费数据盘仍可能继续计费。不要只因包周到期就点击“释放实例”；先看控制台显示的到期、释放倒计时和续费/转按量选项。

- 数据规则：[AutoDL 实例数据](https://www.autodl.com/docs/instance_data/)、[本地数据盘](https://www.autodl.com/docs/local_disk/)
- 同地区迁移：[AutoDL 迁移实例（同地区）](https://www.autodl.com/docs/migrate_instance_2/)
- 共享文件存储：[AutoDL 文件存储](https://www.autodl.com/docs/fs/)

本项目 2026-09-23 只读检查：旧实例 `root@connect.bjb2.seetacloud.com:35947` 仍可连接，`/root/autodl-tmp/agent-ex-phase0a1-judge-v2/run-store` 存在；该 judge 根目录约 2.1 GB，数据盘约 150 GB、已用 61 GB、可用 90 GB；端口 8000 仍有监听。`/root/autodl-fs` 当前未挂载，不能假定已有共享备份。检查没有读取原始回答。797 条 judge 已完成，但服务尚未做正式停止/交接证据；**不要直接删除旧实例或手动杀掉服务**。

## 二、旧实例保全顺序

1. 在 AutoDL 控制台确认“实例到期”与“实例释放”是不是两个不同日期，截图保存实例 ID、地区、GPU、镜像、数据盘大小、SSH 入口和到期提示。不要在未验证备份前点击释放。
2. 保留旧实例的 `/root/autodl-tmp/agent-ex-phase0a1-judge-v2/`，其中包含 judge 的持久化证据。还要盘点 Phase 0A 校准的原始归档、模型文件、环境锁、服务证据和运行日志。不要只保留 Git 仓库：原始结果本来就不入 Git。
3. 优先选择同地区“克隆实例”并**勾选数据盘**；AutoDL 说明这样可同时迁移系统盘和数据盘。若只克隆系统盘，`/root/autodl-tmp` 不会因此自动出现在新实例。克隆前按服务生命周期脚本完成旧服务的受控停止和证据核验，不用 `kill -9`、`pkill` 或手动删除端口占用。
4. 如果换到不同地区，不能假定 `/root/autodl-fs` 自动跨地区共享。先按官方跨地区迁移文档安排传输，或将必要数据备份到受控外部存储；核对大小、文件数量和 SHA-256 后再释放源实例。
5. 新实例中确认代码、模型、环境和完整证据目录均能打开且哈希一致，**然后**才处理旧实例。文件存储适合持久备份，同地区实例可共享，但不应直接承载高 I/O 的正式事件数据库。

## 三、你自己连接与看状态

在 Windows PowerShell 中，先从新实例的 AutoDL 控制台复制**实际** SSH 主机与端口。旧实例的示例：

```powershell
ssh -o IdentitiesOnly=yes -i 'C:\Users\Bai Yuexi\.ssh\agent_ex_autodl_20260910' -p 35947 root@connect.bjb2.seetacloud.com
```

私钥只留在你自己的电脑，不上传、不粘贴到聊天或 Git。新主机第一次连接出现主机指纹时，应与 AutoDL 控制台/可信记录核对，不要用 `StrictHostKeyChecking=no` 跳过检查。如果新实例没有导入同一公钥，先在 AutoDL 控制台设置 SSH 免密登录。

登入后，这些是**只读**状态命令，不会启动实验：

```bash
date -u
nvidia-smi
df -h /root/autodl-tmp
ss -ltnp 'sport = :8000'
ls -ld /root/autodl-tmp/agent-ex-phase0a1-judge-v2/run-store
```

`nvidia-smi` 可看 GPU 是否可见和显存占用；`df` 看磁盘余量；`ss` 看 8000 端口是否已有模型服务。不要因为端口已被占用就再启动第二个 vLLM。

## 四、断线或额度耗尽时，程序怎样继续运行

Codex 额度和云端进程是两回事：已经在云端后台正确启动的进程，不会因为对话额度耗尽而自动停止；但实例关机、到期自动停机、进程崩溃或磁盘满仍会中断。用户自己运行时建议用 `tmux` 保留会话：

```bash
command -v tmux
tmux new -s agentex-run
# 在 tmux 内执行已批准、带完整哈希的正式启动命令；当前尚未提供这条命令。
# 按 Ctrl-b，再按 d：退出观看但不结束会话。
tmux ls
tmux attach -t agentex-run
```

只有确认日志**不含原始 prompt/回答**时，才可用 `tail -n 30 <安全日志路径>` 查看进度；不要在聊天里粘贴 raw response。不要看到 SSH 断线就重新运行：先检查 PID、终态投影、dispatch intent、attempt 和 checkpoint；未决 dispatch 存在时绝不能盲目重发。

## 五、当前真正可运行的边界

云端 Phase 0A-1 已完成 816 条真实校准与 797/797 条盲判，相关结果是**校准/盲判证据**，不是 N=20 网络动力学结果。Phase 0B 的本地代码当前已有 N=20/T=2 材料生成、真实请求/响应证据前缀、成功终态与单事件状态重放；但失败终态、完整 checkpoint/resume、12-cell 真实事件接线、Linux 验证及安全报告尚未全部完成。

当前 `codex/paper1-phase0` 本地分支比其已知远端跟踪分支**领先 117 个提交**（以 2026-09-23 的本地跟踪信息为准）；新服务器上简单 `git clone` 或 `git pull` **不能保证得到最新代码**。在正式迁移前，应由维护者审核并推送该分支，或生成、验证并传输精确 Git bundle；不得把未审代码、私钥、模型权重或原始响应提交到 Git。

## 六、Phase 0B 之后交给你的五段式运行卡

只有下面全部准备完毕，才会提供可复制的实际命令及具体哈希、路径；现在不猜命令：

1. **核验**：代码提交/bundle、12-cell 材料、授权哈希、环境锁、模型 revision、磁盘及端口。
2. **服务交接**：797 judge 的终态和服务停止证据完整后，为 Phase 0B 建立新的服务身份。
3. **两事件预检**：独立归档，验证一次请求、解析、持久化、断线恢复和错误处理；不并入 480-event 正式诊断归档。
4. **480 事件运行**：新建空归档，严格串行，每个事件写入不可变证据；只启动一次。用 tmux/后台进程让它在 Codex 额度耗尽后继续。
5. **只读核验与导出**：确认 12 个完整数据库、480 个成功事件、0 未决 dispatch，生成脱敏 preliminary 报告和归档哈希；原始结果留在受控存储，不入 Git。

若任何核验失败，停在相应阶段保存证据，不跳过失败或自行拼接旧、新服务器的运行结果。
