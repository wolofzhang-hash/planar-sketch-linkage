# 六连杆综合目标模板（仅定义问题，不含几何）

本包新增 4 个六连杆目标模板 JSON，位于：
`seed_user_home/.planar_sketch/intel_templates/`

文件：
- `sixbar_watt1_2pos.json`：六连杆-Watt I-2位置综合（base_topology_id=6bar_watt1）
- `sixbar_watt1_3pos.json`：六连杆-Watt I-3位置综合（base_topology_id=6bar_watt1）
- `sixbar_stephenson1_2pos.json`：六连杆-Stephenson I-2位置综合（base_topology_id=6bar_stephenson1）
- `sixbar_stephenson1_3pos.json`：六连杆-Stephenson I-3位置综合（base_topology_id=6bar_stephenson1）

这些模板用于后续在程序中扩展“目标曲线类型/综合问题”时直接复用；当前版本若程序只通过 index.json 列出模板，需要你把相应条目加入 index.json。
