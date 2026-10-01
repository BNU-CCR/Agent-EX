# SIS 健康观察入口（非运行授权）

Linux 服务启动记录与先前 vacancy 的 host hash 已核实后，可执行：

```bash
PYTHONPATH=platform/src python -m agent_ex.identity_network.service_health \
  --start /absolute/path/service-start.json \
  --host-identity-hash <previously-verified-vacancy-host-sha256>
```

当前不需要为此打开云服务器。此入口将真实 procfs 身份观察放在固定
`http://127.0.0.1:8000/health` 请求前后；检查同一 recorded PID/start tick/
cmdline/executable、host、netns 和监听 FD 归属。禁用代理与重定向，仅接受
HTTP200；响应最多8192字节，只保存hash/大小，不输出body，不调用completion。
HTTP socket timeout为5秒，不声明整个过程有5秒硬截止。

stdout为安全观察JSON；拒绝返回2。Windows拒绝，不接收替代procfs路径。
已通过的是合成procfs和mock HTTP专项，不是AutoDL现场验收。

观察不是原子lease，不能阻止检查后服务改变，也不是model/revision证明或
dispatch授权；真正发送入口仍须接入source bundle、当前runtime checkout、
environment、完整bridge、精确scope人类receipt、durable dispatch以及发送前复查。
不得用健康响应替代这些边界，也不得将此命令用于重启/停止既有服务。
