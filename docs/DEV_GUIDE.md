# 开发指南（DEV_GUIDE）

> 本文档面向“日常开发/扩展/修 bug”，强调 **不引入回归** 的规范与流程。

## 1. 环境与运行

### 1.1 Python 与依赖
推荐：
- Python 3.10+（3.9 也可）
- 依赖：`PyQt6`, `numpy`, `scipy`（可选：有 SciPy 才能用精确后端）

安装示例：
```bash
pip install PyQt6 numpy scipy
```

### 1.2 启动
在仓库根目录：
```bash
python run.py
```

---

## 2. 贡献流程（建议固定）

### 2.1 分支
- `main`：稳定可运行
- 功能开发：`feature/<name>`
- 修 bug：`fix/<name>`

### 2.2 提交粒度
- 一次 commit 只做一类变更（例如“点线约束 UI”）
- commit message 用动词开头：`Add ... / Fix ... / Refactor ...`

### 2.3 合并前自检（非常重要）
- 启动不崩溃（MainWindow 能打开）
- 拖拽点时约束能收敛（长度不漂）
- sweep 在死点处会停，而不是拉长杆
- 保存/加载不丢字段（expr/parameters/constraints）

---

## 3. 新增约束的“强制清单”
新增任何约束（例如“点到圆/线线平行”等）必须按以下顺序做完，否则容易漏：

### 3.1 core/controller.py
- 增加存储 dict：`self.xxx_constraints = {}`
- 增加 id 生成器：`self._next_xid`
- 增加命令：
  - `cmd_add_xxx(...)`
  - `cmd_delete_xxx(xid)`
  - `cmd_set_xxx_enabled(xid, enabled)`
  - `cmd_set_xxx_hidden(xid, hidden)`
- 在 `solve_constraints()` 迭代中加入该约束的投影/残差计算
- 在 `to_dict()/from_dict()` 序列化/反序列化该约束

### 3.2 core/solver.py（或新 solver 模块）
- 实现 PBD 投影函数（输入点坐标、锁定状态、目标参数）
- 输出：
  - 更新后的坐标增量
  - 残差（用于 over/可行性判定）

### 3.3 core/constraints_registry.py
- 让约束在 Constraints Tab 中“可见”
- 支持：
  - 列表行生成（类型、文本）
  - 删除/启用/隐藏路由到 controller 对应 cmd

### 3.4 ui
- 右键菜单入口（例如对点/线/角的菜单）
- 列表选择与画布高亮同步
- 可选：画布符号标记 item（例如“∈”）

### 3.5 docs
- 更新 `docs/ARCHITECTURE.md`（新增约束类型）
- 更新 `docs/CHANGELOG.md`（版本记录）

---

## 4. 参数与表达式系统

### 4.1 规则
- 数值字段保留 `x/y/L/deg`
- 表达式放在 `x_expr/y_expr/L_expr/deg_expr`
- 在每次求解前调用 `recompute_from_parameters()`：
  - 解析表达式 -> 得到 float -> 写回数值字段
  - 解析失败：保留旧值，并给 UI 标记（不崩溃）

### 4.2 安全性
表达式解析应使用白名单（例如 sympy 的安全子集）：
- 允许：`+ - * / ** ( )`
- 允许函数：`sin cos tan asin acos atan atan2 sqrt abs`
- 常量：`pi, E`

---

## 5. 求解器开发注意事项

### 5.1 PBD（交互）
- 目标：拖拽稳定、不抖
- 约束顺序要固定
- 迭代次数提供默认值（例如 20~80），必要时可在设置中暴露

### 5.2 SciPy（精确）
- 目标：残差更小，适合 sweep/导出
- 使用 `least_squares`，初值用上一步结果
- 对无解步：返回失败并给出 msg

### 5.3 Dead-point（死点）处理策略
当前策略（工程化）：**宁可停，也不变形**  
- 每一步求解后计算 `max_error`
- 超阈值：回滚该步 + 停止 sweep + 记录失败原因

后续增强可做：
- 自适应步长（靠近死点减小步长）
- 支路切换（open/crossed 两解切换）
- 多初值尝试（随机扰动）

---

## 6. UI 开发规则（防启动崩溃）

1) UI 调用 controller 的方法，必须存在且为公共 API  
2) 若需要兼容旧工程/旧 controller：UI 端做 `hasattr` 兜底，但最终仍要在 controller 补齐接口  
3) 菜单绑定建议走“安全绑定”工具函数：不存在则禁用该菜单项（启动不崩）

---

## 7. 版本与发布（强烈建议固定）

### 7.1 版本号
建议语义化版本：
- `MAJOR.MINOR.PATCH`
- 大功能：MINOR +1
- 修 bug：PATCH +1

### 7.2 Git tag 与 GitHub Release
发布流程：
```bash
git add .
git commit -m "Release: vX.Y.Z"
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```
然后在 GitHub Releases 上传 `planar_sketch_vX.Y.Z_code.zip`。

---

## 8. 故障排查（常见坑）

### 8.1 “点可随意拖动，约束不生效”
- 检查 `solve_constraints()` 是否完整、是否被缩进错位
- 检查拖拽事件是否调用 `solve_constraints()`

### 8.2 “启动报 AttributeError（controller 缺方法）”
- 确认运行的 controller 路径（打印 `controller.__file__`）
- 保证 UI 使用的方法在 `SketchController` 中存在

### 8.3 “四连杆死点时长度被拉长”
- sweep 必须有可行性检查（max error 阈值）
- dead-point 步应停或切换策略，不允许变形穿越
