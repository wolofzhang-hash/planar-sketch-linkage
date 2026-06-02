"""Planar Sketch – Synthesis (智能推荐) 模块

本包用于承载“从需求出发推荐机构拓扑 + 预置测量/驱动/Case + 初始化优化参数”的能力。

当前版本先提供：
- 需求数据结构（requirements）
- 曲线/函数的标准化与相似度（metrics）
- 候选机构检索接口骨架（retrieval）

后续可接：
- 内置模板库（四连杆/六连杆/舱门模板）
- 本地机制库/数据集（含 LINKS 风格的 coupler path atlas）
- 多 case 优化器（SciPy least_squares / 自研）
"""

from .requirements import DriverSpec, DoorSpec, CaseSpec, SynthesisProblem
from .retrieval import RetrievalConfig, TopologyCandidate, retrieve_candidates

__all__ = [
    "DriverSpec",
    "DoorSpec",
    "CaseSpec",
    "SynthesisProblem",
    "RetrievalConfig",
    "TopologyCandidate",
    "retrieve_candidates",
]
