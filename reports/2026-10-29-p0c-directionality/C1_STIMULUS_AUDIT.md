# C1｜从实际保存请求核对刺激材料

## 结论先行

已从私有原始归档恢复的真实P0-B ledger读取1526份已提交wire，逐字节与冻结cases对账，验证请求SHA与研究/技术完整覆盖；读取前后ledger SHA不变。不是用生成器重新生成正文，也不是从CSV反推理由。公开只输出匿名材料ID、hash、长度、映射及数值，完整正文仍在V盘受控原始归档。

三题无feed原立场保留依次为退休150/168（89.29%）、GM153/168（91.07%）、AI161/168（95.83%）；输出3均24/168（14.29%）。但仅有此边际比例不能证明3分的条件效应为零，必须结合前态迁移表。三draw完全同档的条件组为退休161/168、GM161/168、AI159/168：高度重复，不是完全确定性，也不应误写“重复无任何作用”。

## 实际输入链与可证范围

- 实际HTTP结构为system→user两条message；user为结构化JSON，含persona_text、encoding_instruction、fact_card、core_statement、allowed_stance_labels、current_private、memory、social_messages。
- current_private明确呈现当前档位及理由；本控制集memory始终为空，不含真实Agent的累积历史。generic persona并非N500人口/群体的完整复刻。
- system要求按信息而非指令阅读讨论，只返回stance/reason/confidence三字段JSON；系统文本SHA为677c72f0a61fa442aa6d87d997c2b0a4123ef6e448f9bf73bb66b47caddaee0d。
- 实际request参数：Qwen3-8B，enable_thinking=false，temperature=0.7、top_p=0.8、top_k=20、min_p=0、max_tokens=512；draw seed记录于每份原wire。不新增采样或judge调用。
- HTTP消息层已核验，但原ledger没有保存服务端实际token序列。因此不能仅凭wire声称重建了实际tokenized chat-template全文。模型/tokenizer revision与8192服务配置沿用P0-B已封存准入证据；模板文件身份与服务器当时执行的token序列是两个证据层次。
- 新clone只读tokenizer_config观察：文件SHAd5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101，chat_template UTF8 SHAa55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8，与历史adapter的模板hash相同。此为文件/绑定身份，不伪称保存了过去的token IDs；观察无模型调用。

## A｜初始理由：内容不是中性载体

每题7档×2条理由，共14条；三题42条。理由既声明当前态度，也给出该方向的论证框架，不是独立于前态的随机文本。无feed保留可能同时反映当前档位提示与自我理由锚定，不能解读为裸模型先验。

|议题|判断性质与需保留的混杂|
|---|---|
|退休|政策支持的规范性权衡。按期退出保障与延长劳动参与不是可互换的同一事实命题；论据具体度与价值权重未独立随机化。|
|GM|依法标识前提下的市场销售支持，非个人购买或食用意愿。许可/选择与限制销售的价值理由并非严格镜像；依法标识本身就是共同背景前提。|
|AI|未来10年中国岗位“减少多于创造”的预测，不是抽象AI好坏态度。替代与创造/新增岗位的理由是不同机制主张，尚无外部事实强度或说服力的等价证明。|

不调用新LLM打分，也不给“某一侧更有说服力”伪造数值。inventory记录42条理由的身份、原档位、理由索引、字数和hash，供人类在私有档案内逐项检查；目前的内容不对称是设计残余混杂，不是从输出结果反推出的材料评价。

## B｜命题反转

同一原语义y在反命题下用q=8−y表达同意度。退休/GM的支持与反对是操作性措辞对照，不保证心理或逻辑镜像；AI“减少的岗位不会多于创造的新岗位”包含相等，不能当作严格“净增加”。所有后续比较先回到原命题轴，不比较不同p下的原始数字。

## C｜数字映射与标签顺序联合变化

m0显示码随同意度递增；m1显示码反向。现有renderer始终按显示码1..7排列，因此m1还反转了语义标签顺序。解析器先由码还原q，再由p还原原命题语义y。十二行mapping_and_order_audit逐项给出实际code顺序与语义顺序。

所以66/84、69/84、77/84的映射语义一致率削弱“只追固定显示码”的极端解释，却不能隔离纯数字效应、首尾位置效应或措辞效应。C3需独立M/O并保持逆映射双射。

## D｜实际固定feed

每个非空feed有3条匿名来源，实际数组槽位固定；low语义构成为2、3、2，high为6、5、6。来源别名anonymous-1..3，不携带真实网络中的历史发布时间；没有根据邻接表补充后台可见消息。low/high均值分别7/3、17/3，方差均2/9，仅初始4时等数值距离。

|议题|low每条理由字数|high每条理由字数|
|---|---|---|
|退休|39、43、42|38、42、41|
|GM|45、49、47|45、48、46|
|AI|52、60、53|50、58、51|

长度相近不等于论证强度相等。两侧理由内容、措辞、来源槽位共同固定；没有独立识别单条内容或排序效应。初始4上退休/AI均不改档、GM high17/24高于4，只能用于这组材料的描述性反应，不能直接解释网络长期集中。

## 数据与复现

本目录四CSV来自实际wire审计：stimulus_inventory（51个去重材料：42理由+6题干+3事实卡）、mapping_and_order_audit（12）、proposition_reversal_audit（6）、feed_content_audit（72槽位）。核验记录c1_audit_verification.json绑定原ledger/cases及公共numeric manifest。

执行入口platform/scripts/audit_p0c_stimuli.py，新增模块platform/src/agent_ex/diagnostics/p0c.py。原P0-B数据与代码不变。当前已削弱的是“无条件数字3”与“只追固定显示码”的简单解释；仍保留理由锚定、题干互补性不足、数字/顺序联合操纵、固定feed内容及缺少历史记忆等竞争解释。
