// See https://observablehq.com/framework/config for documentation.
//
// 빌드 시점에 KK_RUN_DIR 환경변수가 가리키는 spec.json 을 읽어
// 페이지 라벨을 시나리오에 맞게 갱신한다. 미지정 시 generic 라벨.
import {readFileSync, existsSync} from "node:fs";
import {join} from "node:path";

const runDir = process.env.KK_RUN_DIR || "";
let pageName = "본 라운드 결과";
if (runDir) {
  try {
    const specPath = join(runDir, "spec.json");
    if (existsSync(specPath)) {
      const spec = JSON.parse(readFileSync(specPath, "utf-8"));
      const topic = (spec.topic || "").split(/\n/)[0].slice(0, 50);
      const n = spec.n || 0;
      pageName = topic ? `N=${n} · ${topic}` : `N=${n}`;
    }
  } catch (e) {
    // ignore — fallback to generic
  }
}

export default {
  title: "knowing-koreans · 한국인 페르소나 시뮬레이터",
  root: "src",
  output: "dist",
  pages: [
    {
      name: pageName,
      path: "/"
    }
  ],
  theme: ["air", "near-midnight"],
  header: "",
  footer: "",
  sidebar: false,
  toc: false,
  pager: false,
  search: false,
  style: "style.css"
};
