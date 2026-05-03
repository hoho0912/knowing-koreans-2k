---
toc: true
---

```js
const round = await FileAttachment("./data/scenario.json").json();
const meta = round.meta;
const fmt = new Intl.NumberFormat("ko-KR");
const questions = round.questions || [];
const distributions = round.distributions || {};
const crosstabs = round.crosstabs || {};
const primaryCol = round.primary_col;
const primaryMeta = crosstabs._meta || {};
const numericQs = questions.filter((q) => q.type_class === "numeric");
const categoricalQs = questions.filter((q) => q.type_class === "categorical");
const freetextQs = questions.filter(
  (q) =>
    q.type_class === "freetext" &&
    (distributions[q.col]?.data?.length || 0) > 0,
);
const topicShort = (round.spec.topic || "").split(/\n/)[0].slice(0, 60);
```

# knowing-koreans · 한국인 페르소나 시뮬레이터

## 본 라운드 — N=${fmt.format(meta.n_total)} · ${topicShort || "시나리오"}

<div class="lede">
한국 인구통계 분포 합성 페르소나 ${fmt.format(meta.n_total)}명에 시나리오를 던진 결과입니다.
<strong>JSON 응답 성공 ${fmt.format(meta.n_ok)}건</strong> → schema 정의 텍스트가 응답값으로 그대로 회신된 <strong>${fmt.format(meta.n_schema_echo)}건</strong>을 제외한 <span class="valid-n-callout">valid ${fmt.format(meta.valid_n)}건</span>이 본 분포·교차분석의 통계 베이스입니다.
</div>

```js
const formatTs = (s) => (s ? s.replace("T", " ").slice(0, 19) : "-");
const startedAt = formatTs(meta.started_at);
const finishedAt = formatTs(meta.finished_at);
const modelShort = (meta.models || [])
  .map((m) => m.replace("openrouter/", "").replace("nousresearch/", ""))
  .join(", ");
const filtersText = (() => {
  const f = meta.filters || {};
  const parts = [];
  if (f.province) parts.push(`지역=${f.province}`);
  if (f.sex) parts.push(`성별=${f.sex}`);
  if (f.age_min) parts.push(`age≥${f.age_min}`);
  if (f.age_max && f.age_max < 120) parts.push(`age≤${f.age_max}`);
  if (f.education_level) parts.push(`학력=${f.education_level}`);
  if (f.occupation) parts.push(`직업=${f.occupation}`);
  if (f.stratify_by) parts.push(`균등 추출=${f.stratify_by}`);
  return parts.length ? parts.join(" · ") : "(없음 — 무작위 샘플)";
})();
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
    <div class="metric-value">${meta.avg_sec_per_call ? meta.avg_sec_per_call.toFixed(1) : "-"}초</div>
    <div class="metric-sub">호출당</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">보고서 합성 모드</div>
    <div class="metric-value">${meta.insight_mode ? "모드 " + meta.insight_mode : "-"}</div>
    <div class="metric-sub">${meta.insight_n_clusters || 0}개 cluster 합성</div>
  </div>
</div>

<div class="muted">
  <strong>측정 시작</strong> ${startedAt} · <strong>측정 완료</strong> ${finishedAt}<br>
  <strong>측정 모델</strong> ${modelShort || "-"} · <strong>페르소나 시드</strong> ${meta.seed ?? "-"}<br>
  <strong>질문 생성</strong> ${(meta.qgen_model || "-").replace("openrouter/", "")} · <strong>인사이트 합성</strong> ${(meta.report_model || "-").replace("openrouter/", "")}<br>
  <strong>페르소나 필터</strong> ${filtersText}
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

<div class="muted">아래 차트는 valid ${fmt.format(meta.valid_n)}건 기준입니다. Likert 응답은 100% 누적 막대(scale 라벨은 차트별), 옵션 선택형은 lollipop, 자유서술은 키워드 매칭 빈도 lollipop (한 응답이 복수 키워드에 동시 매칭).</div>

```js
const likertColorRange = ["#b32424", "#d97706", "#9ca3af", "#65a30d", "#1f6feb"];

function numericLikertChart(q, dist) {
  const total = d3.sum(dist.data, (d) => d.count);
  const labels = q.likert_labels || dist.data.map((d) => String(d.value));
  const enriched = [];
  let cum = 0;
  for (const d of dist.data) {
    const pct = total ? d.count / total : 0;
    const labelText = labels[d.value - 1] || String(d.value);
    enriched.push({
      value: d.value,
      level: `${d.value} ${labelText}`,
      count: d.count,
      pct,
      x_mid: cum + pct / 2,
    });
    cum += pct;
  }
  const colorDomain = enriched.map((e) => e.level);
  return Plot.plot({
    title: `Q${q.q_num}. ${q.q_text}`,
    caption: q.scale_text || q.description || "",
    height: 150,
    marginLeft: 30,
    marginRight: 30,
    x: {percent: true, label: null, grid: true},
    y: {label: null},
    color: {
      type: "categorical",
      domain: colorDomain,
      range: likertColorRange.slice(0, colorDomain.length),
      legend: true,
      label: null,
    },
    marks: [
      Plot.barX(enriched, {
        y: () => "분포",
        x: "pct",
        fill: "level",
        tip: true,
        title: (d) =>
          `${d.level}: ${d.count}건 (${(100 * d.pct).toFixed(1)}%)`,
      }),
      Plot.text(
        enriched.filter((d) => d.pct >= 0.05),
        {
          y: () => "분포",
          x: "x_mid",
          text: (d) => `${(100 * d.pct).toFixed(0)}%`,
          fill: "white",
          fontSize: 11,
          fontWeight: 600,
        },
      ),
    ],
  });
}

function categoricalLollipop(q, dist, color = "#d97706") {
  const total = d3.sum(dist.data, (d) => d.count);
  if (!dist.data.length) return html`<div class="muted">데이터 없음</div>`;
  return Plot.plot({
    title: `Q${q.q_num}. ${q.q_text}`,
    caption: q.description || "",
    height: Math.max(200, 40 + dist.data.length * 36),
    marginLeft: 130,
    marginRight: 70,
    x: {
      grid: true,
      label: "응답 수",
      domain: [0, Math.max(1, d3.max(dist.data, (d) => d.count) * 1.15)],
    },
    y: {label: null, domain: dist.data.map((d) => d.label)},
    marks: [
      Plot.ruleY(dist.data, {
        x1: 0,
        x2: "count",
        y: "label",
        stroke: color,
        strokeWidth: 2,
      }),
      Plot.dot(dist.data, {
        x: "count",
        y: "label",
        fill: color,
        r: 6,
        tip: true,
        title: (d) =>
          `${d.label}\n${d.count}건 (${(100 * d.count / Math.max(total, 1)).toFixed(1)}%)`,
      }),
      Plot.text(dist.data, {
        y: "label",
        x: "count",
        text: (d) => `${d.count}`,
        dx: 10,
        textAnchor: "start",
        fontSize: 11,
        fontWeight: 600,
      }),
    ],
  });
}
```

<div class="grid grid-cols-2">
${numericQs.map(
  (q) => html`<div class="card">${numericLikertChart(q, distributions[q.col])}</div>`,
)}
</div>

<div class="grid grid-cols-2">
${categoricalQs.map(
  (q) => html`<div class="card">${categoricalLollipop(q, distributions[q.col], "#d97706")}</div>`,
)}
${freetextQs.map(
  (q) => html`<div class="card">${categoricalLollipop(q, distributions[q.col], "#0ea5e9")}</div>`,
)}
</div>

---

## ② 페르소나 속성 × 핵심 응답 교차분석

```js
const hasCrosstab = primaryCol && primaryMeta.labels;
```

${hasCrosstab ? html`<div class="muted">페르소나 demographic 축별로 <strong>Q${primaryMeta.primary_q_num}</strong>(${primaryMeta.primary_q_text}) 응답 분포가 어떻게 달라지는지를 <strong>100% 누적 막대(그룹 내 비율)</strong>로 표시합니다. 그룹명 옆 N은 그룹 표본 크기.</div>` : html`<div class="muted">numeric 응답이 없어 교차분석을 생략합니다.</div>`}

```js
function crosstabChart({title, rows, height = 320, marginLeft = 150, sortByOpposition = false}) {
  if (!rows || !rows.length) return html`<div class="muted">데이터 없음</div>`;
  const labels = primaryMeta.labels || ["1", "2", "3", "4", "5"];
  const range = primaryMeta.range || [1, 5];
  const valueLabel = (v) => `${v} ${labels[v - 1] || v}`;
  const colorDomain = [];
  for (let i = range[0]; i <= range[1]; i++) colorDomain.push(valueLabel(i));
  const colorRange = likertColorRange.slice(0, colorDomain.length);

  const totals = d3.rollup(
    rows,
    (vs) => d3.sum(vs, (v) => v.count),
    (v) => v.group,
  );
  const enriched = [];
  const byGroup = d3.group(rows, (r) => r.group);
  for (const [g, list] of byGroup) {
    const total = totals.get(g) || 0;
    const sorted = [...list].sort((a, b) => a.value - b.value);
    let cum = 0;
    for (const r of sorted) {
      const pct = total ? r.count / total : 0;
      enriched.push({
        ...r,
        level: valueLabel(r.value),
        pct,
        x_mid: cum + pct / 2,
      });
      cum += pct;
    }
  }
  const oppositionPct = new Map();
  const lowMax = Math.floor((range[0] + range[1]) / 2); // 중간값 미만이 "반대측"
  for (const [g, total] of totals) {
    const sub = rows.filter((r) => r.group === g);
    const opp = d3.sum(
      sub.filter((r) => r.value <= lowMax),
      (r) => r.count,
    );
    oppositionPct.set(g, total ? opp / total : 0);
  }
  const groupOrder = sortByOpposition
    ? Array.from(totals.keys()).sort(
        (a, b) => oppositionPct.get(b) - oppositionPct.get(a),
      )
    : Array.from(totals.keys()).sort(
        (a, b) => totals.get(b) - totals.get(a),
      );
  const yLabel = (g) => `${g} (N=${totals.get(g) || 0})`;
  return Plot.plot({
    title,
    height,
    marginLeft,
    marginRight: 50,
    x: {percent: true, label: "그룹 내 비율 (%)", grid: true},
    y: {label: null, domain: groupOrder.map(yLabel)},
    color: {
      type: "categorical",
      domain: colorDomain,
      range: colorRange,
      legend: true,
      label: `Q${primaryMeta.primary_q_num} 응답`,
    },
    marks: [
      Plot.barX(enriched, {
        y: (d) => yLabel(d.group),
        x: "pct",
        fill: "level",
        tip: true,
        title: (d) =>
          `${d.group} (N=${totals.get(d.group)})\n${d.level}: ${d.count}건 (${(100 * d.pct).toFixed(1)}%)`,
      }),
      Plot.text(
        enriched.filter((d) => d.pct >= 0.08),
        {
          y: (d) => yLabel(d.group),
          x: "x_mid",
          text: (d) => `${(100 * d.pct).toFixed(0)}`,
          fill: "white",
          fontSize: 10,
          fontWeight: 600,
        },
      ),
    ],
  });
}

const axisOrder = [
  {key: "age", label: "연령대 (age_bucket)", h: 260, ml: 150, sortByOpposition: true},
  {key: "sex", label: "성별", h: 200, ml: 130, sortByOpposition: false},
  {key: "region", label: "수도권/광역시/그 외", h: 220, ml: 150, sortByOpposition: true},
  {key: "education", label: "학력 (education_level)", h: 280, ml: 180, sortByOpposition: true},
  {key: "province", label: "지역 17개 시도", h: 480, ml: 160, sortByOpposition: false},
  {key: "occupation", label: "직업 top 12", h: 400, ml: 200, sortByOpposition: true},
];
const availAxes = hasCrosstab
  ? axisOrder.filter(({key}) => (crosstabs[key]?.length || 0) > 0)
  : [];
```

<div class="grid grid-cols-2">
${availAxes
  .filter(({key}) => key !== "province" && key !== "occupation")
  .map(
    (ax) => html`<div class="card">${crosstabChart({
      title: `${ax.label} × Q${primaryMeta.primary_q_num}`,
      rows: crosstabs[ax.key],
      height: ax.h,
      marginLeft: ax.ml,
      sortByOpposition: ax.sortByOpposition,
    })}</div>`,
  )}
</div>

${availAxes.find((ax) => ax.key === "province") ? html`<div class="card">${crosstabChart({
  title: `지역 17개 시도 × Q${primaryMeta.primary_q_num} (표본 크기 정렬)`,
  rows: crosstabs.province,
  height: 480,
  marginLeft: 160,
})}</div>` : ""}

${availAxes.find((ax) => ax.key === "occupation") ? html`<div class="card">${crosstabChart({
  title: `직업 top 12 × Q${primaryMeta.primary_q_num}`,
  rows: crosstabs.occupation,
  height: 400,
  marginLeft: 200,
  sortByOpposition: true,
})}</div>` : ""}

---

## ③ 발견 패턴 — key findings

<div class="muted">보고서 합성 LLM이 valid ${fmt.format(meta.valid_n)}건 응답 + ${fmt.format(meta.insight_n_clusters || 0)}개 cluster 분석 + cross-cluster diff + synthesis 합성 단계로 도출한 패턴입니다.</div>

```js
const findings = round.insight.key_findings || [];
```

<div>
${findings.length === 0 ? html`<div class="muted">key_findings 비어 있음</div>` : findings.map((f) => html`
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
const quotes = round.insight.responses_to_chew_on || [];
```

<div>
${quotes.length === 0 ? html`<div class="muted">responses_to_chew_on 비어 있음</div>` : quotes.map((q) => html`
  <div class="quote-card">
    <div class="muted"><strong>${q.persona_attrs}</strong> · 모델: <code>${q.model}</code></div>
    <blockquote>${q.quote}</blockquote>
    <div class="curator-note">📝 <strong>큐레이터 노트</strong> — ${q.curator_note}</div>
  </div>
`)}
</div>

---

## ⑤ 응답 카드 — 핵심 응답 분포 샘플

```js
const samples = round.sample_responses || [];
const primaryQNum = primaryMeta.primary_q_num;
const primaryLabels = primaryMeta.labels || ["1","2","3","4","5"];
const primaryRange = primaryMeta.range || [1, 5];
const sampleByPrimary = (() => {
  const c = {};
  for (const r of samples) c[r._primary] = (c[r._primary] || 0) + 1;
  return c;
})();
const primaryValues = [];
for (let v = primaryRange[0]; v <= primaryRange[1]; v++) primaryValues.push(v);
const sampleSummary = primaryValues
  .map((v) => `${v} ${primaryLabels[v-1] || v}: ${sampleByPrimary[v] || 0}건`)
  .join(" · ");
```

<div class="muted">Q${primaryQNum} 핵심 응답 1~5 각 구간에서 valid 응답 최대 6건씩 시드 고정 샘플로 표시합니다. 본 라운드: ${sampleSummary}. 자유서술은 240자에서 잘립니다.</div>

```js
const filterPrimary = view(
  Inputs.checkbox(primaryValues, {
    label: `Q${primaryQNum} 응답 필터`,
    value: primaryValues,
    format: (v) => `${v} ${primaryLabels[v - 1] || v}`,
  }),
);
```

```js
const filtered = samples.filter((r) => filterPrimary.includes(r._primary));
```

<div>
${filtered.map((r) => html`
  <div class="response-card">
    <div class="badge-col">
      <span class="q1-badge q1-${r._primary}">${r._primary}</span>
      <span class="q1-label">Q${primaryQNum}</span>
      <span class="muted">${
        questions
          .filter((q) => q.q_num !== primaryQNum && q.type_class === "numeric")
          .map((q) => `Q${q.q_num} ${r[q.q_key] ?? "-"}`)
          .join(" · ")
      }</span>
    </div>
    <div>
      <div class="persona-attrs">
        ${[r.age ? r.age + "세" : "", r.sex, r.province, r.education_level, r.occupation, r.marital_status]
          .filter((x) => x)
          .join(" · ")}
      </div>
      ${questions
        .filter((q) => q.type_class === "freetext")
        .map((q) => html`<p class="persona-quote">${r[q.q_key] || ""}</p>`)}
      ${questions
        .filter((q) => q.type_class === "categorical")
        .map((q) => html`<div class="response-meta">Q${q.q_num}: <code>${r[q.q_key] || "-"}</code></div>`)}
    </div>
  </div>
`)}
</div>

<div class="muted">필터 결과 ${filtered.length} / ${samples.length}건 표시</div>

---

## ⑥ 큐레이터 가설 — curator hypotheses

<div class="muted">발견 패턴을 큐레이터 도메인 어조로 옮긴 가설 후보입니다. 타깃 그룹·전달 형식·메시지 본문 세 차원으로 정리됩니다.</div>

```js
const hypotheses = round.insight.curator_hypotheses || [];
```

<div>
${hypotheses.length === 0 ? html`<div class="muted">curator_hypotheses 비어 있음</div>` : hypotheses.map((h, i) => html`
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
const nextQs = round.insight.next_questions || [];
```

<div>
${nextQs.length === 0 ? html`<div class="muted">next_questions 비어 있음</div>` : nextQs.map((q, i) => html`
  <div class="next-question"><strong>Q${String(i + 1).padStart(2, "0")}</strong> — ${q}</div>
`)}
</div>

---

<div class="muted">
⚙ knowing-koreans · run_id <code>${meta.run_id || "-"}</code> · 데이터: NVIDIA Nemotron-Personas-Korea (CC BY 4.0) · OpenRouter 경유 다중 LLM · Observable Framework 정적 호스팅
</div>
