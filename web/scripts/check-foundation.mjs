import { readFile } from "node:fs/promises";

const packageUrl = new URL("../package.json", import.meta.url);
const manifest = JSON.parse(await readFile(packageUrl, "utf8"));
const [nodeMajor, nodeMinor] = process.versions.node.split(".").map(Number);

if (nodeMajor !== 24 || nodeMinor < 14) {
  throw new Error(
    `需要 Node.js 24.14.x，当前为 ${process.versions.node}；请按根目录 .nvmrc 切换版本`,
  );
}

if (manifest.private !== true) {
  throw new Error("web/package.json 必须声明 private=true");
}

if (!manifest.engines?.node || !manifest.packageManager) {
  throw new Error("Web 工作区必须固定 Node.js 与 pnpm 边界");
}

console.log("Web 工程边界检查通过；当前没有安装或运行 Web 业务依赖。");
