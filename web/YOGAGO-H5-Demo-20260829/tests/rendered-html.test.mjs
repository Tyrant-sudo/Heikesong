import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the YOGAGO product shell and metadata", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>伽伽狗｜你的具身智能瑜伽搭子<\/title>/);
  assert.match(html, /property="og:title" content="伽伽狗｜你的具身智能瑜伽搭子"/);
  assert.match(
    html,
    /property="og:image" content="http:\/\/localhost(?::\d+)?\/og-yogago\.jpg"/,
  );
  assert.match(
    html,
    /<iframe class="demo-frame" src="\/demo\.html" title="伽伽狗 YOGAGO 手机端 H5 交互原型"><\/iframe>/,
  );
  assert.doesNotMatch(html, /codex-preview|Building your site|react-loading-skeleton/i);
});

test("ships the interactive yoga companion experience and required assets", async () => {
  const demo = await readFile(new URL("../public/demo.html", import.meta.url), "utf8");

  assert.match(demo, /aria-label="伽伽狗 YOGAGO 瑜伽陪伴 H5"/);
  assert.match(demo, /id="emergency"/);
  assert.match(demo, /紧急停止伽伽狗移动/);
  assert.match(demo, /让伽伽狗开始陪练/);
  assert.match(demo, /查看本次瑜伽日记/);
  assert.match(demo, /querySelector\('#emergency'\)\.addEventListener/);
  assert.match(demo, /querySelectorAll\('\.screen-link'\)/);

  await Promise.all([
    access(new URL("../public/demo.css", import.meta.url)),
    access(new URL("../public/yogago-logo.png", import.meta.url)),
    access(new URL("../public/yogago-dog.jpg", import.meta.url)),
    access(new URL("../public/yoga-capture-woman-v1.jpg", import.meta.url)),
    access(new URL("../public/og-yogago.jpg", import.meta.url)),
  ]);
});
