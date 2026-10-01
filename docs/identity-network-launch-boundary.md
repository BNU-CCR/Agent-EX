# SIS真实启动边界（本地合同阶段）

本文件是实现交接，不冻结新的研究参数，也不代表已运行云端实验。

## 已实现

`launch.build_service_launch_intent` 将完整pre-service固定来源投影、源码commit、bundle
大小/SHA-256、服务五字段配置及专属`/root/autodl-tmp`归档子目录绑定为自包含意向。
意向不依赖尚未出现的service-start hash，也不授予dispatch或formal权限。
服务启动后，只有start identity可经`bind_candidate_service`机械换入；固定来源不得变化。

`StudyApprovalReceipt` 使用新SIS schema，记录精确target hash、研究者、UTC时间和
作用域。service_start与diagnostic_dispatch不互相替代。记录仅为人类批准的归档归属，
不是密码学签名；执行方必须先取得真实用户批准，不能自行调用create伪造批准。

`validate_service_start_approval` 冷核验来源意向与receipt，只接受当前意向的
service_start批准，核对调用者报告的实际commit、实际bundle字节大小和SHA。
它不解析Git bundle来证明其中包含commit；后续文件/执行入口必须做Git独立核验。

## 必须继续完成的接线

当前service_bridge已接纯合同验证：启动前vacancy绑定intent/inspection/host，要求
8000端口无监听及GPU compute进程空观察；新start-first记录须绑定本次intent和inspection，
与固定服务配置、PID/proc tick及时间顺序一致。环境锁仅作为固定模型/依赖profile，
不把旧scope授权给SIS；当前环境记录绑定本次intent，新代码必须clean且commit相同。
模型/分词器/制品、chat template、package/image/vLLM、non-thinking render和serve参数
与固定profile一致，并要求明确loopback/8000/served name/BF16，拒绝equals-form覆盖。
输出桥仍dispatch_authorized=false。

这些输入必须来自真实host collector；当前纯合同不证明进程仍活着、观察来源诚实或
旧797归档已经迁移完成。后续启动入口须读取实际PID/start tick/cmdline/host并做Git及
bundle核验，不能用合成test fixture替代现场证据。端口/GPU忙时拒绝，不自动kill。

1. 将上述纯合同接到真实观察与运行入口；原服务收口/冷关机/迁移保留原有独立证据。
   不得把旧Phase0B 12格/N20授权套给SIS，也不把新host空闲观察当作旧数据归档证明。
2. 为真实身份操纵检验生成具体来源/规模/criteria和独立执行授权；pure-label first，
   只接受已绑定stage-one report/criteria的人类no_signal决定进入预定义stage-two。
3. 最终诊断授权绑定实际candidate、服务证据、源码、scope和独立人工receipt。
   真实启动CLI在一切验证后才能构造HTTP adapter；只读verify/report无需model请求。
4. Linux专项及独立命令运行、必要的安全恢复/失败收口验证；准备最终source bundle。

以上均未由当前纯合同测试证明。当前无自动start/run命令，也没有现成获批的真实
bundle/receipt，尚不需要开启服务器；本地补齐后再列出云端启动所需批准项。
# Stage-one manipulation dispatch target（2026-10-01）

`manipulation_authorization` 已接纯合同：显式研究者sample/analysis/success/no-signal文本
与样本inventory、seeds/order绑定为preregistration；来源包按独立candidate重建，service
bridge按全evidence重放；最终target包含pack/criteria/bridge/adapter/start hashes及endpoint/
archive/generation settings。`validate_manipulation_dispatch_approval` 只接受精确target的
diagnostic_dispatch人类receipt，并要求其不早于criteria/service观察、不晚于检查时间。

文本规则不是自动可执行判定器，create receipt不是取得人类批准，现场服务truth、fresh
archive与Git bundle内容验证仍需真实入口。Stage-two素材receipt不能绕过stage1结果门。
当前v1对应原四配对素材；用户新240请求候选见
`identity-network-manipulation-240-candidate.md`，尚未用v1冒充重复层或case级推断实现。
