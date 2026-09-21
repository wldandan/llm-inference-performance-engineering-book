# V0.1 发布前代码审查

日期：2026-09-21。范围仅本工具新增文件，不包含教材原有未提交修改。
以 `docs/sprints/v0.1.md` 的 F01—F14 为验收依据；没有 PR，不适用 PR 质量轴。

主任务使用代码审查、安全审查、可维护性与实现验证技能，阅读实际实现和对应测试。
语言规范 resolver 对 Python、JavaScript、CSS 均返回通用最佳实践；风格由 Ruff 与 JS 语法检查验证。
独立审查者 Maxwell 复核执行核心，详细结论见 `workflow-integration-validation.md`。

## 已修复的问题

| 严重度 / 轴 | 问题 | 修复及可复现验证 |
| --- | --- | --- |
| blocking / functionality | 缺失 usage 导致 EvalScope 累计器抛错，后续请求未完成 | canonical JSON 保留 null；仅上游内部诊断兼容数值累计器，工作台不消费该诊断。真实 NOUSAGE 后续请求测试通过。 |
| blocking / functionality | HTTP 200 仅凭 finish_reason 将畸形 message 判为成功 | 校验 message/delta 与内容结构；非法 finish 类型安全失败；worker 边界测试覆盖。 |
| blocking / functionality | 预检绕过正在执行实验的互斥 | 同一管理器及跨进程文件锁共同约束预检/提交；禁止交叉污染测量。 |
| important / security | 响应超限后 JSON→text 回退获得新额度 | 字节累计与失败状态持续生效，超限关闭连接；重复读取测试通过。 |
| important / security | 密钥可能残留在字典键或上游异常日志 | 递归脱敏键和值；请求期间在 EvalScope 日志处理前过滤注入密钥。嵌套键与异常日志 canary 测试通过。 |
| important / functionality | 小数秒超时向上取整 | 保留上游整数字段兼容性，外层异步时限严格采用原值；真实 50 ms 超时测试通过。 |
| important / functionality | 中断耗时依赖墙上时钟 | 保存单调时钟锚点；缺锚点不填造耗时；时钟跳变回归通过。 |
| important / functionality | 控制器退出后子进程可能继续运行 | worker 导入重依赖前启动父 PID 看护，父进程消失后终止自身；子进程验证通过。 |
| important / performance | 每次进度刷新重读增长的完整响应文件 | 增量计数完整 JSONL 行；进度仅刷新 manifest，计数不变时不写盘。 |
| important / functionality | 创建计划失败后文件锁未释放 | 创建失败关闭锁描述符；磁盘写入失败边界回归通过。 |
| important / functionality | CLI 与网页复测持久化结构不一致 | 两者统一保存状态、基线/候选 ID、判定条件与差异；跨入口回归通过。 |
| important / functionality | 报告将 TPOT 与请求时延写成相同单位 | 时延表增加单位列：TPOT 为 ms/token，其他时延为 ms；导出回归通过。 |

每项生产修复之前均运行对应失败测试；证据汇总见 `validation.md`。
独立核心复审结论：APPROVED for the reviewed fixes；不是硬件性能或全平台安全认证。

## 文件 × 审查轴覆盖

✓ 表示已阅读实现并结合测试逐项检查，不表示不存在任何潜在缺陷。
安全检查包含输入、凭据、路径、命令、HTML、同源、请求预算与本地隐私边界；未使用数据库。

| 文件 | 功能 | 测试 | 性能 | 安全 | 可维护性 | 风格 | PR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| config.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| dataset.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| store.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| runner.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| evalscope_worker.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| telemetry.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| analysis.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| sweep.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| report.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| cli.py / __main__.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| demo.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| web.py | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| static/app.js | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| static/index.html / style.css | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| __init__.py | ✓ | n/a：版本常量 | n/a | ✓ | ✓ | ✓ | n/a |

## 保留的限制与非阻断建议

- 单用户本地工具，不具备公网或多租户权限隔离。没有公网鉴权不作为此范围内的缺陷；公开部署必须重新设计与审查。
- 高请求量下的网页全量记录加载、实验清理与磁盘配额尚未做规模化验证。首次真机实验使用小数据集和有限预算，不把配置允许的上限当作验证过的能力。
- 本地质量规则只检查声明条件，不能证明模型事实正确；模型选择与容量必须基于真实业务质量标准。
- 默认导出对自由文本采取严格脱敏：模型/环境用指纹关联，类别用别名。需要原始名称时在私有本地快照中核对。
- 已检查凭据 canary 与代码边界，但没有运行第三方依赖漏洞数据库审计，不宣称依赖零漏洞。
- 两条 Starlette/TestClient 与 AnyIO 的弃用警告已保留记录，不影响本轮测试结果。
- 仓库未提供 graphify 索引；尝试 `graphify update .` 返回 command not found。没有自行安装或修改仓库图索引。
