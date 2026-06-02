# Planar Sketch v2.12.73 patch notes

本次直接在源码上完成并验证的修改：

1. 修复 `loads` 序列化字段不全：保存工程时现在会完整写出 `fx_expr/fy_expr/mz_expr/ref_pid/k/theta0/load/k_expr/load_expr`。
2. 修复 `save_current_run()`：`runs/<case>/current/case.json` 现在记录本次实际执行的 case spec，而不是优先写旧的 stored case。
3. 统一参数表达式函数白名单：新增 `expression_registry.py`，UI 和后端共享同一套函数定义，补齐 `sinh/cosh/tanh/exp/log/log10/floor/ceil/round`。
4. 用户曲线项目化：用户曲线现在会随项目保存/打开而持久化；`New Project` 仍会清空它们。
5. case 收口为“稳定 id + 可编辑 display name”：
   - 新 case 内部 id 改为 `case_001` 这类稳定字符串
   - 默认显示名仍保持 `1/2/3`
   - 重命名现在只改 display name，不再改内部 id 和路径
6. 统一版本常量：新增 `planar_sketch/version.py`，窗口标题与项目 schema 版本统一。
7. 关键 run 持久化路径不再静默吞异常，失败时会弹出错误提示。
8. 补了测试，当前 `PYTHONPATH=. pytest -q` 通过，11 项测试全部通过。

## Hotfix
- Fixed missing `APP_VERSION` import in `planar_sketch/ui/main_window.py` causing startup NameError.
