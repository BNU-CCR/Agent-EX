# 240请求操纵检验候选：用户决定与待确认语义

状态：2026-10-01用户候选方案已记录；下述代码接法和统计细节待确认。
preliminary / not_frozen / formal_parameter_authority=false；不是云端执行批准。

## 用户已给出的候选

- 30个独立benchmark cases，distance=1/2/3 × upward/downward六strata各5。
- 每case Blue→Blue、Blue→Green、Green→Green、Green→Blue四个cell；箭头表示
  focal group→source group。除这两项标签外全部内容固定。
- 每cell两次独立生成：30×4×2=240 requests。
- `toward_source_shift = abs(pre_stance-source_stance)-abs(post_stance-source_stance)`。
- mean paired effect>0、paired-bootstrap95%CI不跨0、至少60%cases方向一致三者同时满足。
- 记录effect magnitude；reason adoption和confidence change仅secondary。
- 无可靠信号仅进入一次既定stance-neutral shared-group framing，不调prompt寻找显著。

## 推荐代码接法（待确认，不先改代码）

保留原单quartet v1为可复现素材合同。增加独立versioned重复层，trial identity包含
case、replicate、focal/source label；30case identity不变，不通过复制case变成60独立样本。
每次生成均保存exact messages、seed、prompt hash、response/parse和持久化dispatch状态。
未知发送是否完成时停止，不自动重发。

统计口径建议：每case同组4响应（2focal labels×2repeats）和异组4响应分别等权平均
toward_source_shift，取 `d_case=ingroup_mean-outgroup_mean`；总体effect为30个d_case均值。
方向一致定义为d_case>0，占比>=0.60；恰好0不计正向。CI必须lower>0，边界0不通过。
case为bootstrap单位，8个请求不能当作8个独立benchmark cases。

可选bootstrap口径：整体重抽30case，或六strata内分别重抽5case后合并；后者保持
原分层配额，推荐作为该平衡设计的候选。两者不是可按结果挑选的分析菜单，运行前
必须选择一种并绑定次数、分析seed和CI计算方式。

生成seed可在同一replicate quartet内配对、两个replicate使用不同seed；也可八项
各自独立seed。两种政策必须预先选择，不能依结果更换。当前未填任何seed默认值。

书面复核还识别出以下须确认的边界：

- “独立case”须由不同基准内容/来源的操作定义保证，不能只改case ID。
- 建议仅完整240项且全部可解析时判定pass/no-signal。缺失、拒答或解析失败为
  execution/measurement invalid，不擅自删case、补样本或缩小30case分母；也不能因
  执行失败自动启动Stage-B。已有安全停止/不重发规则不变。
- 建议Stage-B复用同一30case、replicate/seed政策与三项判据，仅加入已预定义framing；
  不能fallback时同时改变样本或统计规则。须确认该复用范围。
- confidence change需要实际pre-confidence来源；没有该基准时只能标记不可计算，
  不用假定中点或把post-confidence称为change。这个secondary缺失不替代primary门。

还需实际30case来源及有序stance数值映射。现round0 source binder仅能生成已有候选
人口/初态中的帖子；若其不覆盖六distance/direction strata，必须显式物化独立benchmark
来源，不能偷偷修改study初态或凭测试fixture构造“真实”case。history也不能伪造。

## 当前不具备的执行权限

旧stage-one授权合同已接full source/规则/service evidence replay和exact human receipt；
它仍对应单quartet素材，不是240版本。单凭该合同、candidate hash或stage-two receipt
形状，均不能启动240请求或Stage-B。独立runner、versioned来源/分析、实际候选规则、
Linux现场服务观察及最终精确审批包接齐后才到需要开云服务器的边界。
