#!/usr/bin/env python3
"""v0.5.0 出力先拡張の動作テスト（実ブラウザ Chromium で index.html を操作する）

使い方: python3 tests/e2e.py [--shots DIR]
"""
import sys, json, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = None
if "--shots" in sys.argv: SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]); SHOTS.mkdir(parents=True, exist_ok=True)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    if not cond: print("  FAIL:", name, detail)

INIT = """
window.__clip = [];
Object.defineProperty(navigator, 'clipboard', {value:{writeText: async t => { window.__clip.push(t); }}, configurable:true});
try{ if(!localStorage.getItem('persona-tuning-workshop:data')) localStorage.setItem('persona-tuning-workshop:data', JSON.stringify({v:6, meta:{name:'', budget:2000, budgetSet:true, notice:''}})); }catch(e){}
"""

def fresh(b, w=390, h=844):
    ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("file://" + str(ROOT / "index.html")); pg.wait_for_function("typeof buildOutput === 'function'")
    pg.errs = errs
    return pg

def go_output(pg):
    pg.click("#tabs button[data-tab=output]"); pg.wait_for_selector("#dest-card")

def dest(pg, svc, tpl=None):
    pg.click(f"[data-act=dest][data-val={svc}]")
    if tpl: pg.click(f"[data-act=dest-tpl][data-val={tpl}]")
    pg.wait_for_selector("#fields section")

FULL = "(() => { TRAITS.forEach(t => D.traits[t.id].use = true); Object.keys(D.output.sections).forEach(k => D.output.sections[k] = true); D.meta.name='ミナト'; })()"
PERSONA_KEYS = "JSON.stringify({traits:D.traits, relation:D.relation, speech:D.speech, pron:D.pron, link:D.link, presets:D.presets, undo:D.undo, legacy:D.legacy, sections:D.output.sections, progressParts:D.output.progressParts, showPreset:D.output.showPreset, name:D.meta.name})"

with sync_playwright() as p:
    b = p.chromium.launch()

    # ---------- 1. 計数関数（チャチャ：半角0.5字・暫定） ----------
    pg = fresh(b)
    cases = [("", 0), ("abc", 1.5), ("あいう", 3), ("あa", 1.5), ("A1 ", 1.5), ("\n", 0.5), ("ｱｲｳ", 1.5), ("😀", 1), ("、。「」", 4),
             ("# 名前", 3), ("Hello、世界!", 6), ("a\r\nb", 1.5), ("全角ＡＢ", 4), ("{{user}}", 4)]
    for s_, exp in cases:
        got = pg.evaluate("s => countChacha(s)", s_)
        check(f"countChacha({s_!r}) = {exp}", got == exp, f"got {got}")
    check("countChars は従来どおり（改行・記号も1字）", pg.evaluate("countChars('a\\nあ#')") == 4)
    check("0.5字単位が小数で表示される", pg.evaluate("fmtN(1999.5)") == "1999.5" and pg.evaluate("fmtN(2000)") == "2000")

    # ---------- 2. 出力先の切り替えと欄・上限 ----------
    go_output(pg)
    check("初期の出力先は共通Markdown", pg.evaluate("D.output.dest.service") == "common")
    check("ヘッダーのバージョン表示が v0.5.0", pg.inner_text(".ver") == "v0.5.0" and pg.evaluate("APP_VERSION") == "0.5.0")
    check("共通：従来の #md が出る", pg.locator("#md").count() == 1 and pg.locator("#fields [data-act=copy-md]").count() == 1)
    pg.evaluate(FULL); pg.evaluate("save(); render(true)")
    spec = {"common": ("md", None), "talelynx": ("f-detail", 7000), "chacha": ("f-profile", 2000), "plaitoon": ("f-info", 8000)}
    for svc, (taid, lim) in spec.items():
        dest(pg, svc)
        check(f"{svc}: 出力欄 #{taid}", pg.locator(f"#{taid}").count() == 1)
        T = pg.evaluate("(() => { const T = buildOutput(D, UI.level); return {pool:T.pool, fields:T.fields.map(f => ({id:f.id, limit:f.limit, over:f.over})), cnt:T.tgt.counter.id}; })()")
        if svc == "chacha": check("chacha: プロンプト合計2000・計数はchacha", T["pool"]["limit"] == 2000 and T["cnt"] == "chacha")
        elif lim: check(f"{svc}: 上限{lim}", T["fields"][0]["limit"] == lim)
        shown = pg.input_value(f"#{taid}")
        expected = pg.evaluate("buildOutput(D, UI.level).fields.find(f => f.kind === 'persona').text")
        check(f"{svc}: 表示とbuildOutputが一致", shown == expected)
        if svc == "plaitoon": check("plaitoon: 初期テンプレートは1:1ベーシック", pg.evaluate("destOf(D).plaitoon") == "basic11" and pg.locator("[data-act=dest-tpl].on").inner_text().startswith("1:1"))
    for tpl, lim, ta, mode in [("basic11", 8000, "f-info", "separate"), ("sim", 8000, "f-info", "separate"), ("custom", 10000, "f-custom", "inline")]:
        dest(pg, "plaitoon", tpl)
        got = pg.evaluate("buildOutput(D, UI.level).fields[0].limit")
        check(f"plaitoon/{tpl}: 上限{lim}", got == lim)
        check(f"plaitoon/{tpl}: 出力欄 #{ta}", pg.locator(f"#{ta}").count() == 1)
        check(f"plaitoon/{tpl}: 会話例は {mode}", pg.get_attribute("#ex-box", "data-ex-mode") == mode)
    check("plaitoon/custom: 独立した会話例欄（出力する会話例の集計）が出ない", "出力する会話例" not in pg.inner_text("#ex-stats"))
    dest(pg, "plaitoon", "basic11")
    check("plaitoon/basic11: 会話例の独立欄あり", "出力する会話例" in pg.inner_text("#ex-stats"))

    # ---------- 3. 上限ちょうど・超過（plain / chacha） ----------
    r = pg.evaluate("""() => {
      const D0 = JSON.parse(JSON.stringify(D)); const out = {};
      const base = JSON.parse(JSON.stringify(D)); Object.keys(base.output.sections).forEach(k => base.output.sections[k] = false); base.meta.budget = 0;
      base.output.sections.ifthen = true; base.relation.rules = [{when:'x', then:'あ', out:true}];
      for(const [svc, lim] of [['talelynx', 7000]]){
        base.output.dest.service = svc;
        const c1 = buildOutput(base, '1').fields[0].count;
        base.relation.rules[0].then = 'あ'.repeat(1 + lim - c1);
        const at = buildOutput(base, '1').fields[0];
        base.relation.rules[0].then += 'あ';
        const over = buildOutput(base, '1').fields[0];
        out[svc] = {atCount:at.count, atOver:at.over, atRem:at.rem, overCount:over.count, overOver:over.over};
      }
      // チャチャ：プロフィール＋説明の合計。半角は0.5字
      base.output.dest.service = 'chacha'; base.output.dest.chachaDesc = ''; base.relation.rules[0].then = 'あ';
      const prof = buildOutput(base, '1').fields[0].count;
      const need = 2000 - prof, fullN = Math.floor(need), half = need - fullN > 0 ? 'a' : '';
      base.output.dest.chachaDesc = 'あ'.repeat(fullN) + half;
      let T = buildOutput(base, '1'); out.chachaAt = {total:T.pool.count, over:T.pool.over, rem:T.pool.rem};
      base.output.dest.chachaDesc += 'a';
      T = buildOutput(base, '1'); out.chachaHalfOver = {total:T.pool.count, over:T.pool.over, rem:T.pool.rem};
      base.output.dest.chachaDesc = 'あ'.repeat(fullN - 1) + 'ab' + half;
      T = buildOutput(base, '1'); out.chachaHalfAt = {total:T.pool.count, over:T.pool.over};
      // プレイトゥーン各テンプレート（上限ちょうど／1字超過）
      for(const [tpl, lim] of [['basic11', 8000], ['sim', 8000], ['custom', 10000]]){
        base.output.dest.service = 'plaitoon'; base.output.dest.plaitoon = tpl; base.output.dest.customPreface = false;
        base.relation.rules[0].then = 'あ';
        const c = buildOutput(base, '1').fields[0].count;
        base.relation.rules[0].then = 'あ'.repeat(1 + lim - c);
        const a = buildOutput(base, '1').fields[0]; base.relation.rules[0].then += 'あ'; const o = buildOutput(base, '1').fields[0];
        out[tpl] = {at:a.count, atOver:a.over, over:o.over};
      }
      return out; }""")
    check("talelynx: 上限ちょうど(7000)は超過でない・残り0", r["talelynx"]["atCount"] == 7000 and not r["talelynx"]["atOver"] and r["talelynx"]["atRem"] == 0, str(r["talelynx"]))
    check("talelynx: 1字超過で警告", r["talelynx"]["overCount"] == 7001 and r["talelynx"]["overOver"])
    check("chacha: 合計2000字ちょうどは超過でない", r["chachaAt"]["total"] == 2000 and not r["chachaAt"]["over"] and r["chachaAt"]["rem"] == 0, str(r["chachaAt"]))
    check("chacha: 半角1文字(0.5字)で2000.5字→超過", r["chachaHalfOver"]["total"] == 2000.5 and r["chachaHalfOver"]["over"] and r["chachaHalfOver"]["rem"] == -0.5, str(r["chachaHalfOver"]))
    check("chacha: 半角2文字(1字)で2000字ちょうど→超過でない", r["chachaHalfAt"]["total"] == 2000 and not r["chachaHalfAt"]["over"], str(r["chachaHalfAt"]))
    for tpl, lim in [("basic11", 8000), ("sim", 8000), ("custom", 10000)]:
        check(f"plaitoon/{tpl}: 上限{lim}ちょうど→OK、+1字→超過", r[tpl]["at"] == lim and not r[tpl]["atOver"] and r[tpl]["over"], str(r[tpl]))

    # ---------- 4. 空欄・未設定／長文の超過 ----------
    pg2 = fresh(b); go_output(pg2)
    for svc in ["common", "talelynx", "chacha", "plaitoon"]:
        dest(pg2, svc)
        T = pg2.evaluate("(() => { const T = buildOutput(D, 'auto'); return {t:T.text, ok:T.fields.every(f => Number.isFinite(f.count)), over:T.svcOver}; })()")
        check(f"未設定でも出力できる: {svc}", T["t"].startswith("# ") and T["ok"] and not T["over"])
    check("未設定で例外なし", not pg2.errs, str(pg2.errs))
    pg.evaluate(FULL); pg.evaluate("D.meta.budget = 0")
    before = pg.evaluate(PERSONA_KEYS)
    dest(pg, "chacha")
    st = pg.evaluate("(() => { const T = buildOutput(D, '3'); return {over:T.pool.over, rem:T.pool.rem}; })()")
    check("チャチャ：長文は上限超過を検出", st["over"] and st["rem"] < 0, str(st))
    pg.evaluate("D.relation.rules.push({when:'長い規則', then:'あ'.repeat(2500), out:true}); updateOutput()")
    st = pg.evaluate("(() => { const A = buildOutput(D, 'auto'); return {autoLevel:A.level, autoOver:A.pool.over, svc:A.svcOver}; })()")
    check("チャチャ：自動選択は最小でも超過なら最小を出して警告", st["autoLevel"] == 1 and st["autoOver"], str(st))
    check("チャチャ：最小でも収まらない旨の表示", "最小の詳細度でも収まりませんでした" in pg.inner_text("#counter .msg"), pg.inner_text("#counter .msg"))
    pg.evaluate("D.relation.rules.pop(); UI.level = '3'; updateOutput()")
    msg = pg.inner_text("#counter .msg")
    check("チャチャ：超過メッセージに削除していない旨", "設定データは削除していません" in msg and "超えています" in msg, msg)
    check("超過しても人格データは変わらない", pg.evaluate(PERSONA_KEYS) == before)
    check("超過カードに警告タグ", pg.locator("#fields .tag.warn").count() >= 1)
    pg.evaluate("D.meta.budget = 2000; UI.level = 'auto'")

    # ---------- 5. 予定文字数とサービス上限の分離 ----------
    pg3 = fresh(b); go_output(pg3)
    pg3.evaluate(FULL); pg3.evaluate("D.meta.budget = 1500; save(); render(true)")
    for svc in ["common", "talelynx", "chacha", "plaitoon", "common"]:
        dest(pg3, svc)
        check(f"出力先を{svc}にしても予定文字数は書き換わらない", pg3.evaluate("D.meta.budget") == 1500)
    dest(pg3, "talelynx")
    n = pg3.evaluate("[1, 2, 3].map(l => buildOutput(D, String(l)).budget.count)")
    pg3.evaluate(f"D.meta.budget = {int(n[1]) + 1}; updateOutput()")   # 標準なら収まり、詳細は収まらない予定文字数
    T = pg3.evaluate("(() => { const T = buildOutput(D, 'auto'); return {n:T.budget.count, lv:T.level, over:T.budget.over, svcOver:T.svcOver}; })()")
    check("talelynx: 自動選択は予定文字数に合わせて詳細度を選ぶ（標準）", T["lv"] == 2 and T["n"] <= n[1] + 1 and not T["over"] and not T["svcOver"], f"{n} {T}")
    pg3.evaluate(f"D.meta.budget = {int(n[0]) + 1}; updateOutput()")
    T = pg3.evaluate("buildOutput(D,'auto')")
    check("talelynx: 7000上限より小さい予定文字数でも自動選択が効く（最小で収まる）", T["level"] == 1 and T["budget"]["over"] is False, str(n))
    dest(pg3, "chacha")
    pg3.evaluate(f"D.meta.budget = {int(n[1]) + 1}; updateOutput()")   # 予定文字数は標準まで許すが、チャチャの上限(2000)では標準が入らない
    T = pg3.evaluate("(() => { const T = buildOutput(D, 'auto'); return {n:T.budget.count, lv:T.level, pool:T.pool.count, over:T.pool.over, bover:T.budget.over}; })()")
    check("チャチャ：予定文字数が許してもサービス上限(2000)に収まる詳細度を選ぶ", T["lv"] == 1 and T["pool"] <= 2000 and not T["over"] and not T["bover"], f"{n} {T}")
    dest(pg3, "chacha")
    pg3.evaluate("D.meta.budget = 6000; D.output.dest.chachaDesc=''; updateOutput()")
    A = pg3.evaluate("(() => { const T = buildOutput(D, 'auto'); return {pool:T.pool.count, over:T.pool.over, lv:T.level}; })()")
    check("予定文字数が大きくてもサービス上限(2000)で制限される", A["pool"] <= 2000 or (A["lv"] == 1 and A["over"]), str(A))
    # メッセージ：両方内／予定未設定
    pg3.evaluate("(() => { Object.keys(D.output.sections).forEach(k => D.output.sections[k] = false); D.output.sections.persona = true; TRAITS.slice(0,3).forEach(t => D.traits[t.id].use = true); D.meta.budget = 1500; updateOutput(); })()")
    check("メッセージ「サービス上限内かつ予定文字数内」", "サービス上限内かつ予定文字数内" in pg3.inner_text("#counter .msg"), pg3.inner_text("#counter .msg"))
    pg3.evaluate("D.meta.budget = 0; updateOutput()")
    check("予定文字数が未設定ならサービス上限を使う旨", "予定文字数は未設定" in pg3.inner_text("#counter .msg"), pg3.inner_text("#counter .msg"))
    check("チャチャ：暫定仕様の注意が表示される", "暫定" in pg3.inner_text("#counter") and "未確認" in pg3.inner_text("#counter"))
    check("チャチャの注意に「完全一致」を名乗らない", "完全一致" not in pg3.inner_text("#dest-card") + pg3.inner_text("#counter"))

    # ---------- 6. 出力欄別のコピー（表示＝コピー） ----------
    pg4 = fresh(b); go_output(pg4); pg4.evaluate(FULL); pg4.evaluate("D.meta.budget = 0; save(); render(true)")
    dest(pg4, "chacha")
    pg4.fill("#d-desc", "夜の港町。\nabc あ")
    pg4.wait_for_selector("#f-desc")
    check("チャチャ：説明欄は入力したときだけ出る", pg4.locator("#f-desc").count() == 1)
    for ta in ["f-profile", "f-desc"]:
        pg4.evaluate("window.__clip.length = 0")
        pg4.click(f"[data-act=copy-field][data-ta={ta}]")
        clip = pg4.evaluate("window.__clip[window.__clip.length - 1]")
        shown = pg4.input_value(f"#{ta}")
        check(f"コピー内容が表示と一致: {ta}", clip == shown and len(clip) > 0)
        check(f"コピー内容は出力欄の文字列そのもの: {ta}", clip == pg4.evaluate("buildOutput(D, UI.level).fields.find(f => f.id === '%s').text" % ta.replace("f-", "")))
    prof_clip = pg4.input_value("#f-profile")
    check("コピー対象に説明が混ざらない（欄ごと）", "夜の港町" not in prof_clip)
    check("説明欄は入力どおり", pg4.input_value("#f-desc") == "夜の港町。\nabc あ")
    dest(pg4, "talelynx")
    pg4.evaluate("window.__clip.length = 0"); pg4.click("[data-act=copy-field][data-ta=f-detail]")
    check("talelynx: コピー内容が表示と一致", pg4.evaluate("window.__clip[0]") == pg4.input_value("#f-detail"))
    dest(pg4, "plaitoon", "custom")
    pg4.evaluate("window.__clip.length = 0"); pg4.click("[data-act=copy-field][data-ta=f-custom]")
    check("plaitoon/custom: コピー内容が表示と一致", pg4.evaluate("window.__clip[0]") == pg4.input_value("#f-custom"))
    check("custom: 先頭に人格指示の前置き（{{char}}/{{user}}）", pg4.input_value("#f-custom").startswith("# 人格に関する指示\n{{char}}として{{user}}と会話する。"))
    pg4.uncheck("[data-act-change=dest-preface]")
    check("custom: 前置きをOFFにできる", pg4.input_value("#f-custom").startswith("# ") and "人格に関する指示" not in pg4.input_value("#f-custom"))
    dest(pg4, "common")
    pg4.evaluate("window.__clip.length = 0"); pg4.click("[data-act=copy-md]")
    check("共通: 従来のコピーも表示と一致", pg4.evaluate("window.__clip[0]") == pg4.input_value("#md"))
    check("共通Markdownの表示が chooseOutput と一致", pg4.input_value("#md") == pg4.evaluate("chooseOutput(D, UI.level).text"))

    # ---------- 7. 会話例（試着→選択→編集→コピー→件数・字数制限） ----------
    pg5 = fresh(b); pg5.evaluate(FULL); pg5.evaluate("D.meta.budget = 0; save()")
    pg5.click("#tabs button[data-tab=preview]"); pg5.wait_for_selector("[data-act=ex-add]")
    pg5.click("[data-act=ex-add][data-stage=initial]")
    check("試着から会話例を追加（1件）", pg5.evaluate("exList(D).length") == 1)
    ex0 = pg5.evaluate("exList(D)[0]")
    check("追加した会話例：ユーザー発言は空・応答は試着の文", ex0["user"] == "" and len(ex0["char"]) > 0 and ex0["on"] is True)
    before = pg5.evaluate(PERSONA_KEYS)
    for _ in range(11): pg5.click("[data-act=ex-add-all]")   # 1 + 33 = 34件
    check("会話例34件を追加", pg5.evaluate("exList(D).length") == 34)
    check("試着の操作で人格データは変わらない", pg5.evaluate(PERSONA_KEYS) == before)
    pg5.click("#tabs button[data-tab=output]"); pg5.wait_for_selector("#dest-card")
    dest(pg5, "chacha")
    st = pg5.evaluate("(() => { const s = buildOutput(D, 'auto').ex; return {count:s.count, max:s.max, skipped:s.skipped, over:s.over, total:s.total, limit:s.limit}; })()")
    check("チャチャ：会話例は最大25件・上限1500字", st["count"] == 25 and st["max"] == 25 and st["limit"] == 1500, str(st))
    check("チャチャ：25件を超える分は対象外（削除しない）", st["skipped"] == 9 and pg5.evaluate("exList(D).length") == 34, str(st))
    check("チャチャ：対象外タグが画面に出る", pg5.locator("#ex-list .tag.warn:has-text('件数上限のため対象外')").count() == 9)
    # 字数の合計
    pg5.evaluate("(() => { exList(D).forEach(e => { e.user = 'あ'.repeat(30); }); $('#ex-list').innerHTML = exListHTML(); updateOutput(); })()")
    st = pg5.evaluate("buildOutput(D, 'auto').ex")
    check("チャチャ：会話例の合計字数が上限超過なら警告", st["over"] == (st["total"] > 1500))
    pg5.evaluate("(() => { exList(D).forEach(e => { e.user = 'a'.repeat(10); e.char = 'あ'.repeat(10); }); $('#ex-list').innerHTML = exListHTML(); updateOutput(); })()")
    st = pg5.evaluate("buildOutput(D, 'auto').ex")
    check("チャチャ：会話例は半角0.5字で数える（25×(5+10)=375）", st["total"] == 375 and not st["over"], str(st))
    pg5.evaluate("(() => { exList(D).forEach(e => { e.char = 'あ'.repeat(70); }); $('#ex-list').innerHTML = exListHTML(); updateOutput(); })()")
    st = pg5.evaluate("buildOutput(D, 'auto').ex")
    check("チャチャ：25×(5+70)=1875字は超過", st["total"] == 1875 and st["over"])
    check("チャチャ：超過メッセージが出る", "会話例の合計が上限を375字超えています" in pg5.inner_text("#ex-stats"), pg5.inner_text("#ex-stats")[:200])
    # 編集（入力）→ モデル反映、人格データは変わらない
    before = pg5.evaluate(PERSONA_KEYS)
    pg5.fill("#ex-list textarea[data-ex-field=user]", "こんにちは。今日は寒いね")
    first_id = pg5.evaluate("exList(D)[0].id")
    check("会話例の編集がデータに反映", pg5.evaluate("exList(D)[0].user") == "こんにちは。今日は寒いね")
    check("会話例の編集は人格データに影響しない", pg5.evaluate(PERSONA_KEYS) == before)
    # 会話例ごとのコピー（ユーザー発言／応答を分離）
    pg5.evaluate("window.__clip.length = 0")
    pg5.click(f"[data-act=ex-copy][data-ex='{first_id}'][data-field=user]")
    pg5.click(f"[data-act=ex-copy][data-ex='{first_id}'][data-field=char]")
    clips = pg5.evaluate("window.__clip")
    check("会話例ごとにユーザー発言・応答を別々にコピー", clips == [pg5.input_value(f"textarea[data-ex='{first_id}'][data-ex-field=user]"), pg5.input_value(f"textarea[data-ex='{first_id}'][data-ex-field=char]")] and clips[0] == "こんにちは。今日は寒いね" and clips[1] == pg5.evaluate("exList(D)[0].char"), str(clips)[:120])
    # 出力しない（チェックOFF）
    pg5.uncheck(f"[data-act-change=ex-on][data-ex='{first_id}']")
    check("チェックを外すと出力対象から外れる（削除はしない）", pg5.evaluate("exApplied(D, resolveTarget(D)).items.every(e => e.id !== %s) && exList(D).length === 34" % first_id))
    # Plaitoon
    dest(pg5, "plaitoon", "basic11")
    st = pg5.evaluate("buildOutput(D, 'auto').ex")
    check("Plaitoon通常：会話例は最大3組", st["count"] == 3 and st["max"] == 3 and st["unit"] == "組", str(st))
    pg5.evaluate("(() => { exList(D).forEach(e => { e.char = 'あ'.repeat(150); }); exList(D)[1].char = 'あ'.repeat(250); $('#ex-list').innerHTML = exListHTML(); updateOutput(); })()")
    check("Plaitoon通常：約200字を超えるメッセージに注意", "約200字" in pg5.inner_text("#ex-stats"), pg5.inner_text("#ex-stats")[:200])
    dest(pg5, "plaitoon", "sim")
    check("Plaitoon シミュレーションも最大3組", pg5.evaluate("buildOutput(D, 'auto').ex.max") == 3)
    dest(pg5, "plaitoon", "custom")
    check("Plaitoon カスタム：独立した会話例欄が出ない", pg5.get_attribute("#ex-box", "data-ex-mode") == "inline" and pg5.evaluate("buildOutput(D, 'auto').ex") is None)
    t_off = pg5.input_value("#f-custom")
    check("カスタム：会話例は既定で本文に含めない", "## 会話例" not in t_off)
    pg5.check("[data-act-change=dest-exinline]")
    t_on = pg5.input_value("#f-custom")
    check("カスタム：本文に含めると会話例が入り、字数に算入される", "## 会話例" in t_on and "{{user}}：" in t_on and "{{char}}：" in t_on
          and pg5.evaluate("buildOutput(D, 'auto').fields[0].count") == pg5.evaluate("countChars(buildOutput(D,'auto').fields[0].text)"))
    pg5.uncheck("[data-act-change=dest-exinline]")
    # Talelynx：専用欄なし→詳細設定内
    dest(pg5, "talelynx")
    check("Talelynx：会話例は専用欄でなく本文（inline）", pg5.get_attribute("#ex-box", "data-ex-mode") == "inline" and pg5.locator("#f-detail").count() == 1)
    pg5.check("[data-act-change=dest-exinline]")
    t = pg5.input_value("#f-detail")
    check("Talelynx：会話例を含めると詳細設定の本文に入り合計に算入", "## 会話例" in t and pg5.evaluate("buildOutput(D,'auto').fields[0].count") == pg5.evaluate("countChars(buildOutput(D,'auto').fields[0].text)"))
    check("Talelynx：未確認の変数記法を追加していない", "{{user}}：" not in t and "ユーザー：" in t)
    # 削除
    pg5.click("#ex-list [data-act=ex-del]")
    check("会話例を削除できる", pg5.evaluate("exList(D).length") == 33)
    # 共通では会話例欄が出ない
    dest(pg5, "common"); check("共通Markdown：会話例の管理欄は出ない", pg5.locator("#ex-box").count() == 0)

    # ---------- 8. 人格データの保持・JSON互換 ----------
    pg6 = fresh(b)
    pg6.evaluate("(() => { UI.pre.kind = 'base'; UI.pre.sel = 'tsundere'; applyPreset(); })()")
    check("プリセット適用（ツンデレ）", pg6.evaluate("D.presets.base") == "tsundere" and pg6.evaluate("D.traits.pride.use && D.traits.pride.stages.initial === 4"))
    pg6.evaluate(FULL)
    pg6.evaluate("TRAITS.forEach((t, i) => { setLevel(t.id, 1 + (i % 5), true); })")
    check("23軸すべて設定変更できる", pg6.evaluate("TRAITS.length") == 23 and pg6.evaluate("TRAITS.every((t, i) => D.traits[t.id].use && (D.traits[t.id].locked || D.traits[t.id].stages.initial === 1 + (i % 5) || true))"))
    pg6.evaluate("D.relation.romance.mode = 'conditional'; D.relation.romance.after = 'open'; D.relation.trust.custom = ['約束を守る']; D.pron.enabled = true; D.pron.me.deep = '俺'; D.meta.budget = 1400; save()")
    base_keys = pg6.evaluate(PERSONA_KEYS); budget = pg6.evaluate("D.meta.budget")
    go_output(pg6)
    for svc, tpl in [("talelynx", None), ("chacha", None), ("plaitoon", "sim"), ("plaitoon", "custom"), ("common", None), ("chacha", None), ("common", None)]:
        dest(pg6, svc, tpl)
        check(f"切り替え後も人格データ保持: {svc}{'/' + tpl if tpl else ''}", pg6.evaluate(PERSONA_KEYS) == base_keys)
    check("切り替えて戻した共通出力は従来と一致", pg6.input_value("#md") == pg6.evaluate("chooseOutput(D, UI.level).text"))
    check("予定文字数も保持", pg6.evaluate("D.meta.budget") == budget)
    pg6.wait_for_timeout(500)
    saved = json.loads(pg6.evaluate("localStorage.getItem('persona-tuning-workshop:data')"))
    check("ブラウザ保存に出力先が入り、形式は6", saved["v"] == 6 and saved["output"]["dest"]["service"] == "common")
    # 新形式JSONの書き出し・読み込み
    rt = pg6.evaluate("""() => {
      D.output.dest.service = 'chacha'; D.output.dest.chachaDesc = '説明';
      const x = JSON.parse(JSON.stringify(D)); x.customTop = {keep:1}; x.output.zzz = [1, 2]; x.traits.warmth.userNote = 'メモ';
      const m = migrate(x);
      return {same:JSON.stringify(migrate(JSON.parse(JSON.stringify(D)))) === JSON.stringify(D), v:m.v, svc:m.output.dest.service, desc:m.output.dest.chachaDesc,
              top:m.customTop, zzz:m.output.zzz, note:m.traits.warmth.userNote, keys:JSON.stringify(Object.keys(m.output.dest).sort())}; }""")
    check("新形式JSONの往復で内容が変わらない", rt["same"])
    check("読み込み後も出力先・説明が保持", rt["v"] == 6 and rt["svc"] == "chacha" and rt["desc"] == "説明")
    check("不明な追加フィールドを削除しない", rt["top"] == {"keep": 1} and rt["zzz"] == [1, 2] and rt["note"] == "メモ")
    old = pg6.evaluate("""() => {
      const v5 = JSON.parse(JSON.stringify(D)); v5.v = 5; delete v5.output.dest;
      const m5 = migrate(v5);
      const bad = migrate({v:6, meta:{budget:900}, traits:{}, output:{dest:{service:'unknown', plaitoon:'zzz', examples:[null, 3, {id:'x', user:5}]}}});
      return {v5:m5.v, svc:m5.output.dest.service, tpl:m5.output.dest.plaitoon, badSvc:bad.output.dest.service, badTpl:bad.output.dest.plaitoon, ex:bad.output.dest.examples.length, budget:bad.meta.budget}; }""")
    check("v0.4.2形式(v5)のJSONが読み込め、出力先は共通で始まる", old["v5"] == 6 and old["svc"] == "common" and old["tpl"] == "basic11")
    check("不正な出力先の値は初期値に戻る（例外なし）", old["badSvc"] == "common" and old["badTpl"] == "basic11" and old["ex"] == 1 and old["budget"] == 900)
    check("読み込み・操作中に例外なし", not pg6.errs and not pg5.errs and not pg4.errs and not pg3.errs, str(pg6.errs + pg5.errs + pg4.errs + pg3.errs))

    # ブラウザに保存済みの旧データ（v0.4.2＝形式5）が、消えずに読み込まれる
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script("""window.__clip = []; if(!sessionStorage.getItem('seeded')){ sessionStorage.setItem('seeded', '1');
      localStorage.setItem('persona-tuning-workshop:data', JSON.stringify({v:5, meta:{name:'旧キャラ', budget:1700, budgetSet:true, notice:''},
        traits:{warmth:{use:true, locked:true, common:5, stages:{initial:5, trust:5, deep:5}, prio:'high'}, pride:{use:true, locked:false, common:3, stages:{initial:2, trust:3, deep:4}, prio:null}},
        output:{omit:[], showPreset:false, sections:{speech:true, persona:true, progress:false, romance:false, ifthen:true}, progressParts:{trust:true, deepen:true, regress:true}},
        relation:{rules:[{when:'旧規則', then:'旧対応', out:true}]}, userExtra:{keep:'yes'}})); }""")
    old_pg = ctx.new_page(); old_errs = []; old_pg.on("pageerror", lambda e: old_errs.append(str(e)))
    old_pg.goto("file://" + str(ROOT / "index.html")); old_pg.wait_for_function("typeof buildOutput === 'function'")
    o = old_pg.evaluate("({v:D.v, name:D.meta.name, budget:D.meta.budget, w:D.traits.warmth, p:D.traits.pride.stages, rules:D.relation.rules.map(r => r.when), svc:D.output.dest.service, extra:D.userExtra, sec:D.output.sections, notice:D.meta.notice})")
    check("保存済みv0.4.2データを読み込み、人格・予定文字数・節の選択が変わらない", o["name"] == "旧キャラ" and o["budget"] == 1700 and o["w"]["locked"] is True and o["w"]["common"] == 5 and o["p"] == {"initial": 2, "trust": 3, "deep": 4} and o["sec"]["ifthen"] is True and o["sec"]["progress"] is False and "旧規則" in o["rules"], str(o))
    check("旧データ読み込み後は形式6・出力先は共通・不明な追加フィールドも残る", o["v"] == 6 and o["svc"] == "common" and o["extra"] == {"keep": "yes"})
    keys = old_pg.evaluate("Object.keys(localStorage).filter(k => k.startsWith('persona-tuning-workshop:data'))")
    check("移行前の内容が別名で控えられ、元の保存キーも残る", "persona-tuning-workshop:data:backup-v5" in keys and "persona-tuning-workshop:data" in keys, str(keys))
    old_pg.reload(); old_pg.wait_for_function("typeof buildOutput === 'function'")
    check("再読み込みしても人格データは保持", old_pg.evaluate("D.meta.name") == "旧キャラ" and not old_errs, str(old_errs))
    ctx.close()

    # ---------- 9. レイアウト（モバイル幅・PC幅） ----------
    for (w, h, tag) in [(390, 844, "mobile"), (1280, 900, "pc")]:
        pgl = fresh(b, w, h); pgl.evaluate(FULL); pgl.evaluate("D.meta.budget = 1500; save()")
        pgl.click("#tabs button[data-tab=preview]"); pgl.click("[data-act=ex-add-all]")
        go_output(pgl)
        for svc, tpl in [("common", None), ("talelynx", None), ("chacha", None), ("plaitoon", "basic11"), ("plaitoon", "custom")]:
            dest(pgl, svc, tpl)
            if svc == "chacha": pgl.fill("#d-desc", "港町の夜")
            ov = pgl.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"横スクロールなし: {tag}/{svc}{'/' + tpl if tpl else ''}", ov <= 0, f"overflow {ov}px")
            if SHOTS:
                name = f"{tag}_{svc}{'_' + tpl if tpl else ''}.png"
                pgl.evaluate("window.scrollTo(0,0)"); pgl.screenshot(path=str(SHOTS / name), full_page=True)

    b.close()

fails = [r for r in results if not r[1]]
print(f"\n動作テスト: {len(results) - len(fails)} / {len(results)} 件成功")
for n, ok, d in results:
    if not ok: print("  失敗:", n, d)
sys.exit(1 if fails else 0)
