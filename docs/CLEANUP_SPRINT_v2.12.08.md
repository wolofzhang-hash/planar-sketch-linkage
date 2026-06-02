# Cleanup Sprint v2.12.08

本轮为 UI 与 i18n 收尾冲刺（用于 GitHub 上传前整理）。

## 目标
- 只保留 zh/en 双语分支
- 统一表格右键菜单入口（builder + dispatch）
- 删除历史 patch 残留与重复函数/分支
- 删除被右键取代的新增/删除按钮（真删除，不是 hide/None）
- 清理 UI 模块硬编码文案，统一走 `tr(...) / _tr(...)`

## 已完成
- `ui/table_context_menu.py`：右键菜单 builder/dispatch/install 统一入口；兼容别名收紧
- `ui/i18n.py`：语言函数收敛为 `norm_lang / ui_language / set_ui_language / get_ui_language`（zh/en only）
- `ui/tabs.py / ui/analysis_tabs.py / ui/sim_panel.py`：语言 helper 收敛到 `_lang/_tr`，减少散点调用
- `ui/sim_panel.py`：载荷/摩擦/测量新增/删除按钮对象/布局/连接/apply_language 分支删除，仅保留右键入口
- `ui/tabs.py / ui/analysis_tabs.py`：草图表与优化表新增/删除按钮入口移除，右键接管
- 多个 UI 模块提示框/右键项/窗口标题硬编码文案改为 i18n 键

## 上传 GitHub 前建议
- 用全新目录解压完整代码包后再运行一次（避免旧文件覆盖）
- 检查 `.gitignore` 是否覆盖本地生成物（zip/csv/svg/log/gif/png 等）
- 提交前运行最小自检（至少 `py_compile` 或直接启动主界面）
