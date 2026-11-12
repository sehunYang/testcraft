// TestCraft 체험판: 앱 화면이 부르는 서버 요청(/api/...)을 브라우저 안에서 흉내 낸다.
// 문항 편집·검토·배점·승인·그림 확정은 실제처럼 움직이고, 내용은 이 창을 닫으면 사라진다.
// AI 작업은 실행하지 않는다. 진행 창이 3초 뜬 뒤 닫히고, 4번 문항(아이디어 한 줄 + AI 재작성)만
// 미리 만들어 둔 실제 앱 결과로 채워진다. 파일 받기와 그림 올리기는 막는다.
'use strict';
(() => {
  if ('serviceWorker' in navigator && !navigator.serviceWorker.controller) { location.replace('./index.html'); return; }
  const BASE = new URL('./', location.href).pathname;
  const JOB_MS = 2600;   // 앱은 1.8초마다 상태를 묻는다: 진행 창은 약 3.6초 뒤 닫힌다
  const realFetch = window.fetch.bind(window);
  const clone = x => JSON.parse(JSON.stringify(x));
  const now = () => new Date().toISOString().slice(0, 19);
  const uid = () => Array.from(crypto.getRandomValues(new Uint8Array(8)), b => b.toString(16).padStart(2, '0')).join('');
  const NOT_HERE = '체험판에서는 실행하지 않는 기능입니다. 앱을 내려받아 사용해 보세요.';
  const NO_AI = '체험판이라 AI 작업은 실행하지 않았습니다. 4번 문항의 AI 생성만 실제 앱 결과로 미리 보여 드립니다.';
  let D, exams = {}, jobs = {};
  const ready = realFetch(BASE + 'data/demo.json').then(r => r.json()).then(d => {
    D = d;
    const e = clone(d.exam); for (const k of ['validation', 'card_validation', 'cards_approved', 'content_digest', 'active_job']) delete e[k];
    exams[e.id] = e;
  });

  // ---- 서버 규칙의 체험판용 축약(app/core.py) ----
  const written = c => (D.boot.subjective_types || []).includes(c.type);
  const imageBlocks = c => (c.materials || []).filter(b => b.kind === 'image');
  const VOLATILE = new Set(['review_approved', 'image', 'image_labels', 'labels_initialized', 'image_scene', 'image_plan_approval', 'calculation_override', 'ai_requested', 'ai_feedback', 'estimate', 'discrimination', 'no', 'points', 'materials']);
  const contentKey = c => JSON.stringify(Object.keys(c).sort().filter(k => !VOLATILE.has(k)).map(k => [k, c[k]]));
  const digest = e => JSON.stringify(e.cards.map(c => [c.no, contentKey(c), !!c.review_approved, c.points]));
  const cardsApproved = e => !!(e.card_approval && e.card_approval.digest === digest(e));
  function validate(e, phase = 'export') {
    const errors = [], issues = [], warnings = []; let total = 0;
    const issue = (code, message, c, field, stage = 'review', material_id = null) => { errors.push(message); issues.push({code, card_id: c ? c.id : null, material_id, field, stage, severity: 'error', message}); };
    if (!e.cards.length) issue('cards_required', '문항을 추가해 주세요.', null, null, 'design');
    for (const c of e.cards) {
      const n = c.no, w = written(c);
      for (const [k, label] of [['standard', '성취기준'], ['type', '문항 유형'], ['difficulty', '난이도'], ['idea', '핵심 아이디어'], ['question', '발문'], ['choices', '선택지'], ['answer', '정답'], ['points', '배점'], ['explanation', '해설']])
        if (!c[k] && !(w && (k === 'choices' || k === 'answer'))) issue(`${k}_required`, `${n}번: ${label} 누락`, c, k);
      if (w) for (const [k, label] of [['model_answer', '모범 답안'], ['rubric', '채점 기준']]) if (!c[k]) issue(`${k}_required`, `${n}번: ${label} 누락`, c, k);
      if (!w && (String(c.choices || '').match(/[①②③④⑤]/g) || []).join('') !== '①②③④⑤') issue('choices_format', `${n}번: 선택지는 ①~⑤ 순서로 한 번씩 필요합니다.`, c, 'choices');
      if (c.type === '합답형' && !c.statements) issue('statements_required', `${n}번: 합답형 보기가 없습니다.`, c, 'statements');
      if (!c.review_approved) issue('review_required', `${n}번: 문항 검토 확인이 필요합니다.`, c, 'review_approved');
      if (phase === 'export') for (const b of imageBlocks(c)) {
        const name = `${n}번 ${b.label || '그림'}`;
        if (!b.image_plan_approval && !(b.image && b.image.approved)) issue('image_plan_unconfirmed', `${name}: 제작 계획을 명시적으로 확인해 주세요.`, c, 'image_plan_approval', 'image-confirm', b.id);
        if (!b.image || !b.image.approved || !b.image.final_file) issue('image_approval_required', `${name}: 그림과 글씨를 최종 확정해 주세요.`, c, 'image', 'image', b.id);
      }
      total += parseFloat(c.points || 0);
    }
    if (Math.abs(total - 100) > 0.001) issue('score_total', `현재 배점 합은 ${+total.toFixed(3)}점입니다. 배점 패널에서 합계 100점을 맞춰 주세요.`, null, 'points', 'score');
    if (phase === 'export' && !cardsApproved(e)) issue('approval_required', '전체 출제안 승인이 필요합니다. 승인 후 그림 제작과 출력을 진행할 수 있습니다.', null, null, 'approval');
    return {errors, issues, warnings, points: Math.round(total * 1000) / 1000, ready: !errors.length};
  }
  function client(e) {
    const r = clone(e);
    r.validation = validate(e); r.card_validation = validate(e, 'cards'); r.cards_approved = cardsApproved(e);
    r.content_digest = digest(e).length.toString(16); r.active_job = Object.values(jobs).find(j => j.exam_id === e.id && j.status === 'running')?.id || null;
    return r;
  }
  function save(e) {
    for (const c of e.cards) {                      // 그림 단계의 상태를 위쪽 칸과 자료 블록이 함께 갖는다
      const b = imageBlocks(c)[0];
      if (b) for (const k of ['image', 'image_labels', 'labels_initialized', 'image_scene', 'image_plan_approval']) c[k] = clone(b[k] ?? null);
    }
    if (e.card_approval && e.card_approval.digest !== digest(e)) e.card_approval = null;
    e.updated = now(); e.revision = (e.revision || 0) + 1;
    return e;
  }
  function allocate(cards) {                       // 상·중·하 배점(소수 첫째 자리, 최대 나머지 방식)
    if (!cards.length || cards.some(c => !['하', '중', '상'].includes(c.difficulty))) throw Error('모든 문항의 상·중·하 난이도를 먼저 입력해 주세요.');
    const base = {하: 100, 중: 125, 상: 150}, w = {};
    for (const level in base) {
      const group = cards.map((c, i) => c.difficulty === level ? i : -1).filter(i => i >= 0);
      group.forEach((i, rank) => { w[i] = base[level] + (group.length > 1 ? 10 * rank / (group.length - 1) - 5 : 0); });
    }
    const total = Object.values(w).reduce((a, b) => a + b, 0), exact = {}, units = {};
    for (const i in w) { exact[i] = 1000 * w[i] / total; units[i] = Math.floor(exact[i] + 1e-9); }
    const left = 1000 - Object.values(units).reduce((a, b) => a + b, 0);
    Object.keys(exact).sort((a, b) => (exact[b] - units[b]) - (exact[a] - units[a]) || w[b] - w[a] || a - b).slice(0, left).forEach(i => units[i]++);
    return cards.map((c, i) => ({...c, points: String(units[i] / 10)}));
  }
  const findCard = (e, id) => { const c = e.cards.find(x => x.id === id); if (!c) throw Error('문항을 찾을 수 없습니다.'); return c; };
  const targets = (c, mid) => imageBlocks(c).filter(b => !mid || b.id === mid);
  const pendingAi = c => c.id === D.ai.card_id && !c.question;
  function summary(e) {
    const review = e.cards.filter(c => !c.review_approved).length, blocks = e.cards.flatMap(imageBlocks), images = blocks.filter(b => !(b.image && b.image.approved)).length;
    const v = validate(e);
    return {id: e.id, title: e.title, updated: e.updated, subject: e.subject, card_count: e.cards.length, review_remaining: review, image_remaining: images, image_total: blocks.length,
      next_action: review ? `검토 ${review}개 남음` : !cardsApproved(e) ? '출제안 승인' : images ? `그림 ${images}개 남음` : v.ready ? '시험지 받기' : `${v.issues.length}개 확인 필요`};
  }

  // ---- AI 작업: 3초 뒤 끝난다 ----
  function finish(job) {
    const e = exams[job.exam_id]; if (!e || job.status !== 'running') return;
    let filled = 0;
    for (const t of job.item_targets) {
      const c = e.cards.find(x => x.id === t.card_id); if (!c || c.id !== D.ai.card_id) continue;
      if ((job.action === 'question' || job.action === 'workflow') && pendingAi(c)) {
        Object.assign(c, clone(D.ai.question), {id: c.id, no: c.no, points: c.points, ai_requested: false, review_approved: false}); filled++;
      } else if (job.action === 'image' && c.question) {
        const blocks = Object.fromEntries(D.ai.image_blocks.map(b => [b.id, b]));
        c.materials = (c.materials || []).map(b => blocks[b.id] ? {...clone(blocks[b.id]), image_plan_approval: b.image_plan_approval} : b); filled++;
      } else if ((job.action === 'labels' || job.action === 'plan') && c.question) filled++;
    }
    if (filled) { save(e); Object.assign(job, {status: 'completed', progress: job.total, succeeded: filled, message: 'AI 작업이 끝났습니다. 결과를 검토해 주세요.'}); }
    else Object.assign(job, {status: 'cancelled', message: NO_AI});
  }

  // ---- 요청 처리 ----
  const json = (body, status = 200) => new Response(JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});
  async function handle(url, method, data, raw) {
    const p = url.pathname;
    if (method === 'GET') {
      if (p === '/api/bootstrap') return json({...D.boot, exams: Object.values(exams).map(summary).sort((a, b) => b.updated.localeCompare(a.updated))});
      if (p === '/api/standards') return json(D.standards);
      if (p === '/api/codex/status') return json(D.boot.codex);
      if (p.startsWith('/api/exams/')) { const e = exams[p.split('/')[3]]; return e ? json(client(e)) : json({error: '회차를 찾을 수 없습니다.'}, 400); }
      if (p.startsWith('/api/jobs/')) { const job = jobs[p.split('/')[3]]; if (!job) return json({error: '작업이 없습니다.'}, 400); if (Date.now() - job.started >= JOB_MS) finish(job); return json({...job, log: ''}); }
      const g = D.gets[p + url.search]; if (g) return json(g);
      if (p === '/api/kice/status') return json({available: false, stage: '', error: ''});
      return json({error: NOT_HERE}, 400);
    }
    const key = p + '|' + raw;
    if (p === '/api/math-preview') return json(D.previews[key] || {segments: [{type: 'text', text: String(data.text || '')}]});
    if (p === '/api/label-preview') return D.previews[key] ? json(D.previews[key]) : json({error: '체험판에서는 새 글씨를 그리지 않습니다.'}, 400);
    if (p === '/api/create') {
      const title = String(data.title || '').trim(); if (!title) throw Error('시험 제목을 1~200자로 입력해 주세요.');
      if (data.xlsx || data.legacy) throw Error(NOT_HERE);
      const tpl = clone(D.ai.question), blank = {};
      for (const [k, v] of Object.entries(tpl)) blank[k] = Array.isArray(v) ? [] : typeof v === 'boolean' ? false : typeof v === 'number' ? 0 : v && typeof v === 'object' ? null : '';
      Object.assign(blank, {id: uid(), no: 1, materials: [], checks: [], authoring_mode: data.authoring_mode || 'ai', image_plan_version: 2});
      const e = {id: uid(), title, subject: String(data.subject || ''), cards: [blank], revision: 0, created: now(), updated: now(), exports: [], card_approval: null, sets: [], school: '', passage_size: '11'};
      exams[e.id] = save(e); return json(client(e));
    }
    const e = exams[data && data.exam_id];
    if (!e) throw Error('회차를 찾을 수 없습니다.');
    if (p !== '/api/cancel' && data.revision !== undefined && data.revision !== e.revision)
      return json({error: '다른 화면에서 변경된 내용이 있습니다. 최신본과 내 초안을 비교해 주세요.', code: 'revision_conflict', latest: client(e)}, 409);
    switch (p) {
      case '/api/save': {
        const old = Object.fromEntries(e.cards.map(c => [c.id, c]));
        e.cards = data.cards.map((raw, i) => {
          const c = clone(raw), prev = old[c.id]; c.no = i + 1;
          for (const b of c.materials || []) if (b.kind === 'image') {     // 그림·확정 상태는 화면이 바꾸지 못한다
            const pb = prev && (prev.materials || []).find(x => x.id === b.id);
            b.image = pb ? clone(pb.image) : null; b.image_plan_approval = pb ? clone(pb.image_plan_approval) : null;
          }
          if (!prev || contentKey(c) !== contentKey(prev)) c.review_approved = false;
          return c;
        });
        for (const k of ['title', 'subject', 'school', 'passage_size', 'sets']) if (data[k] !== undefined) e[k] = data[k];
        return json(client(save(e)));
      }
      case '/api/delete': delete exams[e.id]; return json({ok: true});
      case '/api/duplicate-card': {
        const i = e.cards.findIndex(c => c.id === data.card_id); if (i < 0) throw Error('복제할 문항을 찾을 수 없습니다.');
        const copy = {...clone(e.cards[i]), id: uid(), review_approved: false};
        for (const b of copy.materials || []) b.id = uid();
        e.cards.splice(i + 1, 0, copy); e.cards.forEach((c, k) => { c.no = k + 1; }); e.card_approval = null;
        return json({exam: client(save(e)), card_id: copy.id});
      }
      case '/api/score-preview': {
        const after = allocate(e.cards);
        return json({points: e.cards.map((c, i) => ({card_id: c.id, no: c.no, difficulty: c.difficulty, before: c.points, after: after[i].points})), total: Math.round(after.reduce((a, c) => a + parseFloat(c.points), 0) * 1000) / 1000});
      }
      case '/api/allocate': e.cards = allocate(e.cards); return json(save(e));
      case '/api/approve-cards': {
        const v = validate(e, 'cards'); if (!v.ready) throw Error('문항카드 승인 전 확인: ' + v.errors.slice(0, 8).join(' / '));
        e.card_approval = {digest: digest(e), approved_at: now()}; return json(save(e));
      }
      case '/api/verify': {
        const c = findCard(e, data.card_id), v = D.verify[c.id];
        if (v && contentKey(c) === contentKey(clone(D.exam.cards.find(x => x.id === c.id) || {}))) return json(v);
        const checks = (c.checks || []).map(x => ({label: x.label, ok: true, detail: '0'}));
        return json({checks, calculation: {required: !!c.calculation, blockers: [], content_digest: '', validation_digest: '', override_allowed: false, override_active: false}});
      }
      case '/api/approve': {
        const c = findCard(e, data.card_id);
        if (data.kind === 'image') {
          for (const b of targets(c, data.material_id)) {
            if (!b.image) throw Error('현재 문항의 그림을 먼저 생성해 주세요.');
            if (data.approved && !cardsApproved(e)) throw Error('문항카드 전체 승인이 필요합니다.');
            b.image.approved = !!data.approved;
          }
        } else {
          if (data.approved && pendingAi(c)) throw Error('4번: 발문·선택지·정답이 아직 없습니다. AI 생성을 먼저 눌러 보세요.');
          c.review_approved = !!data.approved; c.calculation_override = null;
        }
        return json(save(e));
      }
      case '/api/confirm-image-plan': {
        if (!cardsApproved(e)) throw Error('문항카드 전체 승인 후 그림 제작 범위를 확인해 주세요.');
        const c = findCard(e, data.card_id);
        for (const b of targets(c, data.material_id)) b.image_plan_approval = {context: 'demo', mode: b.image_mode, confirmed_at: now()};
        return json(save(e));
      }
      case '/api/jobs': {
        const action = data.action;
        if (!['question', 'image', 'workflow', 'plan', 'labels'].includes(action)) throw Error('작업 유형 오류');
        if (['image', 'labels'].includes(action) && !cardsApproved(e)) throw Error('문항카드를 먼저 전체 승인해 주세요. 승인 후 실제 그림을 생성합니다.');
        let ids = data.card_ids || (data.card_id ? [data.card_id] : e.cards.filter(c => c.ai_requested).map(c => c.id));
        if (!ids.length) throw Error('AI 생성 요청이 Yes인 문항이 없습니다.');
        const cards = ids.map(id => findCard(e, id));
        if (['question', 'workflow'].includes(action)) for (const c of cards) if (!(c.standard && c.type && c.difficulty && c.idea)) throw Error(`${c.no}번: 성취기준·유형·난이도·핵심 아이디어를 입력해 주세요.`);
        const item_targets = cards.flatMap(c => ['image', 'labels', 'plan'].includes(action) ? targets(c, data.material_id).map(b => ({card_id: c.id, material_id: b.id})) : [{card_id: c.id, material_id: null}]);
        const first = cards[0];
        const job = {id: uid(), exam_id: e.id, status: 'running', progress: 0, total: item_targets.length, created: now(), provider: 'codex', action, failed: [], succeeded: 0,
          message: `${first.no}번 ` + ({question: '문항·해설 생성 중', workflow: '문항·해설 생성 중', plan: '그림·글씨 프롬프트 분리 중', image: '글씨 없는 배경 생성 중', labels: '글씨 객체 배치 중'})[action],
          item_ids: [...new Set(item_targets.map(t => t.card_id))], item_targets, started: Date.now()};
        jobs[job.id] = job; return json(job);
      }
      case '/api/cancel': { const job = jobs[data.job_id]; if (job && job.status === 'running') Object.assign(job, {status: 'cancelled', message: '작업을 취소했습니다.'}); return json({ok: true}); }
      case '/api/export': case '/api/recalculate':
        throw Error('체험판에서는 시험지 파일을 만들지 않습니다. 홈페이지의 시험지·답지 예시를 보거나, 앱을 내려받아 사용해 보세요.');
      default: throw Error(NOT_HERE);
    }
  }
  window.fetch = async function (input, opts = {}) {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return realFetch(input, opts);
    await ready;
    const method = (opts.method || (typeof input === 'string' ? 'GET' : input.method) || 'GET').toUpperCase();
    try { return await handle(url, method, opts.body ? JSON.parse(opts.body) : null, opts.body || ''); }
    catch (err) { return json({error: err.message}, 400); }
  };
  // 홈페이지의 단계 탭(설계·검토·그림·출력)을 누르면 체험판도 그 단계로 간다.
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || typeof event.data?.tcDemoStage !== 'number') return;
    document.querySelector(`[data-stage="${event.data.tcDemoStage}"]`)?.click();
  });
  // 첫 화면 대신 예시 시험을 바로 연다.
  const open = setInterval(() => {
    if (typeof state === 'undefined' || !state.boot || typeof openExam !== 'function') return;
    clearInterval(open); if (!state.exam) openExam(D.exam.id);
  }, 120);
})();
