# 新2×3候选归档的本地命令入口

本入口只初始化/检查初态，不跑模型、不启动服务、不授予实验权限。
所有候选仍为 `preliminary / not_frozen / formal_parameter_authority=false`。
它不是云端正式run命令，也不是旧797条judge的恢复入口。

## 输入

`request.json` 必须是完整JSON对象，字段恰好为：

```json
{
  "schema_version": "paper1.identity-network.prepare-request.v1",
  "candidate": "完整six-cell ArtifactEnvelope对象，不是hash或路径",
  "context": {
    "git_sha": "实际源码40位commit SHA",
    "dirty": false,
    "diff_hash": null,
    "environment": {
      "python_version": "与schedule来源一致的显式版本",
      "dependency_lock_hash": "与候选adapter一致的64位hash",
      "platform": "显式平台描述"
    },
    "launch_nonces": "六个canonical cell_id到显式nonce的完整对象",
    "schedule_uris": "六个canonical cell_id到证据URI的完整对象",
    "created_at": "显式ISO时间",
    "authorization_hash": null
  }
}
```

以上为结构说明，字符串占位项不是可执行配置。不得用测试donor/persona/理由/模型
fixture冒充实际来源；未决值会被拒绝，不内置N/T/seed等研究默认值。
模型/环境字段仍是声明的candidate provenance，本命令不会验证真实服务、环境安装
或URI文件存在。首次上云前须另核验真实环境和服务身份；不能把声明说成观察证据。

候选必须由 `build_six_cell_candidate` 构造，包含完整人口/persona、初态、排程来源和
六格binding。输入全量冷重放后才创建文件；Python/random来源版本不符时拒绝。

## 三条命令

在项目环境中设定 `PYTHONPATH=platform/src`，使用与候选排程来源匹配的Python：

```text
python -m agent_ex.identity_network.candidate_cli prepare --request request.json --root prepared-candidate
python -m agent_ex.identity_network.candidate_cli check-initial --root prepared-candidate
python -m agent_ex.identity_network.candidate_cli resume-init --request request.json --root prepared-candidate
```

- `prepare`：目标必须是不存在的子目录、父目录已存在；先写并fsync完整
  `preparation.json`，再创建六个独立SQLite和round0。已有目录一律拒绝，不能覆盖。
- `check-initial`：从完整存储计划重建来源和manifest；要求六格都已封存且无attempt/event。
  不补缺失初态、不获取writer lease、不发送请求。输出仅hash与计数，不含理由或响应。
- `resume-init`：请求必须与已存计划完整一致；保留所有已有证据，只补齐缺失数据库/
  缺失初态。六格已有数据须符合相同候选，任何已启动attempt/event均拒绝初始化。

成功退出0，stdout为脱敏ArtifactEnvelope；失败退出2且不打印输入内容或traceback。
目录路径拒绝静态symlink/reparse；不是针对攻击者并发替换路径的文件系统沙箱。
检查期间检测数据库变化，遇到运行中的归档应停止并等稳定副本，而非修改其数据。

## 中断与迁移

保留整个归档目录，包含完整计划、数据库及SQLite必要的sidecars；不要单独复制
数据库或改写nonce/manifest。不得把部分写坏的计划、异常临时文件或损坏数据库当成
可自动恢复的正常前缀：命令会fail closed，需要先保留证据并人工定位。
本轮已验证独立Python进程冷读取；Linux现场复验与真实运行授权仍待后续完成。

此入口创建的manifest没有 `sis_diagnostic_authorization_hash`，已有低层运行器因此
不能发送请求。未来真实启动要另绑定human receipt、source bundle、服务交接及
实际模型/环境；不能手工给此JSON加一个hash就视为获准。
