# capacity/

对应阶段七（Ch26–Ch29）。verify.py 从这个目录读 `capacity/capacity.json`。

- 卡数推导、余量构成、实际单位成本（分母是有用的产出）、假设分析。用 `code/ch26/capacity_cost.py`。
- `binding_constraint` 写明哪个约束先满（`memory` 或 `throughput`）。上下文变了之后怎么折算成卡数取决于它，见 29.7。
- `context_tokens` 要和 workload 那边一致。这两个数不一致就是 29.8 案例一。
- `instances` 是峰值卡数，`floor_instances` 是下限卡数（第 26 章 Demo 的 `gpus_floor`）。接缝之四核对两个不等式：`max_instances ≥ instances`，`min_instances ≥ floor_instances`。
- 扩缩容的边界说明用 `code/ch27/autoscale_sim.py`，尤其是那张回路滞后表。

`samples/sample-pass/capacity/capacity.json` 是一份填好的例子，`samples/sample-incomplete/` 里的同名文件是它“差一点”的版本。
