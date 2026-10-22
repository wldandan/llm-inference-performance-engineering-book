# observe/

对应阶段三（Ch8–Ch10）。verify.py 从这个目录读 `observe/capabilities.json`。

- `request_id_propagated` 和 `drilldown_supported` 两项决定“可观测”这项交付物算不算成立。
- `unavailable_stages` 是这份文件里最重要的一项。第 1 章那条纪律：拿不到的阶段写 unavailable，不写 0。
- verify.py 的第一条自查就是拿这份清单去报告里搜有没有对应的 0。
- 追踪与根因用 `code/ch08/trace_one_request.py` 和 `code/ch10/rca_report.py`。

`samples/sample-pass/observe/capabilities.json` 是一份填好的例子，`samples/sample-incomplete/` 里的同名文件是它“差一点”的版本。
