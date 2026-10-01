# Linux现场服务观察：只读入口

模块：`agent_ex.identity_network.service_live`。当前只有合成procfs/Windows拒绝专项
证据，**尚未在AutoDL现场验证**；命令现在不需要你开服务器。上云边界到达后再现场复验。

## 主机与服务

在已准备依赖的Linux项目目录中，先观察host/container identity：

```bash
PYTHONPATH=platform/src python -m agent_ex.identity_network.service_live host
```

输出的 `payload.host_identity_hash` 由Linux boot UUID与container hostname派生，
不会直接打印hostname。该hash应由同一次现场vacancy/服务启动流程绑定，重启主机
或迁移container后不能复用原hash。

已有**真实服务启动身份文件**时，可只读检查它是否仍对应当前进程：

```bash
PYTHONPATH=platform/src python -m agent_ex.identity_network.service_live service \
  --start "$service_start_path" --host-identity-hash "$observed_host_identity_hash"
```

变量必须来自真实现场记录，不能使用测试fixture、猜PID或自行填host hash。
`--start`严格读取已有start JSON，不修改/生成service start记录，不查找“差不多”的PID。

成功返回0和元数据JSON。拒绝返回2及错误类别，无完整cmdline、环境变量、响应、
公开理由或socket内容。Windows明确拒绝，不用合成观察伪装Linux现场证据。

## 检查范围

- exact start record/hash，记录PID、Linux field22启动tick、raw NUL cmdline SHA和exe；
- PID不是zombie/exited状态，cmdline非空，exe未deleted，启动时间不在未来；
- 服务与观察客户端的network namespace相同且观察期间不变；
- 当前端口8000仅IPv4 `127.0.0.1` LISTEN，所有listener inode由记录PID的FD持有；
- 两次process/listener/FD观察一致，boot/container identity未变化。

读取stat时按comm最后的括号边界处理，避免进程名含空格/右括号时错读启动tick。
命令身份沿用service script对`/proc/PID/cmdline`原始bytes的SHA-256算法。

## 不证明什么

这只是一个瞬时观察，不是进程lease。真正runner在发送前必须重新观察，不能把
旧文件的hash验证当成现在的进程证明。当前不查询health、不读取model revision/wheel
或GPU占用，也不验证whole source checkout/environment/service bridge/审批。
因此服务alive不等于model ready，更不等于正式/诊断发送权限。

它不stop/restart/kill、不绑定端口、不发HTTP或模型请求，不接触raw response。
缺PID、权限不足、PID/namespace/监听变化均失败关闭，不能自动补起服务或切换实例。
