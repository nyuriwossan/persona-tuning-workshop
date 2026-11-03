#!/usr/bin/env python3
"""共通Markdown出力の回帰テスト（v0.4.2 の出力と、現在の index.html の出力が一致するか）

使い方（Python の playwright と chromium が必要）:
  python3 tests/regression.py              # index.html を tests/baseline-v0.4.2.json と比較
  python3 tests/regression.py --make-baseline /path/to/v0.4.2/index.html   # 基準データを作り直す（通常は不要）

基準データには長い文字列そのものではなく SHA-256 と長さを保存しています。
"""
import sys, json, hashlib, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = pathlib.Path(__file__).resolve().parent / "baseline-v0.4.2.json"

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
    now = snapshot(ROOT / "index.html"); base = json.loads(BASE.read_text(encoding="utf-8"))
    bad = []; diff(base, now, "", bad)
    n = sum(1 for _ in json.dumps(base).split(","))
    print(f"回帰テスト（共通Markdown出力・旧形式の移行）: {'成功' if not bad else '失敗'} / 比較項目 約{n} / 不一致 {len(bad)}")
    for x in bad[:20]: print("  不一致:", x)
    sys.exit(1 if bad else 0)
