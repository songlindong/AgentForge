# Generators

生成器实现在 `harness/agentforge_harness/generators.py`。相同参数和 Seed 必须产生字节一致的 JSONL；向量逐行生成，不在内存中保存全集，也不会写入 Milvus。

默认命令只生成小样本。100 万向量必须通过显式 `--count 1000000` 请求，输出目录应放在已忽略的 `tmp/` 或 `reports/`，不能提交生成的大文件。
