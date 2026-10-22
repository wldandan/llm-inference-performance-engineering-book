# workload/

对应阶段二（Ch6–Ch7）。verify.py 从这个目录读 `workload/workload.json`。

- 长度分布、到达模式、并发、SLO、随机种子、文件哈希，六项都要有。
- 直接用 `code/ch06/workload_builder.py` 生成，它会在缺随机种子或缺长度分布时拒绝出文件。
- `context_tokens` 这一项会被 verify.py 拿去和容量模型那边对照，是五处接缝的第一处。

`samples/sample-pass/workload/workload.json` 是一份填好的例子，`samples/sample-incomplete/` 里的同名文件是它“差一点”的版本。
