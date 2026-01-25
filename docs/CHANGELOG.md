# 变更日志（CHANGELOG）

> 记录每个版本的主要功能与破坏性变更，便于回溯与定位回归。

## v2.6.6
- 修复：Sweep 增加可行性检查（dead-point 附近无解时停止/回滚），避免“拉长杆”硬穿越
- 清理：移除历史合并残留的异常求解代码块（防止未来触发错误）
- 保持：参数系统、点线约束、SciPy 后端可用

## v2.6.5
- 修复：`solve_constraints()` 恢复完整 PBD 迭代流程，约束重新生效
- 修复：controller 多处方法缺失/缩进错位导致 UI 启动崩溃的问题（统一补齐公共 API）
- 保持：SciPy 精确求解入口与 sweep 输出

## v2.6.0
- 新增：SciPy 运动学求解后端（`least_squares`）用于精确求解与 sweep
- 新增：Simulation sweep 结果更稳定（可选使用 SciPy）

## v2.5.1
- 修复：Sketch 面板重复定义导致 Parameters Tab 不显示

## v2.5.0
- 新增：参数系统（Parameters Tab）
- 新增：表达式支持（坐标 x/y、长度 L、角度 deg 均可绑定表达式）
- 新增：保存/加载包含 parameters 与 *_expr 字段

## v2.4.20
- 新增：点线约束（Point On Line），支持右键创建与 Constraints 列表管理

## v2.4.19
- 基线版本：Points/Lengths/Angles/Constraints/RigidBodies 基础编辑与 PBD 求解
