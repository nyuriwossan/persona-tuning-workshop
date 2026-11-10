#!/usr/bin/env python3
"""回帰テスト（段階変化型の出力が以前の版と一致するか）

  1. 共通Markdown出力・旧形式の移行 … v0.4.2 と比較（tests/baseline-v0.4.2.json）
  2. 出力先4系統の出力・試着・会話例Markdown・プリセット適用と取り消し・関係段階の作り方・急変チェック
     … v0.5.0 と比較（tests/baseline-v0.5.0.json）。v0.6.0 の単独人格モードを追加しても、
     段階変化型（既定）の結果が変わっていないことを確かめる

使い方（Python の playwright と chromium が必要）:
  python3 tests/regression.py              # index.html を2つの基準データと比較
  python3 tests/regression.py --make-baseline /path/to/v0.4.2/index.html        # 基準1を作り直す（通常は不要）
  python3 tests/regression.py --make-baseline-v050 /path/to/v0.5.0/index.html   # 基準2を作り直す（通常は不要）

基準データには長い文字列そのものではなく SHA-256 と長さを保存しています。
"""
import sys, json, hashlib, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = pathlib.Path(__file__).resolve().parent / "baseline-v0.4.2.json"
BASE050 = pathlib.Path(__file__).resolve().parent / "baseline-v0.5.0.json"

FIXTURES = {
  "default": "(() => defaultData())()",
  "all_used": "(() => { const d = defaultData(); TRAITS.forEach(t => d.traits[t.id].use = true); return d; })()",
  "all_sections": "(() => { const d = defaultData(); TRAITS.forEach(t => d.traits[t.id].use = true); Object.keys(d.output.sections).forEach(k => d.output.sections[k] = true); d.meta.name='ミナト'; d.relation.romance.mode='conditional'; d.relation.romance.after='open'; d.relation.romance.presets=[]; return d; })()",
  "locked_mix": "(() => { const d = defaultData(); TRAITS.forEach((t,i) => { d.traits[t.id].use = i % 2 === 0; if(i % 5 === 0) d.traits[t.id].locked = true; d.traits[t.id].stages = {initial:1+(i%5), trust:1+((i+2)%5), deep:1+((i+4)%5)}; d.traits[t.id].common = 1+(i%5); }); Object.keys(d.output.sections).forEach(k => d.output.sections[k] = true); d.meta.name='ユリ'; d.output.showPreset = true; return d; })()",
  "speech_pron_stages": "(() => { const d = defaultData(); TRAITS.forEach(t => d.traits[t.id].use = true); d.speech.enabled = true; d.speech.stages = {initial:'polite', trust:'std', deep:'gentle'}; d.pron.enabled = true; d.pron.me.initial='私'; d.pron.me.deep='俺'; d.pron.you.initial='あなた'; d.pron.you.deep='君'; d.output.sections.speech = true; d.output.sections.persona = true; d.output.sections.progress = true; d.output.sections.ifthen = true; d.relation.rules.push({when:'褒められたとき', then:'顔を背けて礼を言う', out:true}); d.relation.rules.push({when:'非表示', then:'出さない', out:false}); return d; })()",
  "romance_none_progress": "(() => { const d = defaultData(); TRAITS.forEach(t => d.traits[t.id].use = true); Object.keys(d.output.sections).forEach(k => d.output.sections[k] = true); d.relation.trust.custom = ['一緒に食事をした']; d.relation.romance.mode = 'none'; return d; })()",
  "romance_innate": "(() => { const d = defaultData(); TRAITS.forEach(t => d.traits[t.id].use = true); Object.keys(d.output.sections).forEach(k => d.output.sections[k] = true); d.relation.romance.mode = 'innate'; d.relation.romance.after = 'bold'; return d; })()",
  "empty_sections": "(() => { const d = defaultData(); Object.keys(d.output.sections).forEach(k => d.output.sections[k] = false); return d; })()",
  "prio_variety": "(() => { const d = defaultData(); TRAITS.forEach((t,i) => { d.traits[t.id].use = true; d.traits[t.id].prio = ['high','normal','low'][i%3]; }); return d; })()",
}
LEGACY = {
  "v1": {"v":1, "meta":{"name":"旧データ","budget":1500}, "traits":{"politeness":{"common":10,"stages":{"initial":10,"trust":50,"deep":90}},"warmth":{"common":70,"stages":{"initial":10,"trust":50,"deep":90},"locked":True}}},
  "v2": {"v":2, "meta":{"name":"V2","budget":1800}, "traits":{"politeness":{"common":3,"stages":{"initial":2,"trust":3,"deep":4}},"warmth":{"common":4,"stages":{"initial":2,"trust":3,"deep":5},"use":True}}, "output":{"omit":["shyness"]}},
  "v3": {"v":3, "meta":{"name":"V3","budget":2000}, "traits":{"affection":{"common":4,"stages":{"initial":2,"trust":4,"deep":5},"use":True,"locked":False,"prio":"high"},"warmth":{"common":3,"stages":{"initial":2,"trust":3,"deep":4},"use":True}}},
  "v4": {"v":4, "meta":{"name":"V4","budget":2400}, "traits":{"warmth":{"common":3,"stages":{"initial":2,"trust":3,"deep":4},"use":True}}, "relation":{"rules":[{"when":"a","then":"b"}]}},
}

def h(x):
    """長い文字列は SHA-256 と長さに置き換える"""
    if isinstance(x, str) and len(x) > 40:
        return {"sha256": hashlib.sha256(x.encode("utf-8")).hexdigest(), "len": len(x)}
    if isinstance(x, dict): return {k: h(v) for k, v in x.items()}
    if isinstance(x, list): return [h(v) for v in x]
    return x

def snapshot(html):
    res = {}
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto("file://" + str(html)); pg.wait_for_function("typeof buildMarkdown === 'function'")
        for name, src in FIXTURES.items():
            res["fx_" + name] = pg.evaluate("""(src) => {
              const D0 = eval(src), out = {};
              for (const lv of [1,2,3]) { const r = buildMarkdown(D0, lv); out['md'+lv] = r.text; out['parts'+lv] = r.parts; }
              for (const mode of ['auto','1','2','3']) for (const budget of [0, 300, 800, 1500, 2000, 6000]) {
                const D1 = JSON.parse(JSON.stringify(D0)); D1.meta.budget = budget;
                const r = chooseOutput(D1, mode); out['ch_'+mode+'_'+budget] = {level:r.level, auto:r.auto, text:r.text};
              }
              return out; }""", src)
        for name, raw in LEGACY.items():
            res["legacy_" + name] = pg.evaluate("""(raw) => {
              const d = migrate(raw);
              const o = {traits:d.traits, relation:d.relation, speech:d.speech, pron:d.pron, link:d.link, legacy:d.legacy, name:d.meta.name, budget:d.meta.budget,
                         sections:d.output.sections, progressParts:d.output.progressParts};
              for (const lv of [1,2,3]) o['md'+lv] = buildMarkdown(d, lv).text;
              return o; }""", raw)
        b.close()
    return h(res)

# v0.5.0 の基準：出力先ごとの出力・試着・プリセット・段階の作り方（段階変化型）
FIXTURES_V050 = dict(FIXTURES)
FIXTURES_V050.update({
  "romance_start_open": "(() => { const d = defaultData(); TRAITS.forEach((t,i) => { d.traits[t.id].use = true; d.traits[t.id].stages = {initial:1+(i%5), trust:1+((i+1)%5), deep:1+((i+3)%5)}; }); Object.keys(d.output.sections).forEach(k => d.output.sections[k] = true); d.relation.romance.mode = 'start'; d.relation.romance.after = 'open'; d.speech.common = 'haughty'; d.pron.me.common = '俺'; d.pron.you.common = 'お前'; return d; })()",
  "romance_cond_conds": "(() => { const d = defaultData(); TRAITS.forEach(t => d.traits[t.id].use = true); Object.keys(d.output.sections).forEach(k => d.output.sections[k] = true); d.relation.romance.mode = 'conditional'; d.relation.romance.after = 'unaware'; d.relation.romance.presets = ['special','absent']; d.relation.romance.custom = ['雨の日に傘を差し出される']; d.speech.enabled = true; d.speech.stages = {initial:'curt', trust:null, deep:'gentle'}; d.output.showPreset = true; d.presets.base = 'kuudere'; return d; })()",
})
SVC_JS = """(src) => {
  const D0 = eval(src), out = {};
  const svcs = [['common',null],['talelynx',null],['chacha',null],['plaitoon','basic11'],['plaitoon','sim'],['plaitoon','custom']];
  const EX = [{id:1,label:'a',user:'こんにちは',char:'「やあ」',on:true},{id:2,label:'b',user:'',char:'（会釈する）',on:true},{id:3,label:'c',user:'x',char:'y',on:false},{id:4,label:'d',user:'u',char:'v',on:true},{id:5,label:'e',user:'p',char:'q',on:true}];
  for(const [svc, tpl] of svcs) for(const inl of [false, true]){
    if(inl && !(svc === 'talelynx' || tpl === 'custom')) continue;
    for(const mode of ['auto','1','2','3']) for(const budget of [0, 900, 1500]){
      const X = JSON.parse(JSON.stringify(D0)); X.meta.budget = budget; X.output.dest.service = svc; if(tpl) X.output.dest.plaitoon = tpl;
      X.output.dest.exInline = inl; X.output.dest.chachaDesc = svc === 'chacha' ? '夜の港町。abc' : ''; X.output.dest.examples = JSON.parse(JSON.stringify(EX));
      const T = buildOutput(X, mode);
      out[[svc, tpl, inl, mode, budget].join('_')] = {level:T.level, auto:T.auto, fields:T.fields.map(f => ({id:f.id, text:f.text, count:f.count, over:f.over, rem:f.rem})),
        pool:T.pool, budget:T.budget, svcOver:T.svcOver, parts:T.md.parts, ex:T.ex, inlineChars:T.inlineChars};
    }
  }
  const NO = {preset:'', me:'', you:''};
  for(const sit of SITUATIONS) for(const rom of [false, true])
    out['pv_' + sit.id + '_' + rom] = STAGES.map(st => { const r = renderSituation(D0, sit, st.id, rom, NO); return {text:r.text, notes:r.notes, me:r.me, you:r.you, preset:r.preset}; });
  out.pvmd = previewMarkdown(D0, SITUATIONS, true, NO);
  out.pvmd_ov = previewMarkdown(D0, SITUATIONS.slice(0, 2), false, {preset:'haughty', me:'俺', you:'お前'});
  D = JSON.parse(JSON.stringify(D0));
  out.checks = checks(); out.secImpact = [1,2,3].map(l => secImpact(D, l)); out.useImpact = [1,2,3].map(l => useImpact(D, l));
  return out; }"""
OPS_JS = """() => {
  const out = {}, J = x => JSON.parse(JSON.stringify(x));
  const strip = u => { const x = J(u); delete x.at; return x; };
  for(const lm of ['suggest','linked','individual']) for(const pat of ['gradual','gap','subtle'])
   for(const [kind, id] of [['base','haughty'],['base','schemer'],['base','tsundere'],['base','timid'],['love','silentDote'],['love','sweet']]){
    D = defaultData(); D.link.mode = lm; D.presets.pattern = pat;
    D.traits.pride.use = true; D.traits.pride.stages = {initial:2, trust:2, deep:3};
    D.traits.candor.use = true; D.traits.candor.locked = true; D.traits.candor.common = 2;
    D.traits.affectionWords.use = true; D.traits.affectionWords.stages = {initial:3, trust:3, deep:3};
    UI.pre.kind = kind; UI.pre.sel = id; resetPreChoice();
    const P = presetOf(kind, id), rows = presetRows(kind, id, pat);
    rows.filter(r => r.status === 'conflict').forEach(r => { UI.pre.choice[r.id] = 'apply'; });
    lockCandidates(P, rows).forEach(r => { UI.pre.locks[r.id] = true; });
    (P.ifthen || []).forEach((x, i) => { UI.pre.rules[i] = true; });
    applyPreset();
    const after = {traits:J(D.traits), link:J(D.link), rules:J(D.relation.rules), presets:J(D.presets), undo:strip(D.undo), rows:J(rows)};
    D.traits.pride.stages.deep = 1; // 適用後に手で変えた項目
    const info = undoInfo(); const changed = info ? info.changed : null;
    doUndo(true);
    out[[lm, pat, kind, id].join('_')] = {after, changed, undone:{traits:J(D.traits), link:J(D.link), rules:J(D.relation.rules), presets:J(D.presets), undo:J(D.undo)}};
  }
  for(const lm of ['suggest','linked','individual']){
    D = defaultData(); D.link.mode = lm; ['warmth','pride','wariness','trustSpeed','candor'].forEach(id => { D.traits[id].use = true; });
    const seq = [['initial','warmth',5,true],['initial','pride',1,false],['trust','warmth',2,true],['initial','warmth',4,true],['initial','pride',2,true],
                 ['deep','pride',5,true],['initial','pride',4,true],['initial','trustSpeed',1,true],['initial','wariness',5,true],['initial','candor',1,true]];
    seq.forEach(([st, id, v, cm]) => { UI.stage = st; setLevel(id, v, cm); });
    commitSugg();
    out['lv_' + lm] = {traits:J(D.traits), link:J(D.link), checks:checks()};
  }
  UI.stage = 'initial';
  return out; }"""

def snapshot_v050(html):
    res = {}
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto("file://" + str(html)); pg.wait_for_function("typeof buildOutput === 'function'")
        for name, src in FIXTURES_V050.items():
            res["svc_" + name] = pg.evaluate(SVC_JS, src)
        res["ops"] = pg.evaluate(OPS_JS)
        b.close()
    return h(res)

def diff(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b: out.append("key " + path + "/" + k)
            else: diff(a[k], b[k], path + "/" + k, out)
    elif a != b: out.append(path)

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--make-baseline":
        BASE.write_text(json.dumps(snapshot(pathlib.Path(sys.argv[2]).resolve()), ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
        print("baseline written:", BASE); sys.exit(0)
    if len(sys.argv) > 2 and sys.argv[1] == "--make-baseline-v050":
        BASE050.write_text(json.dumps(snapshot_v050(pathlib.Path(sys.argv[2]).resolve()), ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        print("baseline written:", BASE050); sys.exit(0)
    failed = False
    for label, fn, path in [("共通Markdown出力・旧形式の移行（基準 v0.4.2）", snapshot, BASE),
                            ("出力先4系統・試着・プリセット・段階の作り方（基準 v0.5.0）", snapshot_v050, BASE050)]:
        now = fn(ROOT / "index.html"); base = json.loads(path.read_text(encoding="utf-8"))
        bad = []; diff(base, now, "", bad)
        n = sum(1 for _ in json.dumps(base).split(","))
        print(f"回帰テスト（{label}）: {'成功' if not bad else '失敗'} / 比較項目 約{n} / 不一致 {len(bad)}")
        for x in bad[:20]: print("  不一致:", x)
        failed = failed or bool(bad)
    sys.exit(1 if failed else 0)
