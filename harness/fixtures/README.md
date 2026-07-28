# Fixtures

本目录保存虚构、合成的固定多模态、渠道和安全测试输入。禁止提交真实金融或个人数据。

- `catalog.json`：每个固定文件的类型、媒体类型、SHA-256 和安全样例预期。
- `documents/`：文本 PDF 与无文本层的扫描 PDF。
- `images/`：合同截图 PNG 与无 EXIF 的拍照页 JPEG。
- `tables/`、`messages/`：固定还款表格与 APP/H5 JSONL。
- `annotations/`：页码、区域坐标、来源对象和黄金问题。
- `security/`：无害的小文件、文本和资源超限元数据。

`build_fixtures.py` 使用固定字体和固定 PDF 元数据生成样例。生成后必须重新执行渲染检查和 `verify`，不能手工改样例后放宽哈希校验。
