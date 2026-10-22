# 图 3-2 制作说明：Chat Template、Tokenizer 与 Embedding

- 来源段落：第 3 章“3.2 Chat Template、Tokenizer 与 Embedding”。
- 阅读顺序：先沿上排从 messages 向右读到 N × Blocks，再看中间两道括线分出的服务进程与模型，最后看下方那张词表连到哪几处。
- 关键结论：前两道只改格式，第三道已经是模型；换模型时三样要一起换，因为它们共用一张词表。
- 边界：卡片下方的实例取自第 1 章那次请求（30 个 token、hidden size 896），控制标记按 Qwen2.5 的 ChatML 写法示意，不代表任何模型的完整模板；不出现性能数字。
