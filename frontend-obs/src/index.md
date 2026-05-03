---
title: 본 라운드 — N=1,000 박물관 관람료 무료화
toc: true
---

# knowing-koreans · 한국인 페르소나 시뮬레이터

```js
const round = await FileAttachment("./data/round1.json").json();
const meta = round.meta;
const fmt = new Intl.NumberFormat("ko-KR");
```

<div class="lede">
국립중앙박물관 상설 전시 관람료 유료화 시나리오에 한국 인구통계 분포 합성 페르소나 1,000명을 던진 결과입니다.
<strong>N=${fmt.format(meta.n_total)}</strong> 시뮬 → JSON 응답 성공 <strong>${fmt.format(meta.n_ok)}건</strong> → schema 정의 텍스트가 응답값으로 그대로 회신된 <strong>${fmt.format(meta.n_schema_echo)}건</strong>을 제외한 <span class="valid-n-callout">valid ${fmt.format(meta.valid_n)}건</span>이 본 분포·교차분석의 통계 베이스입니다.
</div>

```js
const formatTs = (s) => (s ? s.replace("T", " ").slice(0, 19) : "-");
const startedAt = formatTs(meta.started_at);
const finishedAt = formatTs(meta.finished_at);
const modelShort = (meta.models || [])
  .map((m) => m.replace("openrouter/", "").replace("nousresearch/", ""))
  .join(", ");
```

<div class="metrics-row">
  <div class="metric-card">
    <div class="metric-label">응답 성공</div>
    <div class="metric-value">${fmt.format(meta.n_ok)} / ${fmt.format(meta.n_total)}</div>
    <div class="metric-sub">실패 ${fmt.format(meta.n_fail)}건</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">통계 베이스</div>
    <div class="metric-value">valid ${fmt.format(meta.valid_n)}</div>
    <div class="metric-sub">schema echo ${fmt.format(meta.n_schema_echo)}건 제외</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">평균 응답 시간</div>
    <div class="metric-value">${meta.avg_sec_per_call.toFixed(1)}초</div>
    <div class="metric-sub">호출당</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">보고서 합성 모드</div>
    <div class="metric-value">모드 ${meta.insight_mode}</div>
    <div class="metric-sub">${meta.insight_n_clusters}개 cluster 합성</div>
  </div>
</div>

<div class="muted">
  <strong>측정 시작</strong> ${startedAt} · <strong>측정 완료</strong> ${finishedAt}<br>
  <strong>측정 모델</strong> ${modelShort || "-"} · <strong>페르소나 시드</strong> ${meta.seed ?? "-"}<br>
  <strong>질문 생성</strong> ${(meta.qgen_model || "").replace("openrouter/", "")} · <strong>인사이트 합성</strong> ${(meta.report_model || "").replace("openrouter/", "")}
</div>

<details class="scenario-spec">
  <summary>📋 시나리오 기획안 — 주제·맥락·질문지·응답 schema</summary>

```js
const spec = round.spec;
```

**주제 (찬성·반대 논거 포함)**

<div style="white-space: pre-wrap;">${spec.topic}</div>

---

**페르소나 주입 맥락**

<div style="white-space: pre-wrap;">${spec.ctx}</div>

---

**질문지**

<div style="white-space: pre-wrap;">${spec.questions}</div>

---

**응답 schema (JSON)**

<pre>${spec.schema_block}</pre>

</details>

---

## ① 핵심 분포 — 질문별 응답 빈도

<div class="muted">아래 차트는 valid ${fmt.format(meta.valid_n)}건 기준입니다. Q1~Q3은 같은 1~5 Likert를 100% 누적 막대로 한 차트에 묶어 비교, Q4는 지불 의향 lollipop, Q5는 자유서술 키워드 lollipop (한 응답이 복수 키워드에 동시 매칭).</div>

```js
const likertColor = {
  type: "categorical",
  domain: [
    "1 매우 반대",
    "2 반대",
    "3 중립",
    "4 찬성",
    "5 매우 찬성",
  ],
  range: ["#b32424", "#d97706", "#9ca3af", "#65a30d", "#1f6feb"],
  legend: true,
  label: "Likert 응답 (Q1·Q2·Q3 공통 색상)",
};

const likertLabel = (v) => `${v} ${["매우 반대","반대","중립","찬성","매우 찬성"][v-1]}`;

const likertCombined = [];
for (const [qKey, dist, qLabel] of [
  ["q1", round.distributions.q1, "Q1 입장료 도입 찬반"],
  ["q2", round.distributions.q2, "Q2 대안 재원 우선 시도"],
  ["q3", round.distributions.q3, "Q3 취약계층 면제 시 변화"],
]) {
  const total = d3.sum(dist, (d) => d.count);
  let cum = 0;
  for (const d of dist) {
    const pct = total ? d.count / total : 0;
    likertCombined.push({
      question: qLabel,
      value: d.value,
      level: likertLabel(d.value),
      count: d.count,
      pct,
      x_mid: cum + pct / 2,
    });
    cum += pct;
  }
}
```

<div class="card">${Plot.plot({
  title: "Q1·Q2·Q3 — 100% 누적 막대 (Likert 1~5)",
  caption: "각 질문에서 응답 5단계가 valid 응답 안에서 차지하는 비율. 막대 안 라벨은 비율(%).",
  height: 220,
  marginLeft: 200,
  marginRight: 40,
  x: {percent: true, label: "비율 (%)", grid: true},
  y: {label: null},
  color: likertColor,
  marks: [
    Plot.barX(likertCombined, {
      y: "question",
      x: "pct",
      fill: "level",
      tip: true,
      title: (d) => `${d.question}\n${d.level}: ${d.count}건 (${(100*d.pct).toFixed(1)}%)`,
    }),
    Plot.text(likertCombined.filter((d) => d.pct >= 0.05), {
      y: "question",
      x: "x_mid",
      text: (d) => `${(100*d.pct).toFixed(0)}%`,
      fill: "white",
      fontSize: 11,
      fontWeight: 600,
    }),
  ],
})}</div>

```js
const q4Total = d3.sum(round.distributions.q4, (d) => d.count);
const q5Total = round.distributions.q5_topic_freq.reduce((a, b) => Math.max(a, b.count), 0);
```

<div class="grid grid-cols-2">
  <div class="card">${Plot.plot({
    title: "Q4. 지불 의향 금액 — lollipop",
    caption: "선 + 점 형태. 응답 수 0건 카테고리도 그대로 표시.",
    height: 280,
    marginLeft: 110,
    marginRight: 60,
    x: {grid: true, label: "응답 수", domain: [0, d3.max(round.distributions.q4, (d) => d.count) * 1.15]},
    y: {label: null, domain: round.distributions.q4.map((d) => d.label)},
    marks: [
      Plot.ruleY(round.distributions.q4, {
        x1: 0,
        x2: "count",
        y: "label",
        stroke: "#d97706",
        strokeWidth: 2,
      }),
      Plot.dot(round.distributions.q4, {
        x: "count",
        y: "label",
        fill: "#d97706",
        r: 6,
        tip: true,
        title: (d) => `${d.label}\n${d.count}건 (${(100*d.count/q4Total).toFixed(1)}%)`,
      }),
      Plot.text(round.distributions.q4, {
        y: "label",
        x: "count",
        text: (d) => `${d.count}`,
        dx: 10,
        textAnchor: "start",
        fontSize: 11,
        fontWeight: 600,
      }),
    ],
  })}</div>
  <div class="card">${Plot.plot({
    title: "Q5. 자유서술 키워드 빈도",
    caption: "한 응답이 복수 키워드에 매칭될 수 있어 합은 valid N을 초과 가능.",
    height: 280,
    marginLeft: 230,
    marginRight: 60,
    x: {grid: true, label: "매칭 응답 수"},
    y: {label: null, domain: round.distributions.q5_topic_freq.map((d) => d.label)},
    marks: [
      Plot.ruleY(round.distributions.q5_topic_freq, {
        x1: 0,
        x2: "count",
        y: "label",
        stroke: "#0ea5e9",
        strokeWidth: 2,
      }),
      Plot.dot(round.distributions.q5_topic_freq, {
        x: "count",
        y: "label",
        fill: "#0ea5e9",
        r: 6,
        tip: true,
        title: (d) => `${d.label}\n${d.count}건`,
      }),
      Plot.text(round.distributions.q5_topic_freq, {
        y: "label",
        x: "count",
        text: (d) => `${d.count}`,
        dx: 10,
        textAnchor: "start",
        fontSize: 11,
        fontWeight: 600,
      }),
    ],
  })}</div>
</div>

---

## ② 페르소나 속성 × Q1 (입장료 찬반) 교차분석

<div class="muted">페르소나 demographic 축별로 Q1 응답 분포가 어떻게 달라지는지를 <strong>100% 누적 막대(그룹 내 비율)</strong>로 표시합니다. 그룹명 옆 N은 그룹 표본 크기. 색상은 ① 섹션과 동일한 Likert 5단계.</div>

```js
const q1Color = {
  type: "categorical",
  domain: [
    "1 매우 반대",
    "2 반대",
    "3 중립",
    "4 찬성",
    "5 매우 찬성",
  ],
  range: ["#b32424", "#d97706", "#9ca3af", "#65a30d", "#1f6feb"],
  legend: true,
  label: "Q1 응답",
};

function groupTotalsMap(rows) {
  return d3.rollup(rows, (vs) => d3.sum(vs, (v) => v.count), (v) => v.group);
}

function crosstabChart({title, rows, height = 320, marginLeft = 150, sortByOpposition = false}) {
  if (!rows.length) return html`<div class="muted">데이터 없음</div>`;
  const totals = groupTotalsMap(rows);
  const enriched = [];
  const byGroup = d3.group(rows, (r) => r.group);
  for (const [g, list] of byGroup) {
    const total = totals.get(g) || 0;
    const sorted = [...list].sort((a, b) => a.q1 - b.q1);
    let cum = 0;
    for (const r of sorted) {
      const pct = total ? r.count / total : 0;
      enriched.push({
        ...r,
        level: likertLabel(r.q1),
        pct,
        x_mid: cum + pct / 2,
      });
      cum += pct;
    }
  }
  // 그룹 정렬: 반대(1+2) 비율 기준 내림차순 OR 표본 크기
  const oppositionPct = new Map();
  for (const [g, total] of totals) {
    const sub = rows.filter((r) => r.group === g);
    const opp = d3.sum(sub.filter((r) => r.q1 <= 2), (r) => r.count);
    oppositionPct.set(g, total ? opp / total : 0);
  }
  const groupOrder = sortByOpposition
    ? Array.from(totals.keys()).sort((a, b) => oppositionPct.get(b) - oppositionPct.get(a))
    : Array.from(totals.keys()).sort((a, b) => totals.get(b) - totals.get(a));
  const yLabel = (g) => `${g} (N=${totals.get(g) || 0})`;
  return Plot.plot({
    title,
    height,
    marginLeft,
    marginRight: 50,
    x: {percent: true, label: "그룹 내 비율 (%)", grid: true},
    y: {
      label: null,
      domain: groupOrder.map(yLabel),
    },
    color: q1Color,
    marks: [
      Plot.barX(enriched, {
        y: (d) => yLabel(d.group),
        x: "pct",
        fill: "level",
        tip: true,
        title: (d) => `${d.group} (N=${totals.get(d.group)})\n${d.level}: ${d.count}건 (${(100*d.pct).toFixed(1)}%)`,
      }),
      Plot.text(enriched.filter((d) => d.pct >= 0.08), {
        y: (d) => yLabel(d.group),
        x: "x_mid",
        text: (d) => `${(100*d.pct).toFixed(0)}`,
        fill: "white",
        fontSize: 10,
        fontWeight: 600,
      }),
    ],
  });
}
```

<div class="grid grid-cols-2">
  <div class="card">${crosstabChart({
    title: "연령대 (age_bucket) × Q1",
    rows: round.crosstabs.age,
    height: 260,
    sortByOpposition: true,
  })}</div>
  <div class="card">${crosstabChart({
    title: "성별 × Q1",
    rows: round.crosstabs.sex,
    height: 200,
  })}</div>
</div>

<div class="card">${crosstabChart({
  title: "지역 (province) × Q1 — 17개 시도, 표본 크기 정렬",
  rows: round.crosstabs.province,
  height: 480,
  marginLeft: 160,
})}</div>

<div class="grid grid-cols-2">
  <div class="card">${crosstabChart({
    title: "학력 (education_level) × Q1",
    rows: round.crosstabs.education,
    height: 280,
    marginLeft: 180,
  })}</div>
  <div class="card">${crosstabChart({
    title: "직업 top 12 × Q1",
    rows: round.crosstabs.occupation,
    height: 400,
    marginLeft: 200,
  })}</div>
</div>

---

## ③ 발견 패턴 — key findings

<div class="muted">보고서 합성 LLM이 valid ${fmt.format(meta.valid_n)}건 응답 + ${fmt.format(meta.insight_n_clusters)}개 cluster 분석 + cross-cluster diff + synthesis 합성 5단계로 도출한 패턴입니다.</div>

```js
const findings = round.insight.key_findings;
```

<div>
${findings.map((f) => html`
  <div class="finding-card">
    <div class="finding-label">${f.label}</div>
    <div>${f.content}</div>
  </div>
`)}
</div>

---

## ④ 곱씹을 만한 응답 — 인용 + 큐레이터 노트

<div class="muted">${fmt.format(meta.valid_n)}건 응답 중 큐레이터에게 의미 있는 인용을 골라 큐레이션 활용 노트와 함께 정리한 카드입니다.</div>

```js
const quotes = round.insight.responses_to_chew_on;
```

<div>
${quotes.map((q) => html`
  <div class="quote-card">
    <div class="muted"><strong>${q.persona_attrs}</strong> · 모델: <code>${q.model}</code></div>
    <blockquote>${q.quote}</blockquote>
    <div class="curator-note">📝 <strong>큐레이터 노트</strong> — ${q.curator_note}</div>
  </div>
`)}
</div>

---

## ⑤ 응답 카드 — Q1 분포 6건씩 샘플

```js
const sampleByQ1 = (() => {
  const c = {};
  for (const r of round.sample_responses) c[r.q1] = (c[r.q1] || 0) + 1;
  return c;
})();
const sampleSummary = [1, 2, 3, 4, 5].map((v) => `Q1=${v} ${sampleByQ1[v] || 0}건`).join(" · ");
```

<div class="muted">Q1 (입장료 찬반) 1~5 각 구간에서 valid 응답 최대 6건씩 시드 고정 샘플로 표시합니다. 본 라운드에서는 ${sampleSummary} (Q1=5 매우 찬성은 valid 응답 0건). 자유서술은 240자에서 잘립니다.</div>

```js
const responses = round.sample_responses;

const filterQ1 = view(
  Inputs.checkbox(
    [1, 2, 3, 4, 5],
    {
      label: "Q1 응답 필터",
      value: [1, 2, 3, 4, 5],
      format: (v) => `${v} ${["매우 반대", "반대", "중립", "찬성", "매우 찬성"][v - 1]}`,
    }
  )
);
```

```js
const filtered = responses.filter((r) => filterQ1.includes(r.q1));
```

<div>
${filtered.map((r) => html`
  <div class="response-card">
    <div class="badge-col">
      <span class="q1-badge q1-${r.q1}">${r.q1}</span>
      <span class="q1-label">Q1</span>
      <span class="muted">Q2 ${r.q2} · Q3 ${r.q3}</span>
    </div>
    <div>
      <div class="persona-attrs">
        ${[r.age ? r.age + "세" : "", r.sex, r.province, r.education_level, r.occupation, r.marital_status]
          .filter((x) => x)
          .join(" · ")}
      </div>
      <p class="persona-quote">${r.q5}</p>
      <div class="response-meta">지불 의향: <code>${r.q4 || "-"}</code></div>
    </div>
  </div>
`)}
</div>

<div class="muted">필터 결과 ${filtered.length} / 30건 표시</div>

---

## ⑥ 큐레이터 가설 — curator hypotheses

<div class="muted">발견 패턴을 큐레이터 도메인 어조로 옮긴 가설 후보입니다. 타깃 그룹·전달 형식·메시지 본문 세 차원으로 정리됩니다.</div>

```js
const hypotheses = round.insight.curator_hypotheses;
```

<div>
${hypotheses.map((h, i) => html`
  <div class="hypothesis-card">
    <div class="hypothesis-meta">
      <strong>가설 ${String(i + 1).padStart(2, "0")}</strong> · 타깃: <code>${h.target_group}</code> · 전달 형식: <code>${h.form}</code>
    </div>
    <div>${h.content}</div>
  </div>
`)}
</div>

---

## ⑦ 다음에 던져볼 질문 — next questions

<div class="muted">본 라운드에서 잡힌 약신호와 모델 편향 의심 패턴을 후속 시나리오 질문으로 옮긴 큐레이터용 work item입니다.</div>

```js
const nextQs = round.insight.next_questions;
```

<div>
${nextQs.map((q, i) => html`
  <div class="next-question"><strong>Q${String(i + 1).padStart(2, "0")}</strong> — ${q}</div>
`)}
</div>

---

<div class="muted">
⚙ knowing-koreans · <strong>v0.3.0</strong> · 2026-05-03 · 데이터: NVIDIA Nemotron-Personas-Korea (CC BY 4.0) · OpenRouter 경유 다중 LLM · Observable Framework 정적 호스팅
</div>
