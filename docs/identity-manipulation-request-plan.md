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

专用 SQLite 存储已接入；下一步是独立运行循环与 CLI。真实240来源、重复seed和
统计规则仍待确认，不把当前四配对合同测试当作已完成真实操纵检验。

## 独立存储的单写者边界

`ManipulationRunLock.acquire(existing_root)` 为专用存储提供 Linux-only 非阻塞锁。
运行根目录必须已存在；锁文件持久保留，不删除、不截断。整个运行会话（包括 HTTP）
必须保有同一 lease，写前调用 `assert_held(root)`，拒绝未取得锁、关闭、进程变化、
错误根目录及锁文件替换。`close` 只关闭 fd，不主动 LOCK_UN，避免 fork 子进程
关闭继承描述符时提前解锁父进程。

这是协作进程的单写者边界，不阻止忽略 lease 的其他 SQLite writer，也不防御恶意
父目录、内核或进程内存变化。它不提供发送权限，已接入 SQLite，尚未接入运行 CLI。
Windows 专项明确使用模拟 syscall；真正的 Linux 竞争、进程死亡后重新获取以及
symlink/FIFO 拒绝测试须在 Linux 验证，不能由本机绿色测试代替。

## 专用 SQLite 证据存储

`ManipulationStore.create/open/verify` 使用独立的 `manipulation.sqlite3`，不复用六条件
study state 或797盲判记录。创建要求已有可信根目录和持有的具体 writer lease；已有
数据库不覆盖。只读 verify 不创建数据库，完整重放来源、计划、试次清单和证据链。

每条试次遵循 `READY → INTENT → RESPONSE_STORED → VALID/INVALID`：
`record_before_dispatch` 先提交精确请求/wire的发送意向，`store_response` 先保存 typed
响应，再由 `terminalize_saved_response` 本地解析。未决 INTENT 不得重发；INVALID
停止后续试次，不代表操纵无信号。该组件本身不调用 HTTP，不推进共享意见状态。

冷读取核验完整前缀；正常追加复用已核验请求和增量前缀，检测外部数据库变化时重新
核验。summary 只提供计数、阶段、哈希和 preliminary/not_frozen/false-authority 标记，
不输出消息、原始响应或 reason。JSON 文件的字段排序不改变精确 encoder wire。

完整 transport loop、假 HTTP 崩溃恢复专项、加载源码来源检查、授权根目录与服务
预检组合及独立 run/resume/verify/report 仍未完成。现在无需开启云服务器。
