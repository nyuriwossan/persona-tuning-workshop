#!/usr/bin/env python3
"""v0.8.0 の動作テスト（実ブラウザ Chromium で index.html を操作する）
  人格形成の背景／恋愛感情の状態遷移／関係段階の状態遷移／ギャップ設計／プロンプトの配置・再掲・配分／設定集／試着の追加と比較
  出力先 ZETA・Zetter の追加と、出力先ごとの案内

  ※ 出力の「文章の効果」（実際のチャットモデルでの人格維持率・条件遵守率）はここでは測れない。
     ここで確かめるのは、設定どおりの文章が・設定どおりの位置に・壊れずに出ることだけ

使い方: python3 tests/e2e_v080.py [--shots DIR]
"""
import sys, json, pathlib, re
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = None
if "--shots" in sys.argv: SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]); SHOTS.mkdir(parents=True, exist_ok=True)
URL = "file://" + str(ROOT / "index.html")
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    if not cond: print("  FAIL:", name, str(detail)[:400])

INIT = """
window.__clip = [];
Object.defineProperty(navigator, 'clipboard', {value:{writeText: async t => { window.__clip.push(t); }}, configurable:true});
try{ if(!localStorage.getItem('persona-tuning-workshop:data')) localStorage.setItem('persona-tuning-workshop:data', JSON.stringify({v:8, meta:{name:'', budget:2000, budgetSet:true, notice:''}})); }catch(e){}
"""
def fresh(b, w=390, h=844):
    ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto(URL); pg.wait_for_function("typeof buildOutput === 'function'")
    pg.errs = errs
    return pg
def tab(pg, t): pg.click(f"#tabs button[data-tab={t}]"); pg.wait_for_timeout(50)
def no_overflow(pg): return pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0

# 豊富な設定（段階変化型）。テストの中で D に入れる
RICH = r"""(() => {
  D = defaultData(); D.meta.budgetSet = true; D.meta.name = 'ミナト';
  ['warmth','pride','wariness','candor','disclosure','reliance','affectionActions','romInitiative','specialTreatment'].forEach(id => D.traits[id].use = true);
  D.traits.pride.locked = true; D.traits.pride.common = 4; D.traits.candor.prio = 'high'; D.traits.candor.stages = {initial:4, trust:4, deep:4};
  Object.keys(D.output.sections).forEach(k => D.output.sections[k] = true);
  D.relation.romance.mode = 'conditional'; D.relation.romance.presets = ['special'];
  D.background.items.push({...newBgItem(1), ...BG_PRESET.betrayal, id:1, preset:'betrayal', prio:'high'});
  D.background.items.push({...newBgItem(2), event:'騎士として育てられた', belief:'主君への忠誠を第一とする', influence:'規律を守る', prio:'low'});
  D.background.items.push({...newBgItem(3), title:'恩師', event:'恩師に救われた', out:'lore', keys:'恩師, 先生'});
  const RF = D.romanceFlow; RF.enabled = true;
  RF.trans.emerge.conds = ['相手の誠実さと価値観に魅力を感じる']; RF.trans.emerge.logic = 'accum'; RF.trans.emerge.after = '気遣いが増えるが友情と解釈する';
  RF.trans.aware.conds = ['相手の不在を寂しく感じた', '特別扱いしている自分に気づいた']; RF.trans.aware.after = '理性と職業倫理を維持する';
  RF.trans.confess.conds = ['立場に問題がない', '自分の意思で進めたいと判断した']; RF.trans.confess.logic = 'and';
  RF.trans.regress.conds = ['信頼を裏切られた']; RF.perceive = ['misread', 'restrain'];
  D.transition.enabled = true; D.transition.logic.trust = 'or'; D.transition.stages.initial.state = '相手を客として扱う';
  D.transition.stages.trust.first = '自分から雑談を振る'; D.transition.core = '嘘をつかない';
  D.gap.scope = 'user'; D.gap.from = '警戒・不信'; D.gap.to = '信頼・安心'; D.gap.keep = '仕事では公平';
  saveNow(); render(false);
})()"""

with sync_playwright() as p:
    b = p.chromium.launch()

    # ---------- 1. 版・移行・保存 ----------
    pg = fresh(b)
    check("版：APP_VERSION 0.8.0・DATA_VERSION 9・ヘッダー表示", pg.evaluate("APP_VERSION") == "0.8.0" and pg.evaluate("DATA_VERSION") == 9 and pg.inner_text(".ver") == "v0.8.0")
    mg = pg.evaluate("""() => {
      const out = {};
      const v8 = defaultData(); v8.v = 8; delete v8.background; delete v8.romanceFlow; delete v8.transition; delete v8.gap;
      ['layout','recap','alloc','extra'].forEach(k => delete v8.output[k]);
      v8.traits.warmth.use = true; v8.autonomy.enabled = true; v8.memo = 'keep';
      const m = migrate(v8);
      out.v = m.v; out.memo = m.memo; out.bg = m.background; out.rf = m.romanceFlow.enabled; out.tr = m.transition.enabled; out.gap = m.gap;
      out.layout = m.output.layout; out.recap = m.output.recap; out.extra = m.output.extra; out.auto = m.autonomy.enabled;
      out.same = buildMarkdown(m, 2).text === buildMarkdown({...v8, v:9}, 2).text;
      for(const v of [1,2,3,4,5,6,7]){ const x = migrate({v, traits:{warmth:{common:3, stages:{initial:2, trust:3, deep:4}, use:true}}}); out['v' + v] = x.v === 9 && Array.isArray(x.background.items) && x.romanceFlow.enabled === false && x.output.layout === 'classic'; }
      const bad = migrate({v:9, traits:{}, background:{items:[{event:5, out:'x', prio:'?'}, 'junk']}, romanceFlow:{enabled:'y', start:'none', trans:{emerge:{conds:'a', logic:'q'}}, perceive:['dull','zz']},
                           transition:{enabled:1, skip:'x', logic:[]}, gap:{scope:'nope', from:3}, output:{layout:'x', recap:'y', extra:[]}});
      out.bad = {items:bad.background.items.length, ev:bad.background.items[0].event, outv:bad.background.items[0].out, prio:bad.background.items[0].prio,
        rf:bad.romanceFlow.enabled, start:bad.romanceFlow.start, conds:bad.romanceFlow.trans.emerge.conds, lg:bad.romanceFlow.trans.emerge.logic, per:bad.romanceFlow.perceive,
        tr:bad.transition.enabled, skip:bad.transition.skip, lgt:bad.transition.logic.trust, sc:bad.gap.scope, from:bad.gap.from, layout:bad.output.layout, recap:bad.output.recap, extra:bad.output.extra,
        txt:buildMarkdown(bad, 2).text.length > 0};
      return out; }""")
    check("移行：形式8→9。新機能は未使用で始まり、出力は変わらない", mg["v"] == 9 and mg["bg"] == {"items": []} and not mg["rf"] and not mg["tr"] and mg["layout"] == "classic" and mg["recap"] is False and mg["same"] and mg["auto"] is True, str(mg))
    check("移行：未知のフィールドを残す", mg["memo"] == "keep")
    check("移行：形式1〜7のデータも形式9へ", all(mg["v%d" % v] for v in range(1, 8)), str(mg))
    bd = mg["bad"]
    check("移行：不正な値は初期値へ（配列内の入力は文字列として残す・型違いの値は初期値・例外なし）", bd["items"] == 1 and bd["ev"] == "5" and bd["outv"] == "always" and bd["prio"] == "normal" and bd["rf"] is False and bd["start"] == "aware"
          and bd["conds"] == [] and bd["lg"] == "or" and bd["per"] == ["dull"] and bd["tr"] is False and bd["skip"] == "sequential" and bd["lgt"] == "accum"
          and bd["sc"] == "" and bd["from"] == "" and bd["layout"] == "classic" and bd["recap"] is False and bd["extra"] == {"background": True, "gap": True} and bd["txt"], str(bd))
    # ブラウザ保存の旧データ（形式8）は移行前に別名で控える
    ctx = b.new_context(viewport={"width": 390, "height": 844}); pr = ctx.new_page(); r_errs = []; pr.on("pageerror", lambda e: r_errs.append(str(e)))
    pr.goto(URL); pr.wait_for_function("typeof buildOutput === 'function'")
    v8raw = json.dumps({"v": 8, "meta": {"name": "旧", "budget": 1500, "budgetSet": True, "notice": ""}, "autonomy": {"enabled": True, "narration": True, "core": True, "ooc": True}}, ensure_ascii=False)
    pr.evaluate("(raw) => { window.removeEventListener('pagehide', saveNow); clearTimeout(saveTimer); localStorage.clear(); localStorage.setItem('persona-tuning-workshop:data', raw); }", v8raw)
    pr2 = ctx.new_page(); pr2.on("pageerror", lambda e: r_errs.append(str(e)))
    pr2.goto(URL); pr2.wait_for_function("typeof buildOutput === 'function'")
    check("保存：形式8のブラウザ保存を読み込み、移行前を別名（backup-v8）で控える", pr2.evaluate("localStorage.getItem('persona-tuning-workshop:data:backup-v8')") == v8raw and pr2.evaluate("D.v") == 9 and pr2.evaluate("D.meta.name") == "旧")
    # 新機能の設定を保存して開き直す
    pr2.evaluate(RICH.replace("D = defaultData(); D.meta.budgetSet = true;", "D = defaultData(); D.meta.budgetSet = true;") + "; D.output.layout = 'priority'; D.output.recap = true; D.output.alloc = true; saveNow();")
    want = pr2.evaluate("JSON.stringify({b:D.background, r:D.romanceFlow, t:D.transition, g:D.gap, o:[D.output.layout, D.output.recap, D.output.alloc, D.output.extra]})")
    pr3 = ctx.new_page(); pr3.on("pageerror", lambda e: r_errs.append(str(e)))
    pr3.goto(URL); pr3.wait_for_function("typeof buildOutput === 'function'")
    got = pr3.evaluate("JSON.stringify({b:D.background, r:D.romanceFlow, t:D.transition, g:D.gap, o:[D.output.layout, D.output.recap, D.output.alloc, D.output.extra]})")
    check("保存：新機能の設定がブラウザ保存から復元される", got == want and not r_errs, str(r_errs))
    js = pr3.evaluate("""() => { const j = JSON.stringify(D), m = migrate(JSON.parse(j)); return {same:JSON.stringify(m) === j, md:buildMarkdown(m, 2).text === buildMarkdown(D, 2).text}; }""")
    check("保存：JSONの書き出し→読み込みで同じ（往復）", js["same"] and js["md"], str(js))
    ctx.close()

    # ---------- 2. 人格形成の背景 ----------
    pg = fresh(b)
    pg.evaluate("D.traits.warmth.use = true; saveNow(); render(false);")
    before_traits = pg.evaluate("JSON.stringify(D.traits)")
    pg.click("#bg-card > summary")
    pg.click("[data-open=bgpre] > summary")
    pg.click("[data-act=bg-preset][data-id=betrayal]")
    it = pg.evaluate("D.background.items[0]")
    check("背景：プリセットで候補が入る（原体験・信念・影響・反応・変化・開示条件）", it["preset"] == "betrayal" and it["event"].startswith("信頼していた人物") and it["belief"] and it["reactWhen"] and it["reactThen"] and it["disclose"], str(it))
    check("背景：プリセットは人格スライダーの値を変えない", pg.evaluate("JSON.stringify(D.traits)") == before_traits)
    ta = pg.locator("[data-path='background.items.0.belief']")
    ta.fill("言葉より行動を信じる")
    check("背景：候補は編集できる", pg.evaluate("D.background.items[0].belief") == "言葉より行動を信じる")
    pg.click("[data-act=bg-add]")
    check("背景：複数件を登録できる", pg.evaluate("D.background.items.length") == 2)
    md = pg.evaluate("buildMarkdown(D, 2).text")
    check("背景：出力（見出し・因果の順：原体験→信念→影響→反応→開示条件）", "## 人格形成の背景" in md and md.index("- 原体験：") < md.index("- 信念：言葉より行動を信じる。") < md.index("- 人格への影響：") < md.index("- 過去について尋ねられた場合：") < md.index("- 開示条件："), md)
    check("背景：空の背景は出力しない（見出しも作らない）", "### 背景" not in md and "### 信頼" not in md and md.count("## 人格形成の背景") == 1, md)
    pg.evaluate("D.background.items[0].out = 'off'; saveNow();")
    check("背景：出力しない設定なら節を作らない", "## 人格形成の背景" not in pg.evaluate("buildMarkdown(D, 2).text"))
    pg.evaluate("D.background.items = []; saveNow(); render(true);")
    pg.on("dialog", lambda d: d.accept())
    bg_lv = pg.evaluate("""() => { const d = defaultData(); d.background.items = [{...newBgItem(1), ...BG_PRESET.loss, prio:'low'}, {...newBgItem(2), ...BG_PRESET.mentor, prio:'high'}];
      return [1,2,3].map(l => buildMarkdown(d, l).text); }""")
    check("背景：優先度「高」が先に並ぶ", bg_lv[1].index("恩師") < bg_lv[1].index("大切な人"), bg_lv[1])
    check("背景：優先度「低」は標準で圧縮（影響・変化を省き、開示条件は残す）", "大切な人を失った" in bg_lv[1] and "身近な人の無事" not in bg_lv[1] and "自分の大切な人の話を打ち明けたとき" in bg_lv[1], bg_lv[1])
    check("背景：詳細ではすべて出力", "身近な人の無事" in bg_lv[2])

    # ---------- 3. 恋愛感情の状態遷移 ----------
    pg.evaluate(RICH)
    md2 = pg.evaluate("buildMarkdown(D, 2).text")
    rom = md2[md2.index("## 信頼と恋愛感情"):]; rom = rom[:rom.index("\n\n## ")]
    check("恋愛：開始時点・段階・認識傾向・各条件を出力", all(x in rom for x in ["- 開始時点：恋愛感情なし。", "なし → 無自覚 → 自覚 → 表明", "- 認識の傾向：恋愛感情を、友情", "- 発生条件（同種の経験が積み重なって成立）：", "- 自覚条件（いずれか1つが成立）：", "- 表明条件（すべてが成立）：", "- 後退条件："]), rom)
    check("恋愛：従来の「芽生える条件」も発生条件に含める", "相手が自分だけを特別に扱う" in rom.split("- 発生条件")[1].split("\n")[0])
    check("恋愛：条件成立前は現在の段階を維持する旨", "条件が成立するまでは現在の段階に応じた言動を維持し、先の段階の言動を先取りしない" in rom)
    check("恋愛：使わない段階（受容）の条件は出力しない", "受容条件" not in rom)
    check("恋愛：従来の「芽生えた後の態度」は出力に使わない", "目が合うと逸らす" not in rom)
    combos = pg.evaluate("""() => {
      const out = [];
      for(const mode of ['conditional','start']) for(const un of [false, true]) for(const ac of [false, true]) for(const op of [false, true]) for(const start of ['unaware','aware','accepted','open']) for(const lv of [1,2,3]){
        const d = JSON.parse(JSON.stringify(D)); d.relation.romance.mode = mode; d.romanceFlow.use = {unaware:un, accepted:ac, open:op}; d.romanceFlow.start = start;
        ['emerge','aware','accept','confess'].forEach(k => { d.romanceFlow.trans[k].conds = ['C_' + k]; });
        const t = buildMarkdown(d, lv).text; out.push({mode, un, ac, op, start, lv, t}); }
      return out; }""")
    bad = []
    for c in combos:
        t = c["t"]
        order = ["none"] + (["unaware"] if c["un"] else []) + ["aware"] + (["accepted"] if c["ac"] else []) + (["open"] if c["op"] else [])
        st = "none" if c["mode"] == "conditional" else (c["start"] if c["start"] in order else "aware")
        si = order.index(st)
        exp = {"emerge": order.index("unaware" if c["un"] else "aware") > si,
               "aware": c["un"] and order.index("aware") > si,
               "accept": c["ac"] and order.index("accepted") > si,
               "confess": c["op"] and order.index("open") > si}
        for k, v in exp.items():
            if (("C_" + k) in t) != v: bad.append((c["mode"], c["un"], c["ac"], c["op"], c["start"], c["lv"], k))
        if "（未設定）" in t or "：\n\n" in t: bad.append(("empty", c["lv"]))
    check(f"恋愛：段階の使用×開始時点×詳細度（{len(combos)}通り）で、出力する移行条件が正しい", not bad, str(bad[:6]))
    lg = pg.evaluate("""() => { const r = {}; for(const lg of ['or','and','accum']) for(const n of [1,2]){ const d = JSON.parse(JSON.stringify(D)); d.relation.romance.presets = [];
      d.romanceFlow.trans.aware.logic = lg; d.romanceFlow.trans.aware.conds = n === 1 ? ['A'] : ['A','B']; r[lg + n] = buildMarkdown(d, 2).text.split('\\n').find(l => l.startsWith('- 自覚条件')); } return r; }""")
    check("恋愛：AND／OR／積み重ねの書き分け", lg["or2"] == "- 自覚条件（いずれか1つが成立）：A／B" and lg["and2"] == "- 自覚条件（すべてが成立）：A／B" and lg["accum2"] == "- 自覚条件（同種の経験が積み重なって成立）：A／B"
          and lg["or1"] == "- 自覚条件：A" and lg["and1"] == "- 自覚条件：A" and lg["accum1"] == "- 自覚条件（同種の経験が積み重なって成立）：A", str(lg))
    l3 = pg.evaluate("buildMarkdown(D, 3).text")
    check("恋愛：詳細では条件を入れ子の一覧で出力", "- 自覚条件（いずれか1つが成立）：\n  - 相手の不在を寂しく感じた\n  - 特別扱いしている自分に気づいた" in l3)
    # 恋愛感情を持たない設定：無効化（入力は保持）
    pg.evaluate("D.relation.romance.mode = 'none'; saveNow(); render(false);")
    none_md = pg.evaluate("buildMarkdown(D, 2).text")
    check("恋愛なし：詳細設定は出力しない（従来どおり「持たない」）", "恋愛感情は持たない" in none_md and "自覚条件" not in none_md and "開始時点：" not in none_md)
    check("恋愛なし：詳細設定の入力は保持", pg.evaluate("D.romanceFlow.enabled") is True and pg.evaluate("D.romanceFlow.trans.aware.conds.length") == 2)
    tab(pg, "relation")
    check("恋愛なし：詳細設定のスイッチは無効・保持の表示", pg.is_disabled("[data-act-change=rf-on]") and "保持" in pg.inner_text("#romflow"))
    check("恋愛なし：矛盾の警告を出す（設定は変えない）", "「恋愛感情は持たない」設定のため出力しません" in pg.inner_text("#v08-warn") and pg.evaluate("D.romanceFlow.enabled") is True)
    pg.click("[data-act=rom-mode][data-val=conditional]")
    check("恋愛：持つ設定に戻すと詳細設定が戻る", "自覚条件" in pg.evaluate("buildMarkdown(D, 2).text"))
    # 画面操作：トリガーのプリセット・追加・削除・成立のしかた
    pg.click("[data-act-change=rf-use][data-id=accepted]")
    if not pg.evaluate("document.querySelector('[data-rt=accept]').open"): pg.click("[data-rt=accept] > summary")
    pg.click("[data-rt=accept] details.plain > summary")
    pg.click("[data-rt=accept] [data-act=rf-trig][data-v='自分の感情を認めることができた']")
    pg.fill("#add-rf-accept", "相手に背中を押された"); pg.press("#add-rf-accept", "Enter")
    check("恋愛：トリガーのプリセット選択と自由記述で条件を追加", pg.evaluate("D.romanceFlow.trans.accept.conds") == ["自分の感情を認めることができた", "相手に背中を押された"])
    pg.locator("[data-path='romanceFlow.trans.accept.conds.0']").fill("自分の気持ちを認めた")
    check("恋愛：選んだ条件を編集できる", pg.evaluate("D.romanceFlow.trans.accept.conds[0]") == "自分の気持ちを認めた")
    pg.click("[data-rt=accept] [data-act=rf-logic][data-val=and]")
    check("恋愛：成立のしかたを切り替え", "- 受容条件（すべてが成立）：自分の気持ちを認めた／相手に背中を押された" in pg.evaluate("buildMarkdown(D, 2).text"))
    pg.click("[data-rt=accept] [data-act=rf-del][data-i='1']")
    check("恋愛：条件を削除", pg.evaluate("D.romanceFlow.trans.accept.conds") == ["自分の気持ちを認めた"])
    # 信頼と恋愛感情の独立
    ind = pg.evaluate("""() => { const sec = (d, id) => buildMarkdownRaw(d, 2).parts.find(p => p.id === id).text;
      const a = JSON.parse(JSON.stringify(D)), b2 = JSON.parse(JSON.stringify(D)); b2.transition.logic.trust = 'and'; b2.transition.skip = 'allow';
      const c2 = JSON.parse(JSON.stringify(D)); c2.romanceFlow.trans.aware.logic = 'and'; c2.romanceFlow.use.open = false;
      return {romSame:sec(a, 'romance') === sec(b2, 'romance'), progSame:sec(a, 'progress') === sec(c2, 'progress'), progDiff:sec(a, 'progress') !== sec(b2, 'progress')}; }""")
    check("独立：関係段階の状態遷移を変えても恋愛感情の節は変わらない／逆も同じ", ind["romSame"] and ind["progSame"] and ind["progDiff"], str(ind))

    # ---------- 4. 関係段階の状態遷移 ----------
    pg.evaluate(RICH + "; D.autonomy.enabled = true;")
    prog = pg.evaluate("buildMarkdownRaw(D, 2).parts.find(p => p.id === 'progress').text")
    check("状態遷移：成立のしかた・進め方・段階ごとの状態・核・先取りしない旨", all(x in prog for x in ["初期→信頼成立後の条件（いずれか1つが成立）", "信頼成立後→関係深化後の条件（同種の経験が積み重なって成立）", "1回の出来事で2段階以上は動かさない", "### 段階ごとの状態", "- 初期（開始時点）：\n  - 状態：相手を客として扱う。", "  - この段階で初めて現れる振る舞い：自分から雑談を振る。", "どの段階でも維持する人格の核：嘘をつかない。", "現在の態度として先取りしない"]), prog)
    check("状態遷移：自律性ONなら、OOCの指定だけでは段階を変えない旨と拒否・中断の尊重", "OOCの指定だけでは変更しない。ユーザーの拒否・中断の意思表示は常に尊重する。" in prog)
    pg.evaluate("D.transition.skip = 'allow'; D.autonomy.enabled = false;")
    prog2 = pg.evaluate("buildMarkdownRaw(D, 2).parts.find(p => p.id === 'progress').text")
    check("状態遷移：飛び越しを許容／自律性OFFならOOCの行は出さない", "段階を飛び越えてもよい" in prog2 and "OOC" not in prog2, prog2)
    pg.evaluate("D.transition.enabled = false;")
    check("状態遷移：OFFなら従来の進め方", "同種の出来事が重なって初めて次の段階へ進める" in pg.evaluate("buildMarkdownRaw(D, 2).parts.find(p => p.id === 'progress').text"))
    pg.evaluate("D.transition.enabled = true; saveNow(); render(false);")
    tab(pg, "relation")
    pg.click("[data-act=tr-logic][data-key=deepen][data-val=and]")
    check("状態遷移：画面で成立のしかたを変更", pg.evaluate("D.transition.logic.deepen") == "and")
    pg.locator("[data-path='transition.stages.deep.first']").fill("将来の話をする")
    check("状態遷移：段階の振る舞いを入力", "将来の話をする" in pg.evaluate("buildMarkdown(D, 2).text"))

    # ---------- 5. ギャップ ----------
    pg = fresh(b)
    pg.evaluate("D.traits.warmth.use = true; D.traits.warmth.locked = true; D.traits.warmth.common = 2; D.traits.closeness.use = true; D.relation.romance.mode = 'none'; saveNow(); render(false);")
    rom_before = pg.evaluate("JSON.stringify(D.relation) + JSON.stringify(D.romanceFlow)")
    pg.click("#preset-card > summary")
    check("ギャップ：プリセットの種類に「ギャップ」（10種）", pg.locator("[data-act=pre-kind][data-val=gap]").count() == 1 and pg.evaluate("PRESETS.gap.length") == 10)
    pg.click("[data-act=pre-kind][data-val=gap]")
    pg.click("[data-act=pre-pick][data-id=thaw]")
    pg.click("[data-act=pre-choice][data-trait=closeness][data-val=apply]")  # 使用中で値が違う項目は、既定では今の値を残す（既存の競合保護）
    pvt = pg.inner_text("#pre-preview")
    check("ギャップ：適用前に対象・現在→提案・変化量・維持する項目・固定中の項目を表示", all(x in pvt for x in ["冷淡・無関心", "固定中のため変えません", "初期→深化後 +", "維持される人格項目", "固定中の項目（変えない）：温かさ", "恋愛感情の設定・発生条件は変えません"]), pvt)
    pg.click("[data-act=pre-apply]")
    tr = pg.evaluate("({w:D.traits.warmth, c:D.traits.closeness, d:D.traits.disclosure, gap:D.gap, presets:D.presets})")
    check("ギャップ：適用で値が入る（未使用の項目は使用に）", tr["c"]["stages"] == {"initial": 2, "trust": 3, "deep": 4} and tr["d"]["use"] and tr["d"]["stages"] == {"initial": 1, "trust": 2, "deep": 4}, str(tr))
    check("ギャップ：固定中の項目は変えない", tr["w"]["locked"] and tr["w"]["common"] == 2 and tr["w"]["stages"] == {"initial": 2, "trust": 3, "deep": 4}, str(tr["w"]))
    check("ギャップ：態度の説明が空欄なら入る", tr["gap"]["from"] == "冷淡・無関心" and tr["gap"]["to"] == "温かい・親密" and tr["presets"]["gap"] == "thaw")
    check("ギャップ：恋愛感情の設定・発生条件は変えない", pg.evaluate("JSON.stringify(D.relation) + JSON.stringify(D.romanceFlow)") == rom_before)
    pg.click("[data-act=pre-undo]")
    un = pg.evaluate("({c:D.traits.closeness, d:D.traits.disclosure, gap:D.gap, presets:D.presets})")
    check("ギャップ：取り消しで値・態度の説明・適用記録が戻る", un["c"]["stages"] == {"initial": 3, "trust": 3, "deep": 3} and not un["d"]["use"] and un["gap"]["from"] == "" and un["gap"]["to"] == "" and "gap" not in un["presets"], str(un))
    pat = pg.evaluate("""() => { const r = {}; for(const p of ['gradual','gap','subtle']){ D.presets.pattern = p; r[p] = presetRows('gap', 'amae', p).find(x => x.id === 'reliance').to; } D.presets.pattern = 'gradual'; return r; }""")
    check("ギャップ：変化の幅は既存の「関係での変わり方」を再利用", pat["gradual"] == [1, 3, 5] and pat["gap"] == [1, 3, 5] and pat["subtle"] == [1, 2, 3], str(pat))
    # ギャップ設計（説明・適用対象）と出力
    pg.evaluate("D.gap.from = '冷淡'; D.gap.to = '親密'; D.traits.closeness.stages = {initial:1, trust:3, deep:5}; saveNow(); render(false);")
    pg.click("#gap-card > summary")
    pg.click("[data-act=gap-scope][data-val=user]")
    gmd = pg.evaluate("buildMarkdown(D, 2).text")
    check("ギャップ：出力（態度の変化・対象・核は変えない）", "## 関係による態度の変化\n- 態度の変化：初期は「冷淡」、関係深化後は「親密」。\n- 変化の対象：関係深化による態度の変化は{{user}}に対してだけ表す。" in gmd and "人格の核（温かさ）と価値観は変えず" in gmd, gmd)
    check("ギャップ：適用対象が未設定なら対象の行は出さない", "変化の対象" not in pg.evaluate("(() => { const d = JSON.parse(JSON.stringify(D)); d.gap.scope = ''; return buildMarkdown(d, 2).text; })()"))
    bars = pg.inner_text("#gap-bars")
    check("ギャップ：比較バー（大きく変化・固定した核、数値つき）", "大きく変化する項目" in bars and "Lv1→3→5" in bars and "固定された人格の核" in bars and "Lv2→2→2" in bars, bars)
    pg.evaluate("D.traits.specialTreatment.use = true; D.traits.specialTreatment.stages.deep = 5; saveNow();")
    pg.click("[data-act=gap-scope][data-val=all]")
    tab(pg, "relation")
    check("ギャップ：他者全般＋特別扱い高めで警告（設定は変えない）", "誰に対しても甘くなる" in pg.inner_text("#v08-warn") and pg.evaluate("D.gap.scope") == "all")
    # 単独人格：ギャップは非表示・無効（データは保持）
    tab(pg, "tune")
    pg.click("[data-act=structure][data-val=single]")
    check("単独：ギャップのプリセット・設計カードを出さない", pg.locator("[data-act=pre-kind][data-val=gap]").count() == 0 and pg.locator("#gap-card").count() == 0)
    check("単独：ギャップは出力しない・データは保持", "関係による態度の変化" not in pg.evaluate("buildMarkdown(D, 2).text") and pg.evaluate("D.gap.from") == "冷淡")
    pg.evaluate("D.background.items.push({...newBgItem(9), event:'旅に出た', belief:'自由を重んじる'}); D.relation.romance.mode = 'conditional'; D.output.sections.romance = true; D.romanceFlow.enabled = true; D.romanceFlow.trans.aware.conds = ['X'];")
    smd = pg.evaluate("buildMarkdown(D, 2).text")
    check("単独：背景・恋愛感情の状態遷移は使える", "## 人格形成の背景" in smd and "- 自覚条件：X" in smd and "段階別" not in smd, smd)
    pg.click("[data-act=structure][data-val=staged]")
    check("単独→段階：ギャップが戻る", "関係による態度の変化" in pg.evaluate("buildMarkdown(D, 2).text") and pg.locator("#gap-card").count() == 1)
    check("ギャップ：操作中に例外なし", not pg.errs, str(pg.errs))

    # ---------- 6. 配置・再掲・配分 ----------
    pg = fresh(b)
    pg.evaluate(RICH + "; D.autonomy.enabled = true; saveNow();")
    lay = pg.evaluate("""() => { const r = {};
      for(const lv of [1,2,3]){
        const a = buildMarkdownRaw(D, lv), X = {...D, output:{...D.output, layout:'priority'}}, b2 = buildMarkdownRaw(X, lv);
        r[lv] = {a:a.parts.map(p => p.id), b:b2.parts.map(p => p.id), at:a.text, bt:b2.text, bparts:b2.parts.map(p => [p.id, p.text])}; }
      return r; }""")
    for lv in ["1", "2", "3"]:
        L = lay[lv]
        check(f"配置（詳細度{lv}）：重要度優先は冒頭＝核・重要な行動原則・自律性・話し方・現在の状態、末尾は状況別の規則", L["b"][:6] == ["head", "core", "principles", "autonomy", "speech", "state"] and L["b"][-1] == "ifthen", str(L["b"]))
        # 文章の順序だけを変えた比較：現在の状態（新しい要約）と見出しを除くと、行の集合が同じ
        strip = lambda t: sorted(x for x in t.split("\n") if x and not x.startswith("#"))
        bt = "\n".join(t for i, t in L["bparts"] if i != "state")
        check(f"配置（詳細度{lv}）：従来形式と重要度優先形式は順序が違うだけ（現在の状態の要約を除く）", strip(L["at"]) == strip(bt), str(set(strip(L["at"])) ^ set(strip(bt)))[:300])
    check("配置：従来形式の順序は v0.7.0 と同じ並び（新しい節は所定の位置）", lay["2"]["a"] == ["head", "speech", "core", "base", "background", "stages", "gap", "progress", "romance", "autonomy", "ifthen"], str(lay["2"]["a"]))
    check("配置：重要な行動原則は基本人格から移す（重複させない）", lay["2"]["bt"].count("- 率直さ：") == 1 and "## 重要な行動原則（優先度：高）\n- 率直さ：" in lay["2"]["bt"])
    rc = pg.evaluate("""() => { const X = {...D, output:{...D.output, recap:true}}; const t = buildMarkdown(X, 2).text; const Y = {...D, autonomy:{...D.autonomy, enabled:false}, gap:{...D.gap, scope:''}, output:{...D.output, recap:true}};
      const Z = defaultData(); Z.output.recap = true; return {t, off:buildMarkdown(D, 2).text, y:buildMarkdown(Y, 2).text, z:buildMarkdown(Z, 2).text, ids:buildMarkdown(X, 2).parts.map(p => p.id)}; }""")
    recap = rc["t"][rc["t"].index("## 重要事項の再確認"):]
    check("再掲：ONで末尾に短い行動原則（核・優先度高・段階の維持・恋愛・対象・自律性）", rc["ids"][-1] == "recap" and all(x in recap for x in ["人格の核（自尊心）", "優先度の高い行動原則（率直さ）", "現在の段階のまま維持", "恋愛感情の段階も", "{{user}}に対してだけ", "ユーザーの拒否・中断の意思表示は常に尊重する"]), recap)
    check("再掲：OFFなら出さない", "重要事項の再確認" not in rc["off"])
    yr = rc["y"][rc["y"].index("## 重要事項の再確認"):]
    check("再掲：使っていない設定（自律性OFF・対象未設定）は再掲しない", "OOC" not in yr and "{{user}}に対してだけ" not in yr, yr)
    check("再掲：何も使っていなければ節を作らない", "重要事項の再確認" not in rc["z"])
    check("再掲：将来の状態を現在として書かない", "関係深化後の" not in recap and "好意を表明" not in recap)
    al = pg.evaluate("""() => { const X = {...D, output:{...D.output, alloc:true}}; const r = {};
      for(const lv of [1,2,3]){ r['on' + lv] = buildMarkdownRaw(X, lv).parts.find(p => p.id === 'core').text; r['off' + lv] = buildMarkdownRaw(D, lv).parts.find(p => p.id === 'core').text; }
      D.traits.wariness.prio = 'low'; r.lowOn = buildMarkdown({...D, output:{...D.output, alloc:true}}, 3).text; r.lowOff = buildMarkdown(D, 3).text; D.traits.wariness.prio = null; return r; }""")
    check("配分：人格の核はどの詳細度でも詳しく（最小でも補足まで）", al["on1"] == al["on3"] and len(al["on1"]) > len(al["off1"]), str(al)[:300])
    check("配分：優先度「低」は詳細でも圧縮（項目は削らない）", len(al["lowOn"]) < len(al["lowOff"]) and "警戒心：" in al["lowOn"])
    # 画面：切り替え・位置の確認・比較用コピー・表示とコピーの一致
    tab(pg, "output")
    pg.click("#place-box > summary")
    pg.click("[data-act=layout][data-val=priority]")
    pl = pg.inner_text("#place-list")
    check("配置：出力位置の確認（冒頭・中央）", "冒頭" in pl and "中央" in pl and "人格の自律性" in pl, pl)
    pg.click("[data-act-change=recap]")
    check("配置：再掲ONで「末尾」の表示", "末尾" in pg.inner_text("#place-list"))
    pg.evaluate("window.__clip.length = 0"); pg.click("[data-act=copy-md]")
    md = pg.input_value("#md")
    check("配置：表示とコピーが一致（重要度優先＋再掲）", pg.evaluate("window.__clip[0]") == md and md.startswith("# ミナト｜人格設計") and md.rstrip().split("\n\n")[-1].startswith("## 重要事項の再確認"))
    pg.evaluate("window.__clip.length = 0"); pg.click("[data-act=copy-other-layout]")
    other = pg.evaluate("window.__clip[0]")
    check("配置：もう一方の形式（従来）でコピーして比べられる", other == pg.evaluate("buildOutput({...D, output:{...D.output, layout:'classic'}}, UI.level).text") and other != md)
    check("配置：注意書き（原著は人格維持を直接実証していない・未検証の断定をしない）", "直接実証したものではありません" in pg.inner_text("#place-box") and "必ず" not in pg.inner_text("#place-box"))
    # 出力先ごとの文字数判定（新機能ON）
    svc = pg.evaluate("""() => { const out = [];
      for(const [s, t] of [['common',null],['talelynx',null],['chacha',null],['plaitoon','basic11'],['plaitoon','sim'],['plaitoon','custom']]) for(const mode of ['auto','1','2','3']){
        const X = JSON.parse(JSON.stringify(D)); X.output.dest.service = s; if(t) X.output.dest.plaitoon = t; X.meta.budget = 1500;
        const T = buildOutput(X, mode), f = T.fields.find(x => x.kind === 'persona');
        out.push({s, t, mode, countOk:f.count === T.tgt.counter.fn(f.text), over:f.over, limit:f.limit, has:f.text.includes('## 人格形成の背景') && f.text.includes('## 重要事項の再確認'),
          lvOk:mode !== 'auto' || T.level === 1 || (T.tgt.counter.fn(f.text) <= 1500 && (!T.pool || T.pool.count <= T.pool.limit))}); }
      return out; }""")
    check("出力先：6出力先×詳細度4で、新しい節を含み、字数は各サービスの計数方式どおり", all(x["countOk"] and x["has"] for x in svc), str([x for x in svc if not (x["countOk"] and x["has"])][:3]))
    check("出力先：自動選択は予定文字数・サービス上限に収まる詳細度を選ぶ（新しい節も数える）", all(x["lvOk"] for x in svc), str([x for x in svc if not x["lvOk"]][:3]))
    # 節ごとのON／OFF（背景・ギャップ）
    pg.click("#sec-box > summary") if not pg.is_visible("#sec-list") else None
    pg.click("[data-act-change=sec-x][data-sec=background]")
    check("節：人格形成の背景をOFF（設定は保持）", "## 人格形成の背景" not in pg.input_value("#md") and pg.evaluate("D.background.items.length") == 3)
    pg.click("[data-act-change=sec-x][data-sec=gap]")
    check("節：ギャップ設計をOFF", "関係による態度の変化" not in pg.input_value("#md"))
    pg.click("[data-act-change=sec-x][data-sec=background]"); pg.click("[data-act-change=sec-x][data-sec=gap]")
    check("節：ONに戻すと出力", "## 人格形成の背景" in pg.input_value("#md") and "関係による態度の変化" in pg.input_value("#md"))
    # 設定集
    lore = pg.input_value("#lore")
    check("設定集：設定集用の背景だけを別テキストに（キーワード付き）", lore.startswith("## 恩師\nキーワード：恩師, 先生\nミナトの背景：\n- 原体験：恩師に救われた。") and "裏切" not in lore, lore)
    check("設定集：人格設定には入れない", "恩師に救われた" not in pg.input_value("#md"))
    pg.evaluate("window.__clip.length = 0"); pg.click("[data-act=lore-copy]")
    check("設定集：コピー内容が表示と一致", pg.evaluate("window.__clip[0]") == lore)
    pg.click("[data-act=bg-to-lore][data-i='1']")
    check("設定集：優先度「低」の候補を確認して移す", pg.evaluate("D.background.items[1].out") == "lore" and "騎士として育てられた" in pg.input_value("#lore") and "騎士として育てられた" not in pg.input_value("#md"))
    check("設定集：キーワード未設定の警告", "キーワードが未設定" in pg.inner_text("#v08-warn"))
    check("配置・出力画面：例外なし", not pg.errs, str(pg.errs))

    # ---------- 7. 試着 ----------
    pg = fresh(b)
    pg.evaluate(RICH)
    sitchk = pg.evaluate("""() => { const bad = [], n = {c:0};
      for(const sit of SITUATIONS_EXT) for(const sp of SPEECH) for(const st of STAGES) for(const rom of [false, true]){
        const d = JSON.parse(JSON.stringify(D)); d.speech.common = sp.id;
        for(const v of [1, 3, 5]){ TRAITS.forEach(t => { if(!d.traits[t.id].locked) d.traits[t.id].stages[st.id] = v; });
          const r = renderSituation(d, sit, st.id, rom, {preset:'', me:'', you:''}); n.c++;
          if(!r.text || /\\{(me|you|voc)|\\$BG|undefined|null|、、|。。/.test(r.text.replace(/\\{\\{user\\}\\}/g, '')) || /[{}]/.test(r.text.replace(/\\{\\{user\\}\\}/g, '')) || !r.merged.some(m => m.k === 'say')) bad.push([sit.id, sp.id, st.id, v, r.text]); } }
      return {bad:bad.slice(0, 5), n:n.c}; }""")
    check(f"試着：追加4状況×口調8×段階3×恋愛×値3（{sitchk['n']}通り）で台詞が壊れない", not sitchk["bad"], str(sitchk["bad"]))
    rej = pg.evaluate("ALL_SITUATIONS.find(s => s.id === 'rejected') && STAGES.every(st => renderSituation(D, sitOf('rejected'), st.id, true, {}).text.endsWith('（それ以上は踏み込まず、相手の意思に任せる）'))")
    check("試着：拒否されたときは、どの段階でも踏み込まず相手の意思に任せる", rej)
    wd = pg.evaluate("renderSituation(D, sitOf('wound'), 'initial', false, {}).text")
    check("試着：過去の傷に触れられたとき、背景の「反応」を使う", wd.startswith("（表情を硬くし、話題を変える）"), wd)
    tab(pg, "preview")
    pg.click("[data-act=sit][data-id=favor]")
    check("試着：追加の状況を選べる（3段階）", pg.locator("#pv-cards .pv").count() == 3)
    pg.click("[data-act=pv-cmp][data-val=romance]")
    titles = pg.locator("#pv-cards .pv h3").all_inner_texts()
    check("試着：恋愛感情段階の比較（なし・無自覚・自覚・抑制・表明）", titles == ["恋愛感情なし", "無自覚な好意があるとき", "恋愛感情を自覚したとき", "自覚後も好意を抑制しているとき", "好意を表明できるとき"], str(titles))
    before = pg.evaluate("JSON.stringify(D.relation) + JSON.stringify(D.traits)")
    pg.click("#pv-cards .pv:nth-child(5) [data-act=ex-add2]") if pg.locator("#pv-cards .pv").count() >= 5 else None
    pg.locator("[data-act=ex-add2][data-k='rom:open']").click()
    ex = pg.evaluate("exList(D).slice(-1)[0]")
    check("試着：比較の会話例を追加（設定は書き換えない）", ex["label"] == "好意を向けられた（好意を表明できるとき）" and ex["char"] and pg.evaluate("JSON.stringify(D.relation) + JSON.stringify(D.traits)") == before, str(ex))
    pg.click("[data-act=pv-cmp][data-val=gap]")
    gt = pg.locator("#pv-cards .pv h3").all_inner_texts()
    check("試着：ギャップの比較（ほかの人物と{{user}}）", len(gt) == 2 and gt[0].startswith("ほかの人物に対して（初期") and gt[1].startswith("{{user}}に対して"), str(gt))
    pg.evaluate("window.__clip.length = 0"); pg.click("[data-act=copy-ex2][data-k='gap:user']")
    check("試着：比較の会話例をコピー", pg.evaluate("window.__clip[0]") == pg.evaluate("pvRender('gap:user').r.text"))
    check("試着：LLMによるシミュレーションではない旨", "LLM" in pg.inner_text("#app"))
    pg.click("#pvmd-box summary"); pg.click("[data-act=pv-scope][data-val=all]")
    check("試着：全状況のMarkdownに追加の状況も入る", "## ユーザーから拒否された" in pg.input_value("#pvmd"))
    pg.evaluate("D.relation.romance.mode = 'none'; UI.pvCmp = 'romance'; render(false);")
    check("試着：恋愛なしなら恋愛感情の比較は出さない", pg.locator("[data-act=pv-cmp][data-val=romance]").count() == 0 and pg.locator("#pv-cards .pv").count() == 3)
    check("試着：例外なし", not pg.errs, str(pg.errs))

    # ---------- 8. 空欄・未設定 ----------
    em = pg.evaluate("""() => { const d = defaultData(); Object.keys(d.output.sections).forEach(k => d.output.sections[k] = true); d.relation.romance.mode = 'conditional';
      d.romanceFlow.enabled = true; d.transition.enabled = true; d.background.items.push(newBgItem(1)); d.gap.scope = 'custom';
      d.output.layout = 'priority'; d.output.recap = true; return [1,2,3].map(l => buildMarkdown(d, l).text); }""")
    check("空欄：未設定の節・空の見出し・「（未設定）」を出さない", all(("（未設定）" not in t and "## 人格形成の背景" not in t and "関係による態度の変化" not in t and not re.search(r"^##+ .*\n(\n|$)", t, re.M) and "：\n\n" not in t) for t in em), em[1])

    # ---------- 9. モバイル表示・操作 ----------
    for (w, h, tag) in [(390, 844, "mobile"), (320, 640, "narrow"), (1280, 900, "pc")]:
        pl = fresh(b, w, h)
        pl.evaluate(RICH + "; UI.open.background = true; UI.open.gapcard = true; UI.open.bg1 = true; UI.open['rt-emerge'] = true; UI.open.place = true; D.output.layout = 'priority'; D.output.recap = true; saveNow(); render(false);")
        for t in ["tune", "relation", "preview", "output"]:
            tab(pl, t)
            if t == "preview":
                for c in ["stage", "romance", "gap"]:
                    pl.click(f"[data-act=pv-cmp][data-val={c}]")
                    if not no_overflow(pl): check(f"モバイル：横スクロールなし {tag}/preview/{c}", False)
            check(f"モバイル：横スクロールなし {tag}/{t}", no_overflow(pl), pl.evaluate("document.documentElement.scrollWidth"))
            if SHOTS: pl.screenshot(path=str(SHOTS / f"v080_{tag}_{t}.png"), full_page=True)
        tab(pl, "tune")
        for sel in ["[data-act=bg-add]", "[data-act=gap-scope][data-val=trusted]"]:
            loc = pl.locator(sel).first; loc.scroll_into_view_if_needed(); bb = loc.bounding_box()
            check(f"操作：{sel} が画面内で押せる大きさ（{tag}）", bb and bb["x"] >= 0 and bb["x"] + bb["width"] <= w and bb["height"] >= 30, str(bb))
            loc.click()
        check(f"操作：背景を追加・対象を変更（{tag}）", pl.evaluate("D.background.items.length") == 4 and pl.evaluate("D.gap.scope") == "trusted")
        pl.click("#bg-card > summary"); pl.wait_for_timeout(150)
        check(f"操作：折り畳みの開閉を記録（{tag}）", pl.evaluate("UI.open.background") is False)
        tab(pl, "relation")
        sw = pl.locator("[data-act-change=tr-on]"); sw.scroll_into_view_if_needed(); sw.click()
        check(f"操作：状態遷移のスイッチ（{tag}）", pl.evaluate("D.transition.enabled") is False and pl.locator("[data-act=tr-skip]").count() == 0)
        check(f"操作：例外なし（{tag}）", not pl.errs, str(pl.errs))

    # ---------- 10. 出力先：ZETA・Zetter と出力先ごとの案内 ----------
    pz = fresh(b)
    pz.evaluate(RICH + "; D.output.layout = 'priority'; D.output.recap = true; saveNow();")
    tab(pz, "output")
    names = pz.locator("#o-dest button").all_inner_texts()
    check("出力先：6つの選択肢にサービス名を明示", names == ["共通（汎用）", "ZETA", "Zetter", "Talelynx", "チャチャ", "Plaitoon"], str(names))
    persona0 = pz.evaluate("JSON.stringify({t:D.traits, r:D.relation, b:D.background, f:D.romanceFlow, tr:D.transition, g:D.gap, s:D.speech, p:D.pron, m:D.meta.budget})")
    for svc in ["common", "zeta", "zetter", "talelynx", "chacha", "plaitoon"]:
        pz.click(f"[data-act=dest][data-val={svc}]"); pz.wait_for_selector("#fields section")
        g = pz.inner_text("#dest-card")
        check(f"出力先：{svc} の案内（貼り付ける欄・上限と数え方・設定集・会話例）", all(x in g for x in ["貼り付ける欄", "文字数の上限と数え方", "設定集（ロアブック）", "会話例"]), g[:200])
        check(f"出力先：{svc} 横スクロールなし", no_overflow(pz))
    check("出力先：切り替えても人格設計データ・予定文字数は変わらない", pz.evaluate("JSON.stringify({t:D.traits, r:D.relation, b:D.background, f:D.romanceFlow, tr:D.transition, g:D.gap, s:D.speech, p:D.pron, m:D.meta.budget})") == persona0)
    # ZETA
    pz.click("[data-act=dest][data-val=zeta]"); pz.wait_for_selector("#f-zprofile")
    zg = pz.inner_text("#dest-card")
    check("ZETA：プロットのキャラクターのプロフィール欄・合計2,400字（公式告知）・数え方は未確認と表示", "キャラクターのプロフィール" in zg and "2,400字" in zg and "公式告知" in zg and "未確認" in zg)
    check("ZETA：設定集の上限は利用者の実機確認による値と表示", "最大50件" in zg and "500字" in zg and "5語" in zg and "実機確認" in zg)
    check("ZETA：人格設定だけで全体を使い切ることを推奨しない旨", "使い切ることはおすすめしません" in zg)
    same = pz.evaluate("""() => { const r = {}; for(const lv of ['1','2','3']){ const X = JSON.parse(JSON.stringify(D)); X.output.dest.exInline = false;
      for(const s of ['zeta','zetter']){ X.output.dest.service = s; r[s + lv] = buildOutput(X, lv).fields[0].text === buildMarkdown(X, +lv).text; } } return r; }""")
    check("ZETA・Zetter：人格Markdownは共通Markdownと同じ処理（詳細度3種）", all(same.values()), str(same))
    zc = pz.evaluate("""() => { const X = defaultData(); ['warmth','pride','candor'].forEach(id => X.traits[id].use = true); X.output.dest.service = 'zeta'; X.output.dest.exInline = false;
      const T0 = buildOutput(X, '2'), n = T0.fields[0].count; const r = {n, pc0:T0.pool.count, lim:T0.pool.limit};
      X.output.dest.zetaReserve = 2400 - n; const T1 = buildOutput(X, '2'); r.at = [T1.pool.count, T1.pool.over, T1.pool.rem];
      X.output.dest.zetaReserve = 2400 - n + 1; const T2 = buildOutput(X, '2'); r.over = [T2.pool.count, T2.pool.over, T2.svcOver];
      X.output.dest.zetaReserve = 1500; X.meta.budget = 0; const T3 = buildOutput(X, 'auto'); r.auto = [T3.level, T3.pool.count, T3.fields[0].count];
      return r; }""")
    check("ZETA：合計は人格設定＋ほかの欄の予定字数", zc["pc0"] == zc["n"] and zc["lim"] == 2400, str(zc))
    check("ZETA：上限ちょうどは超過でない／1字超えで超過", zc["at"] == [2400, False, 0] and zc["over"][1] and zc["over"][2], str(zc))
    check("ZETA：自動選択はほかの欄の予定字数を差し引いて収まる詳細度を選ぶ", zc["auto"][1] <= 2400 or zc["auto"][0] == 1, str(zc))
    pz.fill("#d-reserve", "800")
    check("ZETA：ほかの欄の予定字数を入力（予定文字数は書き換えない）", pz.evaluate("D.output.dest.zetaReserve") == 800 and pz.evaluate("D.meta.budget") == 2000 and "うちほかの欄（予定）" in pz.inner_text("#counter"))
    pz.fill("#d-reserve", "0")
    cw = pz.inner_text("#counter")
    check("ZETA：ほかの欄が0字なら、人格設定だけで上限まで使う前提だと警告", "0字のため、人格設定だけで" in cw and "数え方" in cw, cw)
    pz.evaluate("window.__clip.length = 0"); pz.click("[data-act=copy-field][data-ta=f-zprofile]")
    zv = pz.input_value("#f-zprofile")
    check("ZETA：表示とコピーが一致し、v0.8.0の配置・再掲を含む", pz.evaluate("window.__clip[0]") == zv and zv.rstrip().split("\n\n")[-1].startswith("## 重要事項の再確認") and "## 重要な行動原則" in zv)
    pz.evaluate("D.background.items[2].keys = 'a,b,c,d,e,f'; D.background.items[2].event = 'あ'.repeat(520); saveNow(); render(true);")
    lc = pz.inner_text("#lore-card")
    check("ZETA：設定集のキーワード5語・本文500字の超過を警告（削らない）", "5語を超えています" in lc and "500字を超えています" in lc and pz.evaluate("D.background.items[2].keys") == "a,b,c,d,e,f", lc[:300])
    # Zetter
    pz.click("[data-act=dest][data-val=zetter]"); pz.wait_for_selector("#f-zsetting")
    tg = pz.inner_text("#dest-card")
    check("Zetter：性格・設定欄・全体20,000字（利用者の確認・公式未確認）・ナレーター欄なし", "性格・設定" in tg and "20,000字" in tg and "公式の仕様文書では未確認" in tg and "ナレーター専用の欄はありません" in tg)
    check("Zetter：設定集の上限は未確認と表示し、ZETAの上限チェックはしない", "確認できていません" in tg and "5語を超えています" not in pz.inner_text("#lore-card"))
    pz.fill("#d-reserve", "3000")
    check("Zetter：ほかの欄の予定字数はZETAと別に保存", pz.evaluate("[D.output.dest.zetterReserve, D.output.dest.zetaReserve]") == [3000, 0])
    pz.click("[data-act-change=dest-exinline]")
    check("Zetter：会話例を本文に含められる（字数に算入）", pz.evaluate("D.output.dest.exInline") is True)
    # 互換
    cm = pz.evaluate("""() => { const a = migrate({v:6, traits:{}, output:{dest:{service:'chacha'}}}), b2 = migrate({v:9, traits:{}, output:{dest:{service:'unknown', zetaReserve:'-5', zetterReserve:'1200'}}});
      return [a.output.dest.service, a.output.dest.zetaReserve, b2.output.dest.service, b2.output.dest.zetaReserve, b2.output.dest.zetterReserve]; }""")
    check("出力先：旧データの出力先はそのまま・不明な値は共通・予定字数は0以上の整数に", cm == ["chacha", 0, "common", 0, 1200], str(cm))
    for (w, h, tag) in [(320, 640, "narrow"), (390, 844, "mobile")]:
        pm = fresh(b, w, h); tab(pm, "output")
        bbs = [pm.locator(f"[data-act=dest][data-val={v}]").bounding_box() for v in ["common", "zeta", "zetter", "talelynx", "chacha", "plaitoon"]]
        check(f"出力先：6つのボタンが画面内で押せる大きさ（{tag}）", all(bb and bb["x"] >= 0 and bb["x"] + bb["width"] <= w and bb["height"] >= 36 for bb in bbs), str(bbs))
        pm.click("[data-act=dest][data-val=zeta]"); pm.wait_for_selector("#f-zprofile")
        check(f"出力先：ZETA選択後も横スクロールなし（{tag}）", no_overflow(pm))
        if SHOTS: pm.locator("#dest-card").screenshot(path=str(SHOTS / f"dest_zeta_{tag}.png"))
        check(f"出力先：例外なし（{tag}）", not pm.errs, str(pm.errs))
    check("出力先：操作中に例外なし", not pz.errs, str(pz.errs))

    b.close()

fails = [r for r in results if not r[1]]
print(f"\nv0.8.0 動作テスト: {len(results) - len(fails)} / {len(results)} 件成功")
for n, ok, d in results:
    if not ok: print("  失敗:", n, str(d)[:300])
sys.exit(1 if fails else 0)
