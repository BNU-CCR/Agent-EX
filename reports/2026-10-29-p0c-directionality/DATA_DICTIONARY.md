# P0-C 数据字典

- stimulus_inventory：51个实际wire去重材料，kind区分42初始理由/6命题/3事实卡。全文留私有；text_sha256按原UTF8，characters为Unicode字符数而非token。
- mapping_and_order_audit：topic/p/m对应实际显示codes、原语义order与解析规则；m同时改变配对和语义排列。
- proposition_reversal_audit：原/反命题身份与互补性限制，AI反命题包含相等。
- feed_content_audit：固定feed实际槽位、来源别名、原语义分数、理由hash/字数。不是整个消息网络。
- event_sampling_frame：全量合格事件的分层计数。category可重叠；population与sampled按层记录，不把各类相加为事件总数。
- sampled_event_index：331唯一事件，event_id为topic/seed/cell/globalordinal的SHA前缀；R0=initial_stance，事件前=before，事件后=after。window为floor((ordinal//500)/10)，即0..9为第一窗口；不是以人为结果挑窗。
- source_version：退休parent T30、退休tail T31–60、跨题三批身份分开；run_id在数值包里退休可能是parent-plus-tail合成轨迹ID，实际原run ID另存私有恢复。
- selected_categories：此事件被哪些配额选中，可多值；不是它全部可能符合的类别。
- feed_direction：empty或实际feed均值相对before的lower/equal/higher；不是相对R0，不将low/high固定材料标签套用到网络。
- prior_exposure_slots：该Agent更新前实际收到的累计槽位，含同源重复，不含当前feed或潜在帖子。
- activation_before：更新前已完成模型事件次数，不含Round0；原successful_update_count额外包含1条初始更新。
- stance_transition_by_exposure：topic/version/seed/cell/window/before/after/feed_direction/prior_slots_band的全量计数。是完整分母来源，不是331案例估计。
- event_exposure_summary：按版本/feed方向/此前槽位层的all/changed/5_to_3/3_to_5计数；all与其他measure不相加。
- sampled_material_features：实际wire、前后理由hash、实际记忆条数、模型/renderer/revision、历史context配置、发布标志。空new_public_semantic表示该事件未新发布，不表示公开库存为空。
- sampled_feed_slots：实际数组顺序；source_publication_ordinal空值可为Round0，不用0替代；message_age沿用原selection定义，非现实秒数。backend群体与model_visible_source_group分列，后者not_shown不能用后台值回填。
- lexical_*_flags：预设中文词表字面出现，只用于可检查检索，不表示自动论据分类或说服力。
- historical_context_cap：历史服务配置上限（退休4096/跨题8192），不是HTTP每请求携带字段，也不代表所有请求用满context。
- private-sampled-events-final-v1.jsonl.gz：受控私有原始恢复证据，包含正文，不进Git或公共包；public receipt仅提供SHA及88源前后不变证明。

数值分数均为原命题1..7顺序档位，不预设心理等距。seed/run是独立重复层，事件与Agent不作为独立重复做正式显著性。
