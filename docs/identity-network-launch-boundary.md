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

1. 校验真实环境inspection、原服务收口/冷关机/迁移证据、新服务start-first记录和
   服务配置，将真实服务身份绑定到新SIS意向。不得把旧Phase0B 12格/N20授权套给SIS。
2. 为真实身份操纵检验生成具体来源/规模/criteria和独立执行授权；pure-label first，
   只接受已绑定stage-one report/criteria的人类no_signal决定进入预定义stage-two。
3. 最终诊断授权绑定实际candidate、服务证据、源码、scope和独立人工receipt。
   真实启动CLI在一切验证后才能构造HTTP adapter；只读verify/report无需model请求。
4. Linux专项及独立命令运行、必要的安全恢复/失败收口验证；准备最终source bundle。

以上均未由当前纯合同测试证明。当前无自动start/run命令，也没有现成获批的真实
bundle/receipt，尚不需要开启服务器；本地补齐后再列出云端启动所需批准项。
