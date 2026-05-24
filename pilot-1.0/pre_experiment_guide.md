# 预实验方案指南

> **目标**：在 AutoDL 上跑通最小可用预实验流程，验证技术方案可行性  
> **时间**：2026-05-06  
> **状态**：即将启动

---

## 一、预实验目标

| 目标 | 验证内容 | 成功标准 |
|------|---------|---------|
| **环境验证** | vLLM + Qwen2.5-7B-Instruct 正常加载 | API 可响应请求 |
| **流程验证** | 单 agent × 1 轮交互完整 | 输出包含 `【评分：X】` |
| **规模验证** | 20 agents × 10 轮 | 方差收敛曲线可绘制 |
| **对比验证** | Instruct vs Abliterated 各跑一次 | 两组曲线有可区分差异 |

---

## 二、AutoDL 服务器选择

### 2.1 推荐配置

| 项目 | 推荐选择 | 备选 | 注意 |
|------|---------|------|------|
| **GPU** | RTX 4090D（24GB）× 1 卡 | - | 中国特供版，与普通 4090 几乎相同，可用 |
| **镜像** | **PyTorch 2.1 + CUDA 11.8** 或 **CUDA 12.x** | CUDA 13.x（vLLM 兼容性可能有问题） | 如果只有 CUDA 13 镜像，用最新 vLLM 版本 |
| **系统** | Ubuntu 22.04 | - | - |
| **数据盘** | **扩容到 270GB** | 50GB 勉强够但紧张 | 模型 14GB + 缓存 + 结果，建议扩容 |

### 2.2 省钱技巧

- **预实验阶段**：先租用 **1 小时** 测试环境，验证代码能跑再续费
- **正式 Phase 0**：租用 **2-3 小时**，足够跑完 20 agents × 50 轮 × 2 组
- **算力平台比价**：AutoDL vs 恒源云，RTX 4090 价格相近，AutoDL 胜在**镜像市场有现成 vLLM 环境**

### 2.3 租用步骤

```
1. 登录 https://www.autodl.com/
2. 进入「控制台」→「实例」
3. 点击「租用新实例」
4. 配置：
   - 区域：尽量选有货的（华北/华东）
   - GPU型号：RTX 4090
   - 镜像：选「PyTorch 2.1 + CUDA 11.8」或「vLLM 镜像」（如有）
   - 数据盘：100GB SSD
5. 支付后等待实例启动（约 3-5 分钟）
```

---

## 三、环境准备（SSH 登录后）

### 3.1 连接服务器

```bash
# AutoDL 控制台获取登录命令，格式类似：
ssh -p 12345 root@你的服务器IP
```

镜像和系统配置与之前相同即可，RTX 4090D 完全支持。

**关键调整**：数据盘建议扩容到 270GB，或在运行前清理 /tmp 目录。

**CUDA 13 处理**：如果必须用 CUDA 13 镜像，安装 vLLM 时指定最新版本：
```bash
pip install vllm --upgrade
```

### 3.2 创建项目目录

```bash
cd /root
mkdir -p experiment/{src,config,experiments,results}
cd experiment
```

### 3.4 安装依赖

```bash
pip install vllm transformers accelerate networkx scipy pandas numpy matplotlib seaborn openai
```

### 3.5 下载模型（可选，vLLM 会自动下载）

如果网络慢，可以先手动下载：
```bash
# 从 ModelScope 下载 Qwen2.5-7B-Instruct
git lfs install
git clone https://modelscope.cn/Qwen/Qwen2.5-7B-Instruct
```

---

## 四、代码结构（最小可用版）

```
experiment/
├── src/
│   ├── __init__.py
│   ├── network.py      # BA 网络构建
│   ├── agent.py        # Agent 类
│   ├── llm_client.py   # vLLM API 调用
│   └── simulator.py    # 主循环
├── config/
│   └── experiment.yaml # 参数配置
├── experiments/
│   └── run_pilot.py     # 预实验脚本
└── results/             # 输出目录
```

### 4.1 核心代码（关键文件）

**config/experiment.yaml**：
```yaml
experiment:
  n_agents: 20        # 预实验用 20，正式 200
  n_rounds: 10         # 预实验 10 轮，正式 50
  n_activated: 8      # 每轮激活 40%（20×0.4=8）
  m: 2                 # BA 网络参数
  alpha: 0.5          # 度数加权采样

model:
  name: Qwen/Qwen2.5-7B-Instruct
  temperature: 0.7
  max_tokens: 100

topic: "AI取代劳动力"
system_prompt: "你是一个{role_description}。你对'{topic}'这一议题有自己的立场和看法。"

output:
  results_dir: results/pilot_001
```

**src/llm_client.py**（关键）：
```python
from openai import OpenAI
import re

class VLLMClient:
    def __init__(self, base_url="http://localhost:8000/v1", model="Qwen/Qwen2.5-7B-Instruct"):
        self.client = OpenAI(api_key="EMPTY", base_url=base_url)
        self.model = model

    def generate(self, prompt, temperature=0.7):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=100,
        )
        return response.choices[0].message.content

    @staticmethod
    def extract_score(text):
        """从 LLM 输出中提取评分"""
        match = re.search(r'【评分：(\d+)】', text)
        if match:
            score = int(match.group(1))
            return score if 1 <= score <= 10 else None
        return None
```

**src/network.py**：
```python
import networkx as nx

def build_ba_network(n, m=2):
    """构建 BA 无标度网络"""
    G = nx.barabasi_albert_graph(n, m, seed=42)
    # 添加初始观点（1-10 正态分布）
    import numpy as np
    scores = np.random.normal(5, 2, n).clip(1, 10).round()
    nx.set_node_attributes(G, dict(enumerate(scores)), "score")
    return G
```

**src/simulator.py**（核心主循环）：
```python
import asyncio

async def run_simulation(client, network, config):
    """预实验主循环：同步批量更新"""
    results = {"rounds": [], "scores": [], "texts": []}

    for round_idx in range(config["n_rounds"]):
        # 1. 收集激活节点的邻居信息
        activated = list(network.nodes())[:config["n_activated"]]

        round_texts = {}
        round_scores = {}

        # 2. 并发生成（Semaphore 控制并发）
        semaphore = asyncio.Semaphore(5)  # 预实验用 5，正式用 10-15

        async def process_node(node_id):
            async with semaphore:
                neighbors = list(network.neighbors(node_id))
                # 采样邻居（最多 10 个）
                import random
                sample_size = min(10, len(neighbors))
                sampled = random.sample(neighbors, sample_size)

                # 构建 Prompt
                neighbor_context = "\n".join([
                    f"邻居{j}: {network.nodes[j].get('last_text', '（首次发言）')}"
                    for j in sampled if "last_text" in network.nodes[j]
                ])

                prompt = f"""你是一个{network.nodes[node_id]['role']}。
你对"AI取代劳动力"议题的当前看法是（1-10分）：{network.nodes[node_id]['score']}

邻居们的观点：
{neighbor_context}

请表达你对这个议题的看法（50字以内），并在最后一行输出：
【评分：X】
"""

                text = client.generate(prompt)
                score = client.extract_score(text)

                return node_id, text, score

        tasks = [process_node(n) for n in activated]
        outputs = await asyncio.gather(*tasks)

        # 3. 统一写入
        for node_id, text, score in outputs:
            round_texts[node_id] = text
            round_scores[node_id] = score
            network.nodes[node_id]["last_text"] = text
            if score:
                network.nodes[node_id]["score"] = score

        # 4. 记录本轮结果
        all_scores = [network.nodes[n]["score"] for n in network.nodes()]
        results["rounds"].append(round_idx)
        results["scores"].append(all_scores)

        print(f"Round {round_idx+1}: mean={np.mean(all_scores):.2f}, var={np.var(all_scores):.2f}")

    return results
```

**experiments/run_pilot.py**：
```python
#!/usr/bin/env python3
"""预实验脚本：20 agents × 10 轮"""
import sys
sys.path.append("/root/experiment/src")

from llm_client import VLLMClient
from network import build_ba_network
from simulator import run_simulation
import yaml, os

# 加载配置
with open("/root/experiment/config/experiment.yaml") as f:
    config = yaml.safe_load()

# 初始化 vLLM 客户端
client = VLLMClient(base_url="http://localhost:8000/v1")

# 构建网络
network = build_ba_network(n=20, m=2)

# 分配角色
roles = ["25岁激进左翼青年", "40岁保守派企业家", "30岁中立学者",
         "55岁传统行业工人", "28岁科技从业者"]
for i, node in enumerate(network.nodes()):
    network.nodes[node]["role"] = roles[i % len(roles)]

# 运行模拟
results = asyncio.run(run_simulation(client, network, config["experiment"]))

# 保存结果
import pandas as pd
os.makedirs(config["output"]["results_dir"], exist_ok=True)
pd.DataFrame(results["scores"]).to_csv(f"{config['output']['results_dir']}/scores.csv", index_label="round")
print("Done! Results saved.")
```

---

## 五、vLLM 服务启动

### 5.1 启动命令

```bash
# 在服务器上运行（推荐 screen / tmux 保持后台运行）
screen -S vllm
cd /root

python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --port 8000 \
    --max-num-seqs 20 \
    --gpu-memory-utilization 0.90

# 按 Ctrl+A+D 退出 screen
```

### 5.2 验证服务

```bash
curl http://localhost:8000/v1/models
# 应返回模型列表
```

### 5.3 测试 API

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen2.5-7B-Instruct", "messages": [{"role": "user", "content": "你好"}], "max_tokens": 50}'
```

---

## 六、执行步骤清单

### Step 1：租用 AutoDL 实例（本地操作）

- [ ] 登录 AutoDL
- [ ] 租用 RTX 4090（1 小时，先测环境）
- [ ] 记录公网 IP 和 SSH 端口

### Step 2：环境准备（SSH 连接后）

- [ ] `nvidia-smi` 确认 GPU 正常
- [ ] 创建项目目录 `/root/experiment/`
- [ ] 安装依赖包
- [ ] 或使用 AutoDL 镜像市场的 vLLM 镜像

### Step 3：上传代码

**方式 A：git clone**
```bash
cd /root
git clone https://github.com/572200469/Agent-EX.git
cd Agent-EX/experiment
```

**方式 B：手动上传（如果 git 慢）**
```bash
# 在本地压缩代码，通过 scp 上传
# 本地执行：
scp -P 12345 -r experiment/ root@你的服务器IP:/root/
```

### Step 4：启动 vLLM 服务

- [ ] `screen -S vllm` 创建会话
- [ ] 运行启动命令
- [ ] 等待模型加载（约 2-3 分钟）
- [ ] `Ctrl+A+D` 后台运行
- [ ] `curl` 验证服务正常

### Step 5：运行预实验

```bash
cd /root/experiment
python experiments/run_pilot.py
```

### Step 6：结果验证

- [ ] 检查 `results/pilot_001/scores.csv` 是否生成
- [ ] 绘制方差收敛曲线
- [ ] 确认曲线有下降趋势

### Step 7：对比实验（可选，如有时间）

- [ ] 停止 vLLM 服务
- [ ] 加载 abliterated 模型（如已准备好）
- [ ] 重复 Step 5-6

---

## 七、常见问题

### Q1：vLLM 启动报错 "Out of memory"

**原因**：显存不够  
**解决**：
- 降低 `--gpu-memory-utilization`（从 0.90 降到 0.85）
- 减少 `--max-num-seqs`（从 20 降到 10）
- 使用量化模型（Qwen2.5-7B-Instruct-AWQ）

### Q2：API 响应很慢

**原因**：模型正在生成，或并发过高  
**解决**：
- 减少 Semaphore 并发数
- 检查 GPU 利用率 `nvidia-smi`

### Q3：评分提取失败

**检查**：
- LLM 输出是否包含 `【评分：X】`
- 正则表达式是否匹配中文括号
- 添加 fallback：如果提取失败，用上一轮评分

### Q4：网络连接问题

**检查**：
- 防火墙是否开放 8000 端口
- 本地是否可访问 `http://服务器IP:8000/v1/models`

---

## 八、预算估算

| 项目 | 预估成本 |
|------|---------|
| 环境测试（1 小时） | ¥2-3 |
| 预实验（2 小时） | ¥4-6 |
| Phase 0 完整运行（8 组 × 2 小时） | ¥32-48 |
| **总计** | **约 ¥50-60** |

---

## 九、下一步（预实验成功后）

1. **正式 Phase 0**：跑完 8 种参数组合，确定 m 和 α 值
2. **代码优化**：添加日志、异常处理、断点续跑
3. **对比实验**：跑完 Instruct vs Abliterated 两组
4. **申请服务器**：带着预实验成果找吴老师申请实验室 GPU

---

*此文档为预实验操作指南，将在执行过程中持续更新。*
