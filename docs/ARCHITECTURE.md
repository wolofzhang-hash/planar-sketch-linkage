# 架构说明（ARCHITECTURE）

> 本文档用于把 **Planar Sketch Linkage** 的核心结构、数据模型、求解流程与 UI 组织方式固定下来，避免“改着改着忘了/接口对不上”。

## 1. 代码目录结构

项目根目录（仓库根）：

- `run.py`：启动入口（创建应用/主窗口）
- `planar_sketch/`
  - `app.py`：应用入口封装（`main()`）
  - `core/`：**数据模型 + 控制器 + 求解器 + 序列化**
    - `controller.py`：`SketchController`（全局核心）
    - `solver.py`：PBD 约束投影求解（交互实时）
    - `scipy_kinematics.py`：SciPy 运动学后端（精确求解/扫掠）
    - `constraints_registry.py`：约束列表统一视图（UI 列表/删除/启用等路由）
    - `parameters.py`：参数系统与表达式计算（用于点/长度/角度）
    - 其他：几何工具、命令栈、常量等
  - `ui/`：**界面与交互**
    - `main_window.py`：主窗口、菜单、布局
    - `panel.py`：右侧 Sketch 面板（tabs）
    - `tabs.py`：Points/Lengths/Angles/Constraints/RigidBodies/Parameters 的表格与交互
    - `sim_panel.py`：Simulation 面板（驱动、扫掠、导出）
    - `items.py` / `view.py`：画布图元（点、线、角、约束标记）、选择与拖拽
  - `utils/`：通用工具（Qt 安全调用、常量、导出等）
- `docs/`：项目“Codex”文档
  - `ARCHITECTURE.md` / `DEV_GUIDE.md` / `CHANGELOG.md`

---

## 2. 数据模型（核心数据结构）

> 设计原则：所有数据**集中存储**在 `SketchController`，所有修改**通过 cmd_*** 执行，以确保 Undo/Redo 与一致性。

### 2.1 点（Points）
通常是 `self.points: dict[int, dict]`，每个点：

- `id`：点编号（dict key）
- `x, y`：数值坐标（float）
- `fixed`：是否固定（bool）
- `hidden`：是否隐藏（bool）
- `x_expr, y_expr`：表达式字符串（可选，字符串为空表示不用表达式）

表达式优先级：
- 若 `x_expr` 非空：用参数系统计算并写回 `x`
- 若 `y_expr` 非空：用参数系统计算并写回 `y`
- 计算失败：保留旧数值，并在 UI 提示错误（不崩溃）

### 2.2 长度（Lengths / Distance constraints）
通常是 `self.lengths` 或 `self.links`（视版本命名），每条：

- 端点：`i, j`
- `L`：长度数值（float）
- `L_expr`：长度表达式（可选）
- `enabled/hidden/over`：启用/隐藏/超约束标记
- `mode`：通常分 `REF`（参考，不参与求解）与 `CONSTRAINT`（参与求解）

### 2.3 角度（Angles）
每条角度约束一般由 3 点定义（或“向量角/关节角”两类）：

- `a, b, c`（或 `i, j, k`）：三点定义
- `deg`：角度（度）
- `deg_expr`：表达式（可选）
- `type`：vector/joint（视项目定义）
- `enabled/hidden/over` 同上

### 2.4 重合（Coincide）
约束两个点位置相同：

- `p, q`
- `enabled/hidden/over`

### 2.5 点线约束（Point-on-Line）
本项目新增（v2.4.20 起）：点 P 落在由两点 i-j 定义的“无限直线”上：

- `p`：被约束点
- `i, j`：定义直线的两点
- `enabled/hidden/over`

### 2.6 刚体（Rigid Bodies）
刚体通常由多条“刚边”组成（点对距离保持不变）：

- `body_id -> {points:[...], edges:[(i,j,L0)...], enabled, hidden}`
- 求解时相当于多条长度约束（或专门投影）

### 2.7 参数系统（Parameters）
`self.parameters: dict[str, float]`

- 参数名：`a, L1, theta0` 等
- 参数值：float
- 表达式可引用参数与安全函数（如 `sin, cos, pi` 等）

---

## 3. 控制器（SketchController）职责划分

`SketchController` 是系统中心，主要职责：

1) **数据管理**：points/lengths/angles/constraints/bodies/parameters 的存储  
2) **命令接口**：所有修改通过 `cmd_*` 方法，写入 command stack（Undo/Redo）  
3) **求解**：
   - `solve_constraints()`：PBD 实时投影（交互拖拽时稳定）
   - `solve_constraints_scipy()`：SciPy 精确求解（更严格的残差最小化）
4) **仿真与驱动**：
   - driver 输入角、输出角、扫掠（sweep）
   - dead-point 附近做可行性检查（不允许“拉伸长度硬跑过去”）
5) **序列化**：
   - `to_dict()/from_dict()`：保存/加载工程文件（包含表达式与参数）

---

## 4. 求解器与流程

### 4.1 PBD（Position Based Dynamics）实时求解
PBD 特点：快、稳定、适合拖拽；代价是精度依赖迭代次数与权重策略。

典型迭代顺序（建议固定）：
1) 参数表达式重算（把 `*_expr` 写回数值）
2) 重合（Coincide）
3) 点线（Point-on-Line）
4) 刚体边（Rigid edges）
5) 长度约束（Distance）
6) 角度约束（Angle）
7) over 检测与标记

**强制规则**：`solve_constraints()` 必须存在且包含完整迭代流程，严禁缩进错位导致“求解代码跑到别的函数体里”。

### 4.2 SciPy 运动学后端
用于：
- “Solve Accurate”
- sweep 中每一步更稳的收敛（若失败可 fallback 到 PBD 或停止）

实现思路：
- 未知量：所有非 fixed 点的 `(x,y)` 拼成向量
- 残差项：长度/角度/重合/点线/刚体边
- `scipy.optimize.least_squares` 求解最小二乘
- 初值：上一步结果（continuation）提高收敛

### 4.3 Sweep 可行性检查（dead-point 保护）
四连杆死点附近可能无解。策略：
- 每一步求解后计算 `max_constraint_error`
- 超过阈值：回滚该步并停止 sweep（或标记失败），**不允许拉伸长度“硬跑过去”**

---

## 5. UI 组织与交互

### 5.1 面板 Tabs
右侧 Sketch 面板 Tabs 通常包含：
- Points
- Lengths
- Angles
- Constraints
- Rigid Bodies
- Parameters（v2.5.0 起）

每个 Tab 的职责：
- 表格编辑（数值/表达式/启用/隐藏）
- 与画布选择同步（选中列表 -> 高亮图元；点选图元 -> 定位行）

### 5.2 右键菜单
右键菜单用于快速创建/编辑：
- 点：添加约束（重合、点线等）
- 线/角：添加长度/角度约束
- 约束标记：删除/启用/隐藏

### 5.3 画布拖拽
拖拽点时：
- 更新点坐标（若点非 fixed）
- 调用 `solve_constraints()`（PBD）实时收敛
- 刷新图元与标签（长度/角度显示）

---

## 6. 文件与兼容性

工程文件（建议 JSON）应包含：
- points（含 fixed/hidden + expr）
- lengths/angles/constraints/bodies
- parameters
- driver/output/measures（若有）

兼容原则：
- 读旧文件时：缺字段用默认值补齐
- 写文件时：完整写出新字段（expr/parameters）

---

## 7. 关键“防回归”清单

1) UI 调用的 controller 方法必须存在（或 UI 做兼容兜底），避免启动崩溃  
2) 求解流程必须在 `solve_constraints()` 中，严禁缩进/复制粘贴导致代码块漂移  
3) 新增约束必须同时更新：controller + solver + registry + UI + IO + docs/changelog  
4) sweep 必须做可行性检查，禁止通过死点时改变长度  
