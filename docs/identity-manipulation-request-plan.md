# 身份操纵检验：来源绑定请求清单

本组件是已批准独立运行器的输入层，不是可运行的完整实验程序。

`build_manipulation_request_plan` 从完整候选、试次来源、规则、服务交接与 scoped receipt
重放构造有序请求；保留原始消息、显式 seed、模型、生成设置和 wire SHA-256。
temperature/top_p 转为 float 仅满足 transport 类型约束，不改变研究数值。

`validate_manipulation_request_plan` 冷重放全部来源并要求完整制品一致，拒绝即使
重新计算哈希的消息、seed、顺序、模型、timeout 或权限替换；返回不可变请求 tuple。
后续循环应复用该已核验 tuple，不在每个请求前重新扫描整个来源包。

本层不访问网络、不写状态、不发送请求。所有制品仍为 preliminary/not_frozen，
formal_parameter_authority=false、dispatch_authorized=false。
当前 `quartet-v1-local-contract-only` 明确 cloud_launch_eligible=false，不能代替真实
30 case × 4 cell × 2 repeat 的240请求版本。

下一步为专用 SQLite 存储和独立运行循环：intent 必须在 HTTP 前持久化，
已有响应仅本地恢复；未决发送不得重发。真实240来源、重复seed和统计规则仍待确认。

## 独立存储的单写者边界

`ManipulationRunLock.acquire(existing_root)` 为专用存储提供 Linux-only 非阻塞锁。
运行根目录必须已存在；锁文件持久保留，不删除、不截断。整个运行会话（包括 HTTP）
必须保有同一 lease，写前调用 `assert_held(root)`，拒绝未取得锁、关闭、进程变化、
错误根目录及锁文件替换。`close` 只关闭 fd，不主动 LOCK_UN，避免 fork 子进程
关闭继承描述符时提前解锁父进程。

这是协作进程的单写者边界，不阻止忽略 lease 的其他 SQLite writer，也不防御恶意
父目录、内核或进程内存变化。它不提供发送权限，且尚未接入 SQLite 或运行 CLI。
Windows 专项明确使用模拟 syscall；真正的 Linux 竞争、进程死亡后重新获取以及
symlink/FIFO 拒绝测试须在 Linux 验证，不能由本机绿色测试代替。
