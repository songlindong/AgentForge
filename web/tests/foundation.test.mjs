import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("Web 工作区保持私有且没有业务依赖", async () => {
  const packageUrl = new URL("../package.json", import.meta.url);
  const manifest = JSON.parse(await readFile(packageUrl, "utf8"));

  assert.equal(manifest.private, true);
  assert.deepEqual(manifest.dependencies ?? {}, {});
  assert.deepEqual(manifest.devDependencies ?? {}, {});
});

