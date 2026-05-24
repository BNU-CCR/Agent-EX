from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OpinionRecord:
    round_id: int
    text: str
    score: int


@dataclass
class Agent:
    agent_id: int
    role_description: str
    initial_score: int
    current_score: int
    stubbornness: float = 0.3  # 固执度 0-1，越高越难被影响
    history: list[OpinionRecord] = field(default_factory=list)

    def visible_history(self, memory_window: int) -> list[OpinionRecord]:
        return self.history[-memory_window:]

    def add_record(self, round_id: int, text: str, score: int) -> None:
        self.current_score = score
        self.history.append(OpinionRecord(round_id=round_id, text=text, score=score))


def default_roles() -> list[tuple[str, int, float]]:
    """返回 (角色描述, 初始评分, 固执度) 的列表"""
    return [
        # 极端支持（10分）
        ("35岁AI公司技术总监，坚信AI是生产力革命，应该全面取代重复性劳动", 10, 0.6),
        # 温和支持（7-8分）
        ("25岁科技公司算法工程师，乐观看待AI提升生产效率", 8, 0.3),
        ("29岁创业者，支持用AI创造新商业模式和新岗位", 8, 0.4),
        # 中立偏支持（6分）
        ("38岁企业管理者，关注AI降本增效与组织转型", 6, 0.4),
        ("34岁自由职业者，认为AI会重塑但不必然摧毁就业", 6, 0.2),
        # 中立（5分）
        ("45岁职业教育教师，关注AI时代技能再培训", 5, 0.3),
        ("22岁应届毕业生，既期待AI机会也担心求职竞争", 5, 0.2),
        # 中立偏反对（4分）
        ("30岁劳动法研究者，重视就业保障与劳动者权益", 4, 0.5),
        ("41岁公共政策研究员，主张用制度缓冲技术冲击", 4, 0.4),
        # 温和反对（3分）
        ("57岁小微企业主，担心普通劳动者难以适应技术变化", 3, 0.5),
        ("52岁传统制造业工人，担心AI替代岗位导致失业", 3, 0.7),
        # 极端反对（1分）
        ("48岁被裁员的前银行职员，坚决反对AI取代人类工作，认为资本在掠夺劳动者", 1, 0.8),
    ]


def build_messages(
    agent: Agent,
    topic: str,
    neighbor_context: str,
) -> list[dict[str, str]]:
    system = (
        f"你是一位{agent.role_description}。"
        f"你正在参与关于「{topic}」的社交媒体讨论。"
        f"请记住：你是基于自己的人生经历和立场在发言，不是评论员。"
        f"{'你比较固执，不容易被别人的话改变。' if agent.stubbornness > 0.5 else ''}"
    )
    user = f"""你当前对「{topic}」的立场：{agent.current_score}/10分。

你刷到了一些邻居的发言：
{neighbor_context or "（暂时没有邻居发言）"}

要求：
1. 用你自己的身份和经历来表达观点，不要说套话
2. {'可以听听邻居怎么说，但你有自己的判断。' if agent.stubbornness < 0.5 else '坚持你自己的看法，邻居的观点仅供参考。'}
3. 80字以内，像真实社交媒体发言那样自然
4. 最后一行严格输出：【评分：X】（X为1-10的整数）"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
