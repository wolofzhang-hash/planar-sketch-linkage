from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from .metrics import Point, bidirectional_chamfer, normalize_path
from .requirements import CaseSpec, OutputType, SynthesisProblem


@dataclass
class RetrievalConfig:
    """检索配置。

    - top_k: 返回候选数量
    - normalize: 是否对路径做标准化（位置/尺度/方向不重要时建议 True）
    - score_fn: 自定义相似度（默认：bi-directional chamfer）
    """

    top_k: int = 10
    normalize: bool = True
    score_fn: Callable[[Sequence[Point], Sequence[Point]], float] = bidirectional_chamfer


@dataclass
class TopologyCandidate:
    """一个候选机构（拓扑 + 初始化 + 得分）。

    这里先留一个与外部库/模板对接的最小字段。
    """

    template_id: str
    score: float
    # 可选：附带解释信息（用于 UI 显示与报告生成）
    notes: str = ""


def _extract_target_path(case: CaseSpec) -> Optional[List[Point]]:
    if case.door.output_type != OutputType.PATH:
        return None
    pts: List[Point] = []
    for row in case.door.targets:
        # (u, x, y)
        if len(row) >= 3:
            pts.append((float(row[1]), float(row[2])))
    return pts if pts else None


def retrieve_candidates(
    problem: SynthesisProblem,
    *,
    config: RetrievalConfig,
    # mechanism_db: 未来对接本地数据库/数据集（如 LINKS atlas）
    # 这里先用 templates 作为占位。
    templates: Optional[Sequence[str]] = None,
) -> List[TopologyCandidate]:
    """基于需求检索候选拓扑。

    当前为“骨架版本”：
    - 仅演示 PATH 类型的 case 如何做 shape 检索
    - templates 只传入 template_id 列表，score 先给占位

    未来版本：
    - 接入 mechanism_db（拓扑 + 运动学仿真 + 预计算的路径特征）
    - 支持 ANGLE / POSE（函数生成/运动生成），以及多 case 聚合评分
    """

    templates = list(templates or [])
    # 兜底：没有模板时，至少给几个常用族
    if not templates:
        templates = [
            "4bar-crank-rocker",
            "4bar-double-rocker",
            "6bar-watt-I",
            "6bar-watt-II",
            "6bar-stephenson-I",
            "6bar-stephenson-II",
        ]

    # 目前：若存在 PATH case，就用目标路径做一个“占位式评分”。
    # 真正实现时，需要对每个 template 生成/读取一批实例的路径，并做最小距离检索。
    target = None
    for c in problem.cases:
        target = _extract_target_path(c)
        if target:
            break

    if target and config.normalize:
        target = normalize_path(target)

    out: List[TopologyCandidate] = []
    for tid in templates:
        if target is None:
            out.append(TopologyCandidate(template_id=tid, score=float("inf"), notes="(no target)"))
        else:
            # TODO: replace with real atlas search.
            # For now, return same score so UI can be wired.
            out.append(TopologyCandidate(template_id=tid, score=1.0, notes="TODO: atlas retrieval"))

    out.sort(key=lambda x: x.score)
    return out[: max(1, config.top_k)]
