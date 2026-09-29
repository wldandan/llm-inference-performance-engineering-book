# Prefix Cache 实验记录

## 本次执行状态

- 日期：2026-09-08
- 状态：未执行真实 GPU benchmark
- 原因：当前验收主机为 Apple arm64，未安装 `vllm` CLI，且没有 `nvidia-smi`。
- 已完成：一键入口 dry-run、Shell 语法检查、报告/对比单元测试。

## Baseline

- 模型：`Qwen/Qwen2.5-7B-Instruct`
- 配置：`--no-enable-prefix-caching`
- 请求数：20
- 客户端并发：4
- 引擎 batch size：动态，不可从客户端观测
- 输入/输出长度：执行后由 `baseline.json` 的 `workload` 字段记录

## Optimized

- 模型：`Qwen/Qwen2.5-7B-Instruct`
- 配置：`--enable-prefix-caching`
- workload：与 baseline 完全相同

## 对比结果

真实性能结果：**暂无，不做收益结论**。

在 NVIDIA GPU 主机运行 `bash run_experiment.sh` 后，将生成：

- `baseline.json`：未优化数据。
- `optimized.json`：开启 Prefix Cache 的数据。
- `comparison.txt`：TTFT 与真实全局输出 TPS 的变化，并标记 better/worse。
- `*-server.log`：启动参数与失败诊断。

若实测没有改善 TTFT，保留原始 JSON 和日志，并把结果记录为“未观测到预期收益”，
不应删除或修改数据以迎合书稿预期。

