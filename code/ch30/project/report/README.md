# report/

对应贯穿全程（Ch30）。verify.py 从这个目录读 `report/report.json`。

- 30.3 那九块，一块不缺、一块不空。缺一块这份报告就不接收，这是契约和模板的区别。
- 第九块 `boundary` 要五项：模型、负载、硬件、配置、链路结构，另外列出没验证的场景。
- `system.startup_steps` 决定“可运行”这项交付物算不算成立。
- 上线评审材料用 `code/ch29/release_check.py packet` 生成，它和这份报告是两份东西：报告说这次做了什么，评审材料说凭什么可以上线。

`samples/sample-pass/report/report.json` 是一份填好的例子，`samples/sample-incomplete/` 里的同名文件是它“差一点”的版本。
