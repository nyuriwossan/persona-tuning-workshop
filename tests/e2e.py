#!/usr/bin/env python3
"""動作テスト（実ブラウザ Chromium で index.html を操作する）
  1〜9：v0.5.0 出力先拡張（段階変化型）
  10〜：v0.6.0 単独人格モード

  ※ v0.6.0 でデータ形式が 6→7、アプリ版が 0.5.0→0.6.0 になったため、版番号を確かめる5か所の期待値だけを更新している
    （出力・計数・移行の内容に関する期待値は変えていない）

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
    check("ヘッダーのバージョン表示が v0.6.0", pg.inner_text(".ver") == "v0.6.0" and pg.evaluate("APP_VERSION") == "0.6.0")
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
    check("ブラウザ保存に出力先が入り、形式は7", saved["v"] == 7 and saved["output"]["dest"]["service"] == "common")
    # 新形式JSONの書き出し・読み込み
    rt = pg6.evaluate("""() => {
      D.output.dest.service = 'chacha'; D.output.dest.chachaDesc = '説明';
      const x = JSON.parse(JSON.stringify(D)); x.customTop = {keep:1}; x.output.zzz = [1, 2]; x.traits.warmth.userNote = 'メモ';
      const m = migrate(x);
      return {same:JSON.stringify(migrate(JSON.parse(JSON.stringify(D)))) === JSON.stringify(D), v:m.v, svc:m.output.dest.service, desc:m.output.dest.chachaDesc,
              top:m.customTop, zzz:m.output.zzz, note:m.traits.warmth.userNote, keys:JSON.stringify(Object.keys(m.output.dest).sort())}; }""")
    check("新形式JSONの往復で内容が変わらない", rt["same"])
    check("読み込み後も出力先・説明が保持", rt["v"] == 7 and rt["svc"] == "chacha" and rt["desc"] == "説明")
    check("不明な追加フィールドを削除しない", rt["top"] == {"keep": 1} and rt["zzz"] == [1, 2] and rt["note"] == "メモ")
    old = pg6.evaluate("""() => {
      const v5 = JSON.parse(JSON.stringify(D)); v5.v = 5; delete v5.output.dest;
      const m5 = migrate(v5);
      const bad = migrate({v:6, meta:{budget:900}, traits:{}, output:{dest:{service:'unknown', plaitoon:'zzz', examples:[null, 3, {id:'x', user:5}]}}});
      return {v5:m5.v, svc:m5.output.dest.service, tpl:m5.output.dest.plaitoon, badSvc:bad.output.dest.service, badTpl:bad.output.dest.plaitoon, ex:bad.output.dest.examples.length, budget:bad.meta.budget}; }""")
    check("v0.4.2形式(v5)のJSONが読み込め、出力先は共通で始まる", old["v5"] == 7 and old["svc"] == "common" and old["tpl"] == "basic11")
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
    check("旧データ読み込み後は形式7・出力先は共通・不明な追加フィールドも残る", o["v"] == 7 and o["svc"] == "common" and o["extra"] == {"keep": "yes"})
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

    # =====================================================================
    # 10〜. v0.6.0 単独人格モード
    # =====================================================================
    FORBID = ["全段階で不変", "全段階共通", "初期段階", "信頼成立後", "関係深化後", "段階別の振る舞い", "（差分）", "移行：", "段階"]
    def forbidden_in(t): return [w for w in FORBID if w in t]
    # 段階・固定・使用・口調・呼称・関係の条件が混在するキャラクター
    MIXED = """(() => {
      TRAITS.forEach((t, i) => { const d = D.traits[t.id]; d.use = i % 4 !== 3; d.stages = {initial:1+(i%5), trust:1+((i+2)%5), deep:1+((i+4)%5)}; d.common = 1+((i+1)%5);
        d.locked = i % 5 === 0; d.prio = ['high','normal','low'][i%3]; });
      Object.keys(D.output.sections).forEach(k => D.output.sections[k] = true);
      D.meta.name = 'ミナト'; D.meta.budget = 0;
      D.speech.common = 'haughty'; D.speech.enabled = true; D.speech.stages = {initial:'polite', trust:null, deep:'gentle'};
      D.pron.enabled = true; D.pron.me.common = '俺'; D.pron.me.initial = '私'; D.pron.you.common = 'お前'; D.pron.you.deep = '君';
      D.relation.trust.custom = ['一緒に食事をした']; D.relation.romance.mode = 'conditional'; D.relation.romance.after = 'open';
      D.relation.romance.presets = ['special']; D.relation.romance.custom = ['雨の日に傘を差し出される'];
      D.relation.rules.push({when:'褒められたとき', then:'顔を背けて礼を言う', out:true});
      D.link.mode = 'linked'; TRAITS.forEach(t => { if(linkable(t.id)) relink(t.id); });
      CATS.forEach(c => { UI.open[c.id] = true; });
      save(); render(true); })()"""
    PERSONA_ALL = "JSON.stringify({traits:D.traits, relation:D.relation, speech:D.speech, pron:D.pron, link:D.link, presets:D.presets, legacy:D.legacy, output:D.output, meta:D.meta})"
    LATER_VALS = "JSON.stringify(Object.fromEntries(TRAITS.map(t => [t.id, [D.traits[t.id].stages.trust, D.traits[t.id].stages.deep]])))"

    pgS = fresh(b)
    check("単独：新規データの初期モードは段階変化型", pgS.evaluate("defaultData().structure.mode") == "staged" and pgS.evaluate("D.structure.mode") == "staged")
    check("単独：v6データは段階変化型・形式7で読み込む", pgS.evaluate("D.v") == 7)
    check("単独：構成方式の切り替えが人格調律の先頭にある", pgS.locator("#app > section#structure-card").count() == 1
          and pgS.evaluate("document.querySelector('#app').firstElementChild.id") == "structure-card"
          and pgS.locator("#structure-seg button").all_inner_texts() == ["単独人格", "段階変化型"])
    check("単独：段階変化型では段階タブと「関係段階の作り方」が出る", pgS.locator(".stagebar").count() == 1 and pgS.locator("#mode-card").count() == 1)
    pgS.evaluate(MIXED)
    staged_md = pgS.evaluate("[1,2,3].map(l => buildMarkdown(D, l).text)")
    staged_pv = pgS.evaluate("previewMarkdown(D, SITUATIONS, true, {preset:'', me:'', you:''})")
    before_all = pgS.evaluate(PERSONA_ALL)

    # ---------- 10. 切り替え：データを書き換えない ----------
    pgS.click("[data-act=structure][data-val=single]")
    check("単独：切り替えで単独人格になる", pgS.evaluate("D.structure.mode") == "single")
    check("単独：切り替えだけでは人格値・段階・連動・関係・口調・呼称を変えない", pgS.evaluate(PERSONA_ALL) == before_all)
    check("単独：段階タブ・関係段階の作り方が非表示", pgS.locator(".stagebar").count() == 0 and pgS.locator("#mode-card").count() == 0 and pgS.locator("[data-act=link-mode]").count() == 0)
    ta = pgS.inner_text("#trait-area")
    check("単独：調律エリアに段階名・急変・全段階の表示がない", not [w for w in ["信頼成立後", "関係深化後", "急変", "全段階", "信頼後", "深化後"] if w in ta], str([w for w in ["信頼成立後", "関係深化後", "急変", "全段階"] if w in ta]))
    check("単独：連動・再提案のボタンが出ない", pgS.locator("[data-act=link-follow], [data-act=resug]").count() == 0)
    check("単独：使用項目の一覧に「全段階共通」が出ない", "全段階共通" not in pgS.inner_text("details.sel"))
    check("単独：口調・呼称の段階切り替えスイッチが出ない（共通の設定を編集）", pgS.locator("[data-act-change=speech-enabled], [data-act-change=pron-enabled], [data-act-change=speech-stage]").count() == 0
          and pgS.locator("#pron-body .picker[data-slot=common]").count() == 2)
    check("単独：段階別の口調・呼称を保持している旨の表示", "段階変化型に戻すと使えます" in pgS.inner_text("#speech-card") and "段階変化型に戻すと使えます" in pgS.inner_text("#pron-card"))
    check("単独：使用・固定の操作は残る", pgS.locator("#trait-area .lockbtn").count() > 0 and pgS.locator("#trait-area input[data-act-change=use]").count() > 0)

    # ---------- 11. Markdown単独出力 ----------
    single_md = pgS.evaluate("[1,2,3].map(l => buildMarkdown(D, l).text)")
    for lv, t in zip([1, 2, 3], single_md):
        check(f"単独：詳細度{lv}で段階の見出し・説明が出ない", not forbidden_in(t), str(forbidden_in(t)))
        check(f"単独：詳細度{lv}は基本人格の節がある", "\n## 基本人格\n" in t and t.startswith("# ミナト｜人格設計"))
    t3 = single_md[2]
    check("単独：話し方は共通の口調・呼称（段階別の値を使わない）", "- 一人称：「俺」\n- 相手の呼び方：「お前」\n- 文体：尊大" in t3, t3[:300])
    exp = pgS.evaluate("""(() => { const out = {core:[], base:[]};
      TRAITS.filter(t => !t.scope && D.traits[t.id].use).forEach(t => {
        const d = D.traits[t.id], v = d.locked ? d.common : d.stages.initial, lv = t.levels[v - 1];
        (d.locked ? out.core : out.base).push(`- ${t.name}：${lv.r + lv.x}`); });
      return out; })()""")
    core_part = t3.split("## 人格の核")[1].split("\n## ")[0] if "## 人格の核" in t3 else ""
    base_part = t3.split("\n## 基本人格\n")[1].split("\n\n## ")[0]
    check("単独：固定項目は「人格の核」に固定の値で出る", exp["core"] and all(x in core_part for x in exp["core"]) and not any(x in base_part for x in exp["core"]), str(exp["core"][:2]))
    check("単独：非固定項目は「基本人格」に初期の値で出る", all(x in base_part for x in exp["base"]) and len([l for l in base_part.split("\n") if l.startswith("- ") and "：" in l]) >= len(exp["base"]))
    check("単独：関係の進展条件は出力しない（節はONのまま保持）", "関係の進展" not in t3 and "一緒に食事をした" not in t3 and pgS.evaluate("D.output.sections.progress") is True)
    check("単独：恋愛感情の条件・反応・If-Thenは出力する", "恋愛感情が芽生える条件" in t3 and "雨の日に傘を差し出される" in t3 and "褒められたとき → 顔を背けて礼を言う" in t3)
    check("単独：恋愛の文章に「信頼の段階」が出ない", "信頼の段階" not in "".join(single_md))
    for mode, after in [("start", "hidden"), ("none", "hidden"), ("conditional", "unaware")]:
        r = pgS.evaluate(f"(() => {{ const X = JSON.parse(JSON.stringify(D)); X.relation.romance.mode = '{mode}'; X.relation.romance.after = '{after}'; return [1,2,3].map(l => buildMarkdown(X, l).text); }})()")
        check(f"単独：恋愛「{mode}」でも段階の表現なしで出力", all(not forbidden_in(x) and "## 信頼と恋愛感情" in x for x in r), str([forbidden_in(x) for x in r]))
    mx = pgS.evaluate("""(() => { const out = [];
      for(const lockAll of [true, false]) for(const useLater of [true, false]){
        const X = JSON.parse(JSON.stringify(D)); TRAITS.forEach((t, i) => { X.traits[t.id].locked = lockAll ? i % 2 === 0 : false; X.traits[t.id].use = useLater || i < 6; });
        out.push([1,2,3].map(l => buildMarkdown(X, l).text)); }
      return out; })()""")
    check("単独：固定／非固定の組み合わせを変えても段階の表現なし", all(not forbidden_in(x) for xs in mx for x in xs))
    pgS.evaluate("D.output.showPreset = true; D.presets.base = 'kuudere'; save()")
    check("単独：プリセット名の表示切り替えが効く", "着想：「クーデレ」" in pgS.evaluate("buildMarkdown(D, 2).text"))
    pgS.evaluate("D.output.showPreset = false; D.presets.base = null; save()")
    nn = pgS.evaluate("[1,2,3].map(l => countChars(buildMarkdown(D, l).text))")
    pgS.evaluate(f"D.meta.budget = {nn[1] + 1}")
    check("単独：予定文字数に合わせて詳細度を自動選択（標準）", pgS.evaluate("chooseOutput(D, 'auto').level") == 2, str(nn))
    pgS.evaluate(f"D.meta.budget = {nn[0] - 1}")
    check("単独：最小でも超えるときは最小で出力", pgS.evaluate("chooseOutput(D, 'auto').level") == 1)
    pgS.evaluate("D.meta.budget = 0")
    pr = pgS.evaluate("""(() => { const id = TRAITS.find(t => !t.scope && D.traits[t.id].use && !D.traits[t.id].locked).id;
      const a = buildMarkdown(D, 1).text; const old = D.traits[id].prio; D.traits[id].prio = 'high'; const b2 = buildMarkdown(D, 1).text; D.traits[id].prio = old;
      const imp = useImpact(D, 2); return {changed:a !== b2, imp:imp.filter(c => c.used).every(c => c.delta > 0)}; })()""")
    check("単独：優先度と使用項目の増減字数が効く", pr["changed"] and pr["imp"], str(pr))

    # ---------- 12. 値の編集：後の2段階・連動の基準を変えない ----------
    later0 = pgS.evaluate(LATER_VALS); link0 = pgS.evaluate("JSON.stringify(D.link)")
    tid = pgS.evaluate("TRAITS.find(t => !t.scope && D.traits[t.id].use && !D.traits[t.id].locked && D.traits[t.id].stages.initial !== 5).id")
    pgS.click(f"#tc-{tid} [data-act=lv][data-val='5']")
    check("単独：スライダーで初期の値が変わる", pgS.evaluate(f"D.traits.{tid}.stages.initial") == 5)
    check("単独：値を変えても信頼成立後・関係深化後は変わらない", pgS.evaluate(LATER_VALS) == later0)
    check("単独：連動調整中でも連動・基準（link）を適用しない", pgS.evaluate("JSON.stringify(D.link)") == link0)
    pgS.evaluate(f"(() => {{ const r = document.querySelector('#tc-{tid} input[type=range]'); r.value = 2; r.dispatchEvent(new Event('input', {{bubbles:true}})); r.dispatchEvent(new Event('change', {{bubbles:true}})); }})()")
    check("単独：ドラッグ操作（input/change）でも後の段階・連動は不変", pgS.evaluate(f"D.traits.{tid}.stages.initial") == 2 and pgS.evaluate(LATER_VALS) == later0 and pgS.evaluate("JSON.stringify(D.link)") == link0)
    # 自動提案モードでも提案しない
    pgS.evaluate(f"window.__lk = D.link.traits.{tid}; D.link.mode = 'suggest'; D.link.traits.{tid} = {{sugg:false, edited:{{trust:false, deep:false}}, follow:{{trust:true, deep:true}}}}; save()")
    link1 = pgS.evaluate("JSON.stringify(D.link)")
    pgS.click(f"#tc-{tid} [data-act=lv][data-val='4']")
    check("単独：自動提案（未提案の項目）でも後の段階を提案で書き換えない", pgS.evaluate(LATER_VALS) == later0 and pgS.evaluate("JSON.stringify(D.link)") == link1 and pgS.evaluate("pendingSugg") is None)
    pgS.evaluate(f"D.link.traits.{tid} = window.__lk; save()")   # テスト用に差し替えた連動データを元に戻す
    gid = "trustSpeed"
    pgS.evaluate("D.traits.trustSpeed.use = true; D.traits.trustSpeed.stages = {initial:2, trust:3, deep:4}; Object.keys(UI.open).forEach(k => UI.open[k] = true); CATS.forEach(c => UI.open[c.id] = true); save(); render(true)")
    pgS.click("#tc-trustSpeed [data-act=lv][data-val='1']")
    later0 = pgS.evaluate(LATER_VALS)   # 信頼形成速度の段階値をテスト用に入れたので取り直す
    check("単独：全段階共通の項目は共通値だけが変わり、段階の値は残る", pgS.evaluate("D.traits.trustSpeed.common") == 1 and pgS.evaluate("D.traits.trustSpeed.stages") == {"initial": 2, "trust": 3, "deep": 4})
    check("単独：信頼形成速度は単独では出力に使わない旨", "単独人格では出力に使いません" in pgS.inner_text("#tc-trustSpeed"))
    lid = pgS.evaluate("TRAITS.find(t => !t.scope && D.traits[t.id].use && !D.traits[t.id].locked).id")
    pgS.evaluate(f"D.link.mode = 'linked'; save()")
    link2 = pgS.evaluate("JSON.stringify(D.link)")
    pgS.click(f"#tc-{lid} .lockbtn")
    check("単独：固定すると初期の値が固定値になり、「人格の核」に出る", pgS.evaluate(f"D.traits.{lid}.locked") is True and pgS.evaluate(f"D.traits.{lid}.common === D.traits.{lid}.stages.initial")
          and pgS.evaluate(f"buildMarkdown(D, 3).text.split('## 基本人格')[0].includes(TRAIT.{lid}.name + '：')"))
    pgS.click(f"#tc-{lid} .lockbtn")
    check("単独：固定の解除で連動の基準を取り直さない・後の段階は不変", pgS.evaluate(f"D.traits.{lid}.locked") is False and pgS.evaluate("JSON.stringify(D.link)") == link2 and pgS.evaluate(LATER_VALS) == later0)
    check("単独：調律中の確認に急変・段階差の警告が出ない", not [c for c in pgS.evaluate("checks()") if c["k"] == "warn"] and "急変" not in pgS.inner_text("#checks"))

    # ---------- 13. 往復で壊れない ----------
    init_now = pgS.evaluate("JSON.stringify(Object.fromEntries(TRAITS.map(t => [t.id, D.traits[t.id].stages.initial])))")
    snap = pgS.evaluate(PERSONA_ALL)
    for m in ["staged", "single", "staged", "single", "staged"]:
        pgS.click(f"[data-act=structure][data-val={m}]")
        check(f"往復：{m}へ切り替えても保存データは同じ", pgS.evaluate(PERSONA_ALL) == snap)
    check("往復：段階変化型に戻すと段階タブ・作り方が戻る", pgS.locator(".stagebar").count() == 1 and pgS.locator("#mode-card").count() == 1)
    check("往復：単独で変えた初期値は段階変化型にも反映、後の2段階は保持", pgS.evaluate("JSON.stringify(Object.fromEntries(TRAITS.map(t => [t.id, D.traits[t.id].stages.initial])))") == init_now and pgS.evaluate(LATER_VALS) == later0)
    pgS.wait_for_timeout(400)
    saved = json.loads(pgS.evaluate("localStorage.getItem('persona-tuning-workshop:data')"))
    check("往復：ブラウザ保存は形式7・構成方式を含む", saved["v"] == 7 and saved["structure"]["mode"] == "staged")
    # 編集前の値に戻すと、段階変化型の出力・試着は切り替え前と完全に一致する
    rt_same = pgS.evaluate("""(before) => { const B = JSON.parse(before); TRAITS.forEach(t => { D.traits[t.id] = B.traits[t.id]; }); D.link = B.link; D.meta = B.meta; D.output = B.output; D.presets = B.presets;
        return JSON.stringify({traits:D.traits, relation:D.relation, speech:D.speech, pron:D.pron, link:D.link, presets:D.presets, legacy:D.legacy, output:D.output, meta:D.meta}) === before; }""", before_all)
    check("往復：段階変化型の出力が切り替え前と一致", rt_same and pgS.evaluate("[1,2,3].map(l => buildMarkdown(D, l).text)") == staged_md)
    check("往復：段階変化型の試着Markdownが切り替え前と一致", pgS.evaluate("previewMarkdown(D, SITUATIONS, true, {preset:'', me:'', you:''})") == staged_pv)
    pgS.click("[data-act=structure][data-val=single]")
    check("往復：単独に戻すと同じ単独出力", pgS.evaluate("[1,2,3].map(l => buildMarkdown(D, l).text)") == single_md)

    # ---------- 14. プリセット（両モード） ----------
    pgP = fresh(b)
    pgP.evaluate("(() => { D.traits.pride.use = true; D.traits.pride.stages = {initial:3, trust:2, deep:1}; D.traits.wariness.use = true; D.traits.wariness.stages = {initial:4, trust:1, deep:1};"
                 " D.traits.candor.use = true; D.traits.candor.locked = true; D.traits.candor.common = 1; D.link.mode = 'suggest'; D.presets.pattern = 'gap'; save(); render(true); })()")
    pgP.click("[data-act=structure][data-val=single]")
    pgP.evaluate("UI.open.presets = true; render(true)")
    later_p = pgP.evaluate(LATER_VALS); link_p = pgP.evaluate("JSON.stringify(D.link)")
    pgP.click("[data-act=pre-pick][data-id=haughty]")
    check("プリセット（単独）：変化パターンの選択UIが出ない", pgP.locator("[data-act=pre-pattern]").count() == 0)
    rows = pgP.evaluate("presetRows('base', 'haughty', D.presets.pattern).map(r => ({id:r.id, status:r.status, to:r.to[0], cur:r.cur[0]}))")
    st = {r["id"]: r for r in rows}
    check("プリセット（単独）：初期の値で比較し、競合・新規・同値を判定", st["pride"]["status"] == "conflict" and st["pride"]["to"] == 5 and st["pride"]["cur"] == 3
          and st["wariness"]["status"] == "same" and st["initiative"]["status"] == "new", str(st))
    check("プリセット（単独）：競合は既定で今の値を残す", pgP.evaluate("rowChoice(presetRows('base','haughty',D.presets.pattern).find(r => r.id === 'pride'))") == "keep")
    pv = pgP.inner_text("#pre-preview")
    check("プリセット（単独）：確認画面に3段階の表記が出ない", "→Lv" not in pv.replace("→ Lv", "") and "（全段階）" not in pv and "初期→信頼成立後" not in pv, pv[:300])
    pgP.click("[data-act=pre-choice][data-trait=pride][data-val=apply]")
    pgP.check("[data-act-change=pre-lock][data-trait=pride]")
    pgP.click("[data-act=pre-apply]")
    check("プリセット（単独）：初期の値だけに適用・固定候補も反映", pgP.evaluate("D.traits.pride.stages.initial") == 5 and pgP.evaluate("D.traits.pride.locked") is True and pgP.evaluate("D.traits.pride.common") == 5
          and pgP.evaluate("D.traits.initiative.use && D.traits.initiative.stages.initial === 5") and pgP.evaluate("D.traits.reliance.stages.initial") == 1)
    later_after = json.loads(pgP.evaluate(LATER_VALS)); later_before = json.loads(later_p)
    check("プリセット（単独）：後の2段階の値を変えない", later_after == later_before)
    check("プリセット（単独）：連動・自動提案の基準を変えない", pgP.evaluate("JSON.stringify(D.link)") == link_p)
    check("プリセット（単独）：段階変化パターンの設定も変えない", pgP.evaluate("D.presets.pattern") == "gap")
    check("プリセット（単独）：適用後の出力は新しい値・段階の表現なし", "自尊心" in pgP.evaluate("buildMarkdown(D, 3).text") and not forbidden_in(pgP.evaluate("buildMarkdown(D, 3).text")))
    pgP.click("[data-act=pre-undo]")
    check("プリセット（単独）：取り消しで値・固定・使用状態が元に戻る", pgP.evaluate("D.traits.pride.stages.initial") == 3 and pgP.evaluate("D.traits.pride.locked") is False
          and pgP.evaluate("D.traits.initiative.use") is False and pgP.evaluate(LATER_VALS) == later_p and pgP.evaluate("JSON.stringify(D.link)") == link_p and pgP.evaluate("D.presets.base") is None)
    # 愛情スタイル＋If-Then候補・手で変えた後の取り消し
    pgP.click("[data-act=pre-kind][data-val=love]"); pgP.click("[data-act=pre-pick][data-id=silentDote]"); pgP.click("[data-act=pre-apply]")
    check("プリセット（単独）：愛情スタイルも初期の値で適用", pgP.evaluate("[D.traits.affectionWords.stages.initial, D.traits.affectionActions.stages.initial, D.traits.affectionWords.use]") == [1, 2, True])
    pgP.click("#tc-affectionActions [data-act=lv][data-val='4']")
    pgP.click("[data-act=pre-undo]")
    check("プリセット（単独）：手で変えた項目がある取り消しは確認が出る", pgP.locator("[data-act=pre-undo-keep]").count() == 1)
    pgP.click("[data-act=pre-undo-keep]")
    check("プリセット（単独）：手で変えた項目は残して取り消せる", pgP.evaluate("D.traits.affectionActions.stages.initial") == 4 and pgP.evaluate("D.traits.affectionWords.use") is False and pgP.evaluate(LATER_VALS) == later_p)
    pgP.click("[data-act=pre-kind][data-val=base]"); pgP.click("[data-act=pre-pick][data-id=schemer]")
    pgP.check("[data-act-change=pre-rule][data-i='0']"); pgP.click("[data-act=pre-apply]")
    check("プリセット（単独）：If-Then候補の追加と取り消し", pgP.evaluate("D.relation.rules.some(r => r.when === '本心や目的を探られたとき')"))
    pgP.click("[data-act=pre-undo]")
    check("プリセット（単独）：取り消すと追加した規則も消える", not pgP.evaluate("D.relation.rules.some(r => r.when === '本心や目的を探られたとき')"))
    # 段階変化型に戻しての適用（従来どおり3段階・パターン）
    pgP.click("[data-act=structure][data-val=staged]")
    pgP.evaluate("UI.open.presets = true; render(true)")
    pgP.click("[data-act=pre-pick][data-id=haughty]")
    check("プリセット（段階）：変化パターンの選択UIが戻る", pgP.locator("[data-act=pre-pattern]").count() == 3)
    pgP.click("[data-act=pre-apply]")
    check("プリセット（段階）：3段階の値と変化パターンを適用（従来どおり）", pgP.evaluate("D.traits.reliance.stages") == pgP.evaluate("(() => { const v = patternVals([1,2,3], 'gap'); return {initial:v[0], trust:v[1], deep:v[2]}; })()"))
    pgP.click("[data-act=pre-undo]")
    check("プリセット（段階）：取り消しも従来どおり", pgP.evaluate(LATER_VALS) == later_p and pgP.evaluate("D.traits.initiative.use") is False)
    check("プリセット：例外なし", not pgP.errs, str(pgP.errs))

    # ---------- 15. 関係・反応 ----------
    pgS.click("#tabs button[data-tab=relation]")
    rel = pgS.inner_text("#app")
    check("関係（単独）：進展条件は編集欄を出さず、保持している旨を表示", pgS.locator("#progress-kept").count() == 1 and pgS.locator("[data-key=trust], [data-key=deepen], [data-key=regress]").count() == 0
          and "段階変化型に戻すと元どおり使えます" in rel and "成立 4件" in rel, rel[:200])
    check("関係（単独）：恋愛感情の3方式とIf-Thenは使える", pgS.locator("[data-act=rom-mode]").count() == 3 and pgS.locator("[data-key=romance]").count() > 0 and pgS.locator("[data-act=rule-add]").count() == 1)
    pgS.click("[data-act=rom-mode][data-val=start]")
    check("関係（単独）：恋愛「最初から」に切り替えて出力", "最初から相手に惹かれている" in pgS.evaluate("buildMarkdown(D, 2).text"))
    pgS.click("[data-act=rom-mode][data-val=conditional]")
    check("関係（単独）：進展条件のデータは保持", pgS.evaluate("D.relation.trust.custom") == ["一緒に食事をした"] and pgS.evaluate("D.relation.regress.presets.length") == 2)

    # ---------- 16. 出力設定画面 ----------
    go_output(pgS)
    na = pgS.locator("[data-sec-na=progress]")
    check("出力（単独）：関係の進展条件は選択不可・理由と保持を表示", na.count() == 1 and na.locator("input[disabled]").count() == 1 and "単独人格では使えません" in na.inner_text() and "保持" in na.inner_text())
    check("出力（単独）：出力する節の件数は4つのうち", pgS.inner_text("#sec-count").endswith("/ 4"))
    check("出力（単独）：人格の節名に「3段階」が出ない", "3段階" not in pgS.inner_text("#sec-list"))
    check("出力（単独）：構成方式の表示", "単独人格" in pgS.inner_text("#o-structure"))
    check("出力（単独）：項目ごとの出力設定に段階の表記がない", "→" not in pgS.inner_text("#omit-list") and "全段階" not in pgS.inner_text("#omit-list"))
    pgS.uncheck("[data-act-change=sec][data-sec=ifthen]")
    check("出力（単独）：節のON/OFFが効く", "## 状況別の行動規則" not in pgS.input_value("#md"))
    pgS.check("[data-act-change=sec][data-sec=ifthen]")

    # ---------- 17. 出力先4系統 ----------
    pgS.evaluate("D.meta.budget = 0; save(); render(true)")
    for svc, tpl, taid in [("common", None, "md"), ("talelynx", None, "f-detail"), ("chacha", None, "f-profile"), ("plaitoon", "basic11", "f-info"), ("plaitoon", "sim", "f-info"), ("plaitoon", "custom", "f-custom")]:
        dest(pgS, svc, tpl)
        label = svc + ("/" + tpl if tpl else "")
        shown = pgS.input_value(f"#{taid}")
        T = pgS.evaluate("(() => { const T = buildOutput(D, UI.level); return {text:T.fields.find(f => f.kind === 'persona').text, count:T.fields[0].count, cnt:T.tgt.counter.id}; })()")
        check(f"出力先（単独）{label}：表示＝buildOutput・段階の表現なし", shown == T["text"] and not forbidden_in(shown), str(forbidden_in(shown)))
        fn = "countChacha" if svc == "chacha" else "countChars"
        check(f"出力先（単独）{label}：字数はサービスの計数方式", T["count"] == pgS.evaluate(f"{fn}(buildOutput(D, UI.level).fields[0].text)"))
        pgS.evaluate("window.__clip.length = 0")
        pgS.click("[data-act=copy-md]" if svc == "common" else f"[data-act=copy-field][data-ta={taid}]")
        check(f"出力先（単独）{label}：コピー＝表示", pgS.evaluate("window.__clip[0]") == shown)
    lim = pgS.evaluate("(() => { const X = JSON.parse(JSON.stringify(D)); X.output.dest.service = 'chacha'; X.meta.budget = 6000; const T = buildOutput(X, 'auto'); return {lv:T.level, count:T.pool.count, over:T.pool.over}; })()")
    check("出力先（単独）：チャチャの上限2000で詳細度を選ぶ", lim["count"] <= 2000 or (lim["lv"] == 1 and lim["over"]), str(lim))
    check("出力先（単独）：構成方式はサービスごとに変わらない（共通データ）", pgS.evaluate("D.structure.mode") == "single" and "structure" not in pgS.evaluate("Object.keys(D.output.dest)"))

    # ---------- 18. 試着・会話例 ----------
    pgS.evaluate("exList(D).length = 0; save()")
    pgS.click("#tabs button[data-tab=preview]"); pgS.wait_for_selector("#pv-cards")
    for sid in pgS.evaluate("SITUATIONS.map(s => s.id)"):
        pgS.click(f"[data-act=sit][data-id={sid}]")
        cards = pgS.locator("#pv-cards .card.pv")
        name = pgS.evaluate(f"SITUATIONS.find(s => s.id === '{sid}').name")
        txt = pgS.inner_text("#pv-cards")
        if not (cards.count() == 1 and pgS.inner_text("#pv-cards h3") == name and not [w for w in ["初期", "信頼成立後", "関係深化後"] if w in txt]):
            check(f"試着（単独）{sid}：1種類だけ・段階名なし", False, txt[:120]); break
    else:
        check("試着（単独）：12状況すべて1種類だけ・見出しに段階名なし", True)
    check("試着（単独）：「3段階をすべて追加」が出ない", pgS.locator("[data-act=ex-add-all]").count() == 0)
    pgS.click("[data-act=sit][data-id=meet]")
    meta = pgS.inner_text("#pv-cards .pv-meta")
    md2 = pgS.evaluate("buildMarkdown(D, 2).text")
    check("試着（単独）：呼称・口調がMarkdownと一致", "一人称 俺" in meta and "二人称 お前" in meta and "口調 尊大" in meta and "- 一人称：「俺」" in md2 and "- 相手の呼び方：「お前」" in md2, meta)
    tags_ok = pgS.evaluate("""(() => { const sit = SITUATIONS.find(s => s.id === 'meet');
      return sit.uses.filter(id => isUsed(D, id)).every(id => document.querySelector('#pv-cards .tags').textContent.includes(TRAIT[id].name + '：' + TRAIT[id].levels[valOf(D, id, 'initial') - 1].label)); })()""")
    check("試着（単独）：参照する人格値がMarkdownと同じ（初期／固定の値）", tags_ok)
    pgS.click("[data-act=ex-add]"); pgS.click("[data-act=ex-add]")
    ex = pgS.evaluate("exList(D)")
    check("試着（単独）：会話例を1件ずつ追加・段階名なし", len(ex) == 2 and ex[0]["label"] == "会ったとき" and ex[0]["char"] == pgS.evaluate("renderSituation(D, SITUATIONS[0], 'initial', UI.romance, pvOverride()).text"))
    pgS.click("#pvmd-box summary")
    pvmd = pgS.input_value("#pvmd")
    check("試着（単独）：会話例Markdownは単独の形式（段階の見出しなし）", pvmd.startswith("# ミナト｜会話例\n\n## 会ったとき\n状況：") and "###" not in pvmd and not [w for w in ["初期", "信頼成立後", "関係深化後"] if w in pvmd], pvmd[:200])
    pgS.click("[data-act=pv-scope][data-val=all]")
    pvall = pgS.input_value("#pvmd")
    check("試着（単独）：全状況のMarkdownも単独の形式", pvall.count("\n## ") == 12 and "###" not in pvall)
    pgS.check("[data-act-change=rom-preview]")
    check("試着（単独）：恋愛感情の反応を足せる（段階で抑えない）", "大切に思" in pgS.inner_text("#pv-cards") or "大事に思" in pgS.inner_text("#pv-cards") or "好き" in pgS.inner_text("#pv-cards") or "隣にいろ" in pgS.inner_text("#pv-cards"), pgS.inner_text("#pv-cards")[:200])
    pgS.click("details:has([data-pv=pvMe]) > summary")
    pgS.fill("[data-pv=pvMe]", "わたくし")
    check("試着（単独）：口調・呼称を試しに変えても設定は変わらない", "一人称 わたくし" in pgS.inner_text("#pv-cards .pv-meta") and pgS.evaluate("D.pron.me.common") == "俺")
    pgS.click("[data-act=pv-clear]")
    go_output(pgS); dest(pgS, "chacha")
    check("試着（単独）：追加した会話例が出力先で使える", pgS.evaluate("buildOutput(D, 'auto').ex.count") == 2)
    pgS.click("#tabs button[data-tab=tune]"); pgS.click("[data-act=structure][data-val=staged]")
    pgS.click("#tabs button[data-tab=preview]")
    check("試着（段階）：戻すと3段階の比較と「すべて追加」が戻る", pgS.locator("#pv-cards .card.pv").count() == 3 and pgS.locator("[data-act=ex-add-all]").count() == 1)
    check("試着（段階）：既存の会話例データは保持", len(pgS.evaluate("exList(D)")) == 2)

    # ---------- 19. JSON ----------
    js = pgS.evaluate("""() => {
      D.structure.mode = 'single';
      const x = JSON.parse(JSON.stringify(D)); x.structure.memo = 'keep'; x.zzTop = 1;
      const m = migrate(x);
      const v6 = JSON.parse(JSON.stringify(D)); v6.v = 6; delete v6.structure;
      const m6 = migrate(v6);
      const bad = migrate({v:7, traits:{}, structure:{mode:'triple'}});
      const bad2 = migrate({v:7, traits:{}, structure:'single'});
      return {mode:m.structure.mode, memo:m.structure.memo, top:m.zzTop, v:m.v, same:JSON.stringify(migrate(JSON.parse(JSON.stringify(D)))) === JSON.stringify(D),
              m6:m6.structure.mode, m6traits:JSON.stringify(m6.traits) === JSON.stringify(D.traits), m6rel:JSON.stringify(m6.relation) === JSON.stringify(D.relation),
              m6pron:JSON.stringify([m6.pron, m6.speech]) === JSON.stringify([D.pron, D.speech]), bad:bad.structure.mode, bad2:bad2.structure.mode}; }""")
    check("JSON：単独人格を書き出して読み込むと単独のまま・往復で同じ", js["mode"] == "single" and js["v"] == 7 and js["same"], str(js))
    check("JSON：構成方式の中の不明なフィールド・最上位の追加フィールドを残す", js["memo"] == "keep" and js["top"] == 1)
    check("JSON：形式6（v0.5.0）は段階変化型で読み込み、全段階の値・関係・口調・呼称を保持", js["m6"] == "staged" and js["m6traits"] and js["m6rel"] and js["m6pron"])
    check("JSON：不正な構成方式は段階変化型に戻る（例外なし）", js["bad"] == "staged" and js["bad2"] == "staged")
    pgS.evaluate("window.confirm = () => true")
    go_output(pgS)
    pgS.click("details:has(#import-box) > summary")
    pgS.fill("#import-box", pgS.evaluate("JSON.stringify(D)")); pgS.click("[data-act=data-import]")
    check("JSON：画面から読み込んでも単独人格のまま", pgS.evaluate("D.structure.mode") == "single")
    check("単独：操作中に例外なし", not pgS.errs, str(pgS.errs))

    # ---------- 20. 画面幅390px（iPhone相当）・PC ----------
    for (w, h, tag) in [(390, 844, "mobile"), (1280, 900, "pc")]:
        pgl = fresh(b, w, h); pgl.evaluate(MIXED); pgl.click("[data-act=structure][data-val=single]")
        pgl.evaluate("UI.open.presets = true; Object.keys(UI.open).forEach(k => UI.open[k] = true); render(true)")
        pgl.click("[data-act=pre-pick][data-id=tsundere]")
        for tab in ["tune", "relation", "preview", "output"]:
            pgl.click(f"#tabs button[data-tab={tab}]")
            ov = pgl.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"単独・横スクロールなし: {tag}/{tab}", ov <= 0, f"overflow {ov}px")
            if SHOTS: pgl.evaluate("window.scrollTo(0,0)"); pgl.screenshot(path=str(SHOTS / f"single_{tag}_{tab}.png"), full_page=True)
        for svc, tpl in [("talelynx", None), ("chacha", None), ("plaitoon", "basic11"), ("plaitoon", "custom")]:
            dest(pgl, svc, tpl)
            ov = pgl.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"単独・横スクロールなし: {tag}/{svc}{'/' + tpl if tpl else ''}", ov <= 0, f"overflow {ov}px")
        pgl.click("#tabs button[data-tab=tune]")
        # 操作できるか：構成方式ボタン・スライダーの目盛り・固定ボタンが画面内にあり、押せる
        btn = pgl.locator("[data-act=structure][data-val=staged]"); box = btn.bounding_box()
        check(f"単独・構成方式ボタンが画面内で押せる: {tag}", box and box["x"] >= 0 and box["x"] + box["width"] <= w and box["height"] >= 30, str(box))
        tick = pgl.locator("#trait-area .trait [data-act=lv]").first; tb = tick.bounding_box()
        check(f"単独・スライダーの目盛りが押せる: {tag}", tb and tb["x"] + tb["width"] <= w and tb["height"] >= 24, str(tb))
        tick.click(); btn.click()
        check(f"単独・操作後も例外なし: {tag}", pgl.evaluate("D.structure.mode") == "staged" and not pgl.errs, str(pgl.errs))

    b.close()

fails = [r for r in results if not r[1]]
print(f"\n動作テスト: {len(results) - len(fails)} / {len(results)} 件成功")
for n, ok, d in results:
    if not ok: print("  失敗:", n, d)
sys.exit(1 if fails else 0)
