# 架构说明

本文档描述 **Planar Sketch Linkage** 在 v2.12.73 之后的长期维护结构，重点覆盖 `case / run / replay`、外置 i18n、以及推荐的扩展边界。

## 目录结构

- `run.py`
  - 启动入口。
- `planar_sketch/`
  - `app.py`
    - 应用初始化。
  - `core/`
    - `controller.py`
      - `SketchController` 聚合核心控制逻辑。
    - `controller_model.py`
      - 模型编辑、脏标记、快照相关逻辑。
    - `controller_selection.py`
      - 选择、创建、约束编辑。
    - `controller_simulation.py`
      - 求解、载荷、测量评估相关逻辑。
    - `case_run_manager.py`
      - case / run 的磁盘读写与索引管理。
    - `project_paths.py`
      - 统一解析工程目录与未保存工程的 session 目录。
    - `run_service.py`
      - 统一 case/run 访问边界，屏蔽 UI 重复拼目录和 manager。
    - `replay_service.py`
      - 只读 replay 结果加载。
    - `run_models.py`
      - `CaseSpec`、`RunRecord`、`ReplayFrame` 等 dataclass 模型。
    - `headless_sim.py`
      - 隔离仿真与 sweep 逻辑。
  - `ui/`
    - `main_window.py`
      - 主窗口与 Ribbon 组装。
    - `sim_panel.py`
      - 仿真面板（求解、导出、保存结果）。
    - `analysis/animation_tab.py`
      - 工况表、回放、绘图。
    - `synthesis_tab.py`
      - 智能综合。
    - `display_format.py`
      - 数值显示格式统一入口。
    - `i18n.py`
      - i18n 加载与翻译 helper。
    - `locales/en.json`, `locales/zh.json`
      - 外置界面文案。
- `docs/`
  - `ARCHITECTURE.md`
  - `DEV_GUIDE.md`
  - `CHANGELOG.md`
- `tests/`
  - 长期维护阶段补充的回归测试。

## 核心边界

### Case
工况定义。只保存“怎么跑”：
- driver / output
- sweep
- solver
- loads / measurements
- 智能综合目标与模板元数据

### Run
一次运行结果。只保存“跑出来了什么”：
- `model.json`
- `case.json`
- `results/frames.csv`
- `summary.json`
- `status.json`

### Replay
对 run 的只读查看：
- 加载 `frames.csv`
- 加载 run 元数据
- 回放帧序列

**规则：** replay 不得成为 case 或普通 run 的默认输入源。

## 数据模型

### `CaseSpec`
定义在 `planar_sketch/core/run_models.py`。

用途：
- 作为 case 的类型化协议。
- 兼容旧的 dict 存储格式。

关键字段：
- `target_input_deg`
- `drivers`
- `outputs`
- `sweep`
- `solver`
- `loads`
- `measurements`
- `extra`

### `RunRecord`
描述磁盘上的一个 run 条目：
- `run_id`
- `path`
- `success`
- `n_steps`
- `updated_utc`

### `ReplayFrame`
包装单帧记录，当前仍保持字典兼容，便于平滑过渡。

## 服务层

### `ProjectPathService`
统一 project/session dir 解析。

目标：
- 未保存工程只生成一个共享 session 目录。
- 不同 tab 不再各自 `mkdtemp()`。

### `RunService`
统一对 `CaseRunManager` 的访问。

职责：
- `manager()`
- `load_case()` / `load_case_spec()`
- `list_run_records()`
- `save_case_run()`
- `save_last_run()`

约束：
- 普通求解只能写 `_last`
- case rerun 才能写 `runs/<case>/current`

### `ReplayService`
只读服务。

职责：
- 判断 replay 是否有 `pose_points`
- 加载 `frames.csv`
- 构造 `ReplayBundle`

## i18n

v2.12.73 起，界面文案从 Python 代码外置为 JSON：
- `planar_sketch/ui/locales/en.json`
- `planar_sketch/ui/locales/zh.json`

`ui/i18n.py` 只负责：
- 读取 locale 文件
- 规范语言代码
- `tr()` / `tr_ui()` helper

收益：
- 减少大文件冲突
- 更容易审校和 diff
- 便于做缺键检查

## 回归测试

`tests/` 目录目前覆盖：
- `CaseSpec` / `ReplayFrame` / `RunRecord` round-trip
- case current run 与 `_last` 分离
- replay bundle 读取
- 外置 locale 文件加载

后续建议继续补：
- 普通 run 不覆盖 saved case
- 拓扑变更清空 run
- replay 不污染 live model
- evaluate / synthesis / load force 的 smoke tests

## 开发约束

1. **关键落盘路径不能兜底猜测**
   - case rerun 必须显式绑定 `case_name`
   - 普通 run 不得回退写 active case

2. **replay 只读**
   - 不得把 replay 作为普通 run 的隐式输入源

3. **服务统一入口**
   - UI 不要重复拼 project dir
   - UI 不要自己 new `CaseRunManager`

4. **兼容阶段允许 dict + dataclass 共存**
   - 新代码优先使用 dataclass
   - 老代码继续可传 dict
   - 过渡期通过 `ensure_*` helper 做兼容

## 下一步建议

- 继续将 `AnimationTab` 中的 replay 解析逻辑下沉到 `ReplayService`
- 继续合并 `controller_simulation.py` 与 `headless_sim.py` 的准静态公共逻辑
- 补 UI 层 smoke tests
