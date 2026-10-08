# Benchmark retry contract v2：本地实施

研究依据：D-2026-10-08-01，240项全部VALID才判定；每项最多3次attempt。
旧manipulation-store.v1及quartet-v1不改、不迁移、不冒充240项运行包。

本阶段建立纯、可冷重放的版本化状态合同；不是SQLite验收或dispatch授权。
逻辑request identity绑定精确wire hash；attempt identity另绑定attempt_index。
每次INTENT必须先持久化；同项重试不能变更wire、seed、prompt或generation。
已保存的技术失败经分类后才可RETRY_READY；第3次失败为INCOMPLETE。
timeout、连接丢失、未知服务错误和无response的INTENT保持歧义，禁止重发。
成功响应解析失败允许技术重试；HTTP 429明确拒绝允许重试。
HTTP 5xx不默认证明没有执行；不擅自增加歧义人工裁定规则。

步骤：
1. TDD验证正常完成、三attempt、歧义阻断、wire漂移、journal篡改及越序。
2. 实现纯record构造和完整prefix replay；hash链是完整性不是来源真实性。
3. 验证专项与legacy回归；记录runtime/prompt权限边界。
4. 后续durable store/loop只能消费经过response来源核验的分类；不能由调用者
   任填VALID来构成实证证据。真实request materialization仍要求明确runtime绑定。

禁止读取raw response、调用模型或启动服务器。保持preliminary/no formal authority。
