---
status: active program map
authority: allocation of research questions across papers; not a Paper 1 execution source
supersedes: the undifferentiated multi-factor roadmap in logs/notion-2026-05-23.md
last-verified: 2026-07-16
---

# 长期研究计划

## Paper 1：固定网络中的意见形态演化

核心问题是多轮局部暴露、理由生成和历史连续性如何使 LLM-agent 网络走向整体均质化、单向端点集中、极化或“组内均质化—组间差异化”。身份信息与连续性被正交拆分，局部 WS 暴露以同数量 shuffled social 为识别对照。

主实验不研究权重微调、安全对齐、动态重连或真人社会效应。开放权重模型提供可复现的主证据，固定 snapshot API 提供有限的模型系统外部稳健性证据。

## Paper 2：模型对齐与生成分布

在 Paper 1 机制和平台稳定后，研究 instruct/abliterated、安全对齐、模型家族、议题敏感度和解码参数如何改变分布压缩、理由多样性及端点集中。05-23 的 RLHF 大设计属于本层，不能回流 Paper 1 主矩阵。

## 外部效度研究

研究真实社交媒体网络初始化、真人—AI 混合网络、历史行为回放、推荐和关系重连。此层才能更接近“Agent 进入真实舆论网络”的社会效果问题；Paper 1 只为其提供可控机制基线。

## 长期实验平台 / benchmark

复用相同领域模型、事件存储、调度、恢复和分析边界，通过新增协议与 adapter 承载多模型、多议题和 GLM-agent benchmark。平台不是通用 Web 产品，也不以复制 Notebook 为目标。

## 顺序依赖

`Paper 1 协议冻结 → mock/真实模型校准 → N=200/500/1000 有限规模 gate → N=1000 正式矩阵 → 稳健性子集 → Paper 2/外部效度扩展`。
