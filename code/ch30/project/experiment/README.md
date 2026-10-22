# experiment/

对应阶段四到阶段六（Ch11–Ch25）。verify.py 从这个目录读 `experiment/rounds.json`。

- 每轮六个字段：预期、唯一改动、主指标、护栏、判定、边界。八条自查里有四条查的是这里。
- `changed` 只能有一项。多于一项时那一轮的结论不可用，verify.py 按失败处理。
- 动了精度的轮次必须有 `quality`，且 `floor` 要标 `decided_before_run`。
- 允许并且鼓励出现“在当前实验精度下不可分辨”。三轮以上全是明确结论时 verify.py 会告警。
- 报告生成用 `code/ch14/prefill_experiment.py`、`code/ch19/decode_experiment.py`、`code/ch25/e2e_experiment.py`，三者共用同一套四种结论。

`samples/sample-pass/experiment/rounds.json` 是一份填好的例子，`samples/sample-incomplete/` 里的同名文件是它“差一点”的版本。
