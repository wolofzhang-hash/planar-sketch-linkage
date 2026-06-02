# 智能综合（Synthesis）设计草案

> 目标：把“舱门需求（输入-输出角曲线/轨迹/多 case 约束）→ 推荐机构拓扑模板 → 自动建模与参数化 → 一键求解/优化”做成一条流水线。

## 1. 三类需求表达

1) **Function Generation（函数生成）**
- 输入：驱动角/行程 `u`
- 输出：门转角 `θ_out(u)`

2) **Path Generation（轨迹生成）**
- 输出：门上某个点的轨迹 `P(u) = (x(u), y(u))`

3) **Motion Generation（运动生成）**
- 输出：门刚体的位姿（至少两点轨迹，或 pose 序列）

## 2. 建议的软件流程

### 2.1 需求录入
- 选择驱动：旋转 / 直线
- 选择输出：角度 / 点轨迹 / 刚体位姿
- 建立多个 case：每个 case 可有不同的输入范围与约束

### 2.2 拓扑推荐
- 先用 **模板库**（四连杆/六连杆/舱门常用模板）做快速推荐
- 再用 **机制库检索（数值图谱/atlas）** 对目标曲线进行近邻检索

### 2.3 自动建模与参数化
- 插入模板后：
  - 自动创建驱动参数 `u`、扫掠范围、输出测量项
  - 自动建立多个 case
  - 自动生成长度变量与范围（初值可按几何尺度估计）

### 2.4 求解与优化
- 用现有 SciPy 后端/优化器执行多 case 约束求解
- 成功后输出：
  - 输入-输出曲线对比
  - 关键尺寸表
  - 机构拓扑说明与“为何推荐该拓扑”的解释

## 3. 代码落点（建议）

- `planar_sketch/core/synthesis/requirements.py`：需求数据结构
- `planar_sketch/core/synthesis/metrics.py`：曲线标准化与距离度量
- `planar_sketch/core/synthesis/retrieval.py`：候选检索接口

后续扩展：
- `planar_sketch/core/synthesis/templates/`：JSON 模板库
- `planar_sketch/core/synthesis/atlas/`：本地机制库索引（预计算特征）
- `planar_sketch/core/synthesis/optimizer.py`：多 case 优化封装
