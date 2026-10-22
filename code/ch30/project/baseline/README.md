# baseline/

对应阶段二（Ch6–Ch7）。verify.py 从这个目录读 `baseline/baseline.json`。

- 四块字段齐全、重复轮次、波动数据、环境指纹。
- 用 `code/ch07/run_baseline.py` 采集。它要求至少重复三轮，因为单轮没有波动数据。
- `framework_version` 会和报告里系统说明那一栏对照，接缝之三。
- 波动数据不是附加项：第 28 章的阈值要从变异系数推出来，没有它门禁只能靠猜。

`samples/sample-pass/baseline/baseline.json` 是一份填好的例子，`samples/sample-incomplete/` 里的同名文件是它“差一点”的版本。
