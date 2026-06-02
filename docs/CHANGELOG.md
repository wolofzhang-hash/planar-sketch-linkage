# 变更日志（CHANGELOG）

> 记录每个版本的主要功能与破坏性变更，便于回溯与定位回归。

## v2.12.73
- 维护：i18n 文案外置到 `planar_sketch/ui/locales/en.json` 与 `zh.json`，`ui/i18n.py` 改为加载器 + helper。
- 维护：新增 `run_models.py`，引入 `CaseSpec`、`RunRecord`、`ReplayFrame`、`ReplayBundle` dataclass，开始替代裸 dict 协议。
- 维护：`RunService` / `ReplayService` 增加 dataclass 访问接口，`CaseRunManager` 增加类型兼容 helper。
- 测试：新增 `tests/` 回归测试，覆盖 case/run 持久化分离、replay 读取、i18n 外置加载、dataclass round-trip。
- 文档：更新 `ARCHITECTURE.md` 与 `DEV_GUIDE.md`，反映长期维护阶段的服务边界与测试要求。

## v2.12.08
- 清理：UI 模块中多轮补丁残留代码继续收敛，减少重复 wrapper / 兼容别名。
- 统一：表格右键框架集中到 `table_context_menu.py`（builder + dispatch + install 入口）。
- 规范：UI 双语仅保留 `zh/en`，语言读取统一走 `i18n` helper（`_lang/_tr/get_ui_language/set_ui_language`）。
- 清理：载荷/摩擦/测量、草图表、优化表的新增/删除按钮入口改为右键后，相关按钮对象/布局/连接/文案分支做真删除。
- 修复：中英文界面切换时右键菜单文案错乱问题（按软件设置语言实时读取）。
- 文档：补充 cleanup sprint 说明，更新 README 与仓库上传用 `.gitignore`。

## v2.12.07
- 清理：UI 模块硬编码中英文文案（重点覆盖右键菜单、提示框标题/正文、结果图窗口等）并统一接入 i18n。

## v2.11.22
- 新增：Intelligent Design 增加“机构族”筛选（Any / 凸轮 / 4连杆 / 6连杆 / 滑轨连杆）
- 扩展：概念库 catalog 扩展为凸轮、4连杆多形态、6连杆经典拓扑、滑轨连杆多形态
- 新增：内置模板扩展：4bar_crank_rocker、4bar_double_rocker、4bar_toggle、offset_slider_crank、dual_slider、6bar_watt1、6bar_stephenson1

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
