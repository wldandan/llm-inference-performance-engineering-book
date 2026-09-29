# Chapter 4 Demo：LLM Serving 架构契约检查器

这个 Demo 用一份 JSON 描述 LLM Serving 的逻辑组件、部署单元和组件间连线，然后检查请求路径与响应路径是否完整。它只使用 Python 标准库，不需要模型或 GPU。

Demo 检查的是架构职责，不是运行时健康状态。报告通过，表示图上的角色和交接关系自洽；它不代表服务已经部署，也不代表性能满足要求。

支持两种 profile：

- `single_instance`：最小路径为 Gateway → Scheduler → Worker → Runtime → Accelerator，不强制 Router 与 Admission；
- `scale_out`：增加 Router 与 Admission，适用于多副本选择和全局流量治理。

## 1. 运行环境

- Python 3.10 或更高版本
- 无第三方依赖
- Level 1：CPU / 无 GPU

## 2. 输入文件

`reference-architecture.json` 使用 `single_instance` profile，先展示最小可运行职责链。它包含三类信息：

- `components`：逻辑组件及其部署单元；
- `flows`：请求、响应、控制和遥测连线；
- `deployment_unit`：多个逻辑组件是否位于同一进程、服务或设备中。

参考架构的请求路径是：

```text
client -> gateway -> scheduler -> worker -> runtime -> accelerator
```

简化后的响应路径是：

```text
accelerator -> runtime -> worker -> gateway -> client
```

返回链路没有再次经过 Router、Admission 和 Engine Scheduler，因为它们通常不再做目标选择或执行准入。真实框架可能还有 Output Processor、Detokenizer 或消息总线；接入时可以扩展组件，但不要混淆逻辑责任。

## 3. 运行检查

从 Git 仓库根目录运行：

```bash
python3 code/ch04/architecture_contract.py \
  --input code/ch04/reference-architecture.json
```

保存报告：

```bash
python3 code/ch04/architecture_contract.py \
  --input code/ch04/reference-architecture.json \
  --output code/ch04/architecture-report.json
```

报告包含：

| 字段 | 含义 |
|---|---|
| `request_path` | 从 Client 到 Accelerator 的完整请求路径 |
| `response_path` | 从 Accelerator 返回 Client 的简化响应路径 |
| `deployment_units` | 逻辑组件与进程、服务或设备的部署关系 |
| `role_contracts` | Router、Admission、Scheduler 等角色的职责边界 |

完成最小路径后，再用 `scale-out-architecture.json` 运行同一检查器。第二份输入增加 Router 与 Admission，便于比较目标选择、全局准入和实例内调度的差异。

## 4. 制造一个错误

复制参考文件，删除下面这条请求连线：

```json
{"from": "scheduler", "to": "worker", "kind": "request"}
```

再次运行后，程序应拒绝该架构并报告缺少完整请求路径。你也可以尝试：

- 在 `scale_out` profile 下删除 `router` 角色；
- 写入重复的组件 ID；
- 把连线指向不存在的组件；
- 把 `kind` 改成未支持的值。

## 5. 单元测试

```bash
python3 -m unittest discover -s code/ch04 -p 'test_*.py'
```

15 项测试覆盖两种 profile、完整请求与响应路径、职责分离、部署单元、缺失角色、重复 ID、错误连线、JSON 读取、CLI 输出和报告保存。

## 6. 边界

- 这是一份教学用参考架构，不是特定框架的源码模型。
- 逻辑组件不等于独立进程；多个角色可以部署在同一个单元中。
- Demo 不连接真实服务，也不采集 TTFT、吞吐或 GPU 指标。
- 多副本在后续章节展开；多 GPU 和 PD Disaggregation 放在 Advanced。

## 7. 参考文档

4.6 节那段分层对照的出处，按层级排列：

服务平台层（发布、扩缩容、多模型治理）

- [Ray Serve Architecture](https://docs.ray.io/en/latest/serve/architecture.html)
- [KServe Concepts and Architecture](https://kserve.github.io/website/docs/concepts)

推理服务器层（协议入口、模型实例管理）

- [Triton Inference Server Architecture](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/architecture.html)
- [NVIDIA Dynamo Architecture](https://docs.nvidia.com/dynamo/dev/knowledge-base/concepts/architecture)

LLM 引擎层（KV Cache 调度、模型执行）

- [vLLM Architecture Overview](https://docs.vllm.ai/en/stable/design/arch_overview/)
- [TensorRT-LLM Executor API](https://nvidia.github.io/TensorRT-LLM/advanced/executor.html)
- [llama.cpp README](https://github.com/ggml-org/llama.cpp/blob/master/README.md)

引这些文档是为了确认各系统覆盖哪些层级，不是做功能或性能对比。文档会随版本变化，比较之前先确认版本。
