# Document Processor

第 7 步已实现 PDF、扫描 PDF、PNG/JPEG 的安全检查、固定样例 OCR、
版面/阅读顺序、表格提取和金融条款切片。

核心文件：

- `security.py`：文件名、MIME/魔数、大小、页数、像素、解压比例、恶意文件扫描和图片元数据清理。
- `parser.py`：使用 `pypdf` 与 `pdfplumber` 解析原生 PDF；扫描件和图片通过 `OCRProviderPort`。
- `chunking.py`：按区域和表格来源生成确定性的 `chunk_uid`。
- `providers.py`：Local/Test 固定 OCR、Hash Embedding 和进程内解析边界。
- `ports.py`：OCR、Embedding、恶意文件扫描和文档沙箱接口。

Local/Test Provider 只用于证明流程、来源字段和存储结构，均标记
`test_model=true`。Production Profile 禁止这些 Provider；正式恶意文件扫描、
OCR/Embedding 和安全沙箱仍须在后续对应步骤完成。

单元验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/unit/document_processor -p "test_*.py" -v
```
