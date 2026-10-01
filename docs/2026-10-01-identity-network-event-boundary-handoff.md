# 新 2×3 单事件接口交接（2026-10-01）

## 本阶段完成

工作分支为 codex/social-identity-network-2x3；旧实验归档与 main 不变。
新增 identity_network/execution.py 的 prepare_study_event 与
finalize_study_response，不引入第二套解析器或云端调度器。

renderer v2 使用 typed TopicPackage、文字 stance labels、整数 1–5 confidence。
准备接口绑定原状态、TopicPackage、实际模型可见内容、事件/尝试身份、外生
publish_flag 和显式模型 seed/settings。完成接口复核响应与 transport 实际发送内容，
严格解析后构造候选 PrivateUpdate/PrivateState/PublicPost。
失败不改变原状态；重试保留事件身份。trace 是 prospective，committed=false。

独立审查发现的重新哈希 prompt 投影篡改及 wire body 篡改已修复并闭环复核。
最终专项：六个 identity_network 测试文件及旧 adapter/parser/state/topic，
106 passed in 1.42s；Ruff check 通过。所有 HTTP 响应为测试替身，
并非真实模型结果；未启动 AutoDL、未运行全仓 pytest。

## 下一阶段：持久化与完整六条件运行

1. 为 SIS cell 和输入证据新增明确的存储 discriminator / reader union；
   不绕过旧 RunStorage 对 legacy P1 cell 的验证。
2. 串行原子提交 state/public output/feed cursor，失败不推进；重开、重试、
   resume/checkpoint 必须复用事件身份并验证 exact cover。
3. 六条件 materializer 绑定同一人口、初始状态、组别、记忆和 matched seed 网络；
   验证跨事件中性别名、帖子来源及只读真实公共表达。
4. 绑定实际获准模型 revision / 服务身份，再准备 manipulation check 的明确
   样本、判据、运行配置。保持 SIS 未决参数，不使用程序默认值填补。
5. 本地闭环后再请求开云服务器，先做真实 identity manipulation check，
   再进入小规模六条件 pilot。正式 N/T/seeds/primary outcome 尚未冻结。

不能把候选公开输出当作实际发表；当前接口不写 SQLite、不修改游标，
不证明真实服务模型身份或源帖因果来源。旧 797 盲判证据不应重跑或合并到新研究。
