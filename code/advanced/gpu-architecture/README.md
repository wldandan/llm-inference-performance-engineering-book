# 附录 A Demo：GPU 约束预算器

这个 Demo 只依赖 Python 标准库。它根据手工输入的模型、上下文和硬件规格，计算：

- 权重、KV Cache、工作区与安全余量的显存容量预算；
- 算力、显存带宽和 Kernel Launch 的理论时间下界；
- 当前输入假设下最值得先验证的一类约束。

从 Git 仓库根目录运行：

```bash
python3 code/advanced/gpu-architecture/gpu_model.py
```

保存 JSON 报告：

```bash
python3 code/advanced/gpu-architecture/gpu_model.py --output gpu-constraint-report.json
```

报告模式固定为 `synthetic_gpu_mental_model`。这些结果来自公式和输入假设，不是 Benchmark，也没有探测真实 GPU。后续要确认瓶颈，仍需用第 8～11 章的方法采集真实 workload、服务指标和 Profiling 证据。

## 测试

```bash
python3 -m unittest discover -s code/advanced/gpu-architecture -p 'test_*.py'
```
