from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple


class DriverType(str, Enum):
    """驱动类型。

    - ROTARY: 输入为角度（deg 或 rad，由上层统一）
    - LINEAR: 输入为行程（stroke），通常来自液压/电动缸
    """

    ROTARY = "rotary"
    LINEAR = "linear"


class OutputType(str, Enum):
    """输出需求表达类型。"""

    ANGLE = "angle"  # 输出角（如舱门转角）
    PATH = "path"  # 单点轨迹
    POSE = "pose"  # 刚体位姿（>=2 点轨迹或 pose 序列）


@dataclass
class DriverSpec:
    driver_type: DriverType
    # 输入范围（角度或行程）
    u_min: float
    u_max: float
    # 采样点数（用于曲线/函数离散化）
    samples: int = 200
    # 驱动点/驱动关节的放置偏好（可选，由 UI 侧提供）
    anchor_hint: Optional[Tuple[float, float]] = None
    # 旋转驱动：初始角（相对水平），线性驱动：初始行程
    u0: float = 0.0


@dataclass
class DoorSpec:
    """舱门/输出对象描述。

    典型用法：
    - ANGLE：门绕铰链转角 θ_out(u)
    - PATH：门上某个点 P 的轨迹 (x(u), y(u))
    - POSE：门上两点 P,Q 的轨迹（即可恢复刚体位姿）
    """

    output_type: OutputType
    # 铰链（若是角度/位姿）
    hinge_a: Optional[Tuple[float, float]] = None
    hinge_b: Optional[Tuple[float, float]] = None
    # 目标：
    # - ANGLE: [(u, theta), ...]
    # - PATH : [(u, x, y), ...]
    # - POSE : [(u, x1, y1, x2, y2), ...]
    targets: Sequence[Tuple[float, ...]] = field(default_factory=list)
    # 允许误差（用于检索/优化权重的默认尺度）
    tol: float = 1e-2


@dataclass
class CaseSpec:
    """一个 case = 一个工况/一组约束。

    舱门场景常见：
    - 不同载荷/不同安装偏差下的输入-输出曲线约束
    - 不同阶段（比如解锁/开门/关门）分段曲线约束
    """

    name: str
    driver: DriverSpec
    door: DoorSpec
    # 额外几何/工程约束（最小间隙、长度范围、铰链位置范围等）
    # 这里先留接口，后续由 optimizer 解释。
    constraints: dict = field(default_factory=dict)


@dataclass
class SynthesisProblem:
    """智能综合问题：多 case + 目标 + 搜索/优化设置。"""

    cases: List[CaseSpec]
    # 期望机构复杂度（用于推荐模板 / 限制搜索空间）
    preferred_links: Optional[int] = None
    preferred_joints: Optional[int] = None
    # 是否允许 slider、齿轮等（当前 Planar Sketch 主体只实现关节/长度/角度，后续可扩展）
    allow_sliders: bool = False
