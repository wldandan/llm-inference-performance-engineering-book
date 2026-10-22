# 图 8-3 制作说明：一次 RAG 调用的 Trace 树

- 来源段落：第 8.4 节。
- 阅读顺序：先看顶部总计 2400 ms 的括号，再从上到下读四个一级 span，最后展开 llm-call 里那三段，注意被标红的 queue。
- 关键结论：只看总时长 2400 ms 得不出“在排队”这个结论。
- 表达边界：不把 scheduled-to-first-token 写成 TTFT；不暗示 span 边界天然可信。
