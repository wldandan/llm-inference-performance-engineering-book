# gate/

对应阶段七（Ch26–Ch29）。verify.py 从这个目录读 `gate/gate.json`。

- 阈值、阈值依据、断言清单、基线更新规则，四项都要有。用 `code/ch28/perf_gate.py`。
- `threshold_basis` 不能空着。阈值至少是变异系数的两倍，这句话要能从这一栏里读出来。
- `assertions` 为空时“有门禁”这项交付物不成立：一次没有断言的门禁运行只是在量，不是在守。
- `batch` 和 `absolute_ttft_p95_ms` 参与接缝之二和之五。

`samples/sample-pass/gate/gate.json` 是一份填好的例子，`samples/sample-incomplete/` 里的同名文件是它“差一点”的版本。
