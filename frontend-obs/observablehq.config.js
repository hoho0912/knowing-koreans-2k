// See https://observablehq.com/framework/config for documentation.
export default {
  title: "knowing-koreans · 한국인 페르소나 시뮬레이터",
  root: "src",
  output: "dist",
  pages: [
    {
      name: "본 라운드 — N=1,000 박물관 관람료 무료화",
      path: "/"
    }
  ],
  theme: ["air", "near-midnight"],
  header: "",
  footer:
    "knowing-koreans · 데이터: NVIDIA Nemotron-Personas-Korea (CC BY 4.0) · OpenRouter 경유 다중 LLM",
  toc: true,
  pager: false,
  search: false,
  style: "style.css"
};
