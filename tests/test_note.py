"""記事パイプラインのテスト（AI を呼ばない部分）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from notelib import article, checks, images, links, sheet  # noqa: E402
from notelib.config import Config  # noqa: E402
from notelib.research import judge_urls, tier_of  # noqa: E402

CFG = Config({
    "note": {"price_single": 200, "price_monthly": 590, "price_monthly_after": 790, "monthly_raise_at": 100,
             "magazine_name": "テスト", "disclaimers": ["期待値は目安です。", "18歳未満は遊技できません。"],
             "allowed_numbers": [18], "number_check_min": 10, "banned_words": ["実在ホール"]},
    "links": {"paid_magazine": "", "articles": {"m041": "https://note.com/x/n/abc"},
              "youtube_article_line": "▼記事\n{article}", "youtube_magazine_line": "▼月額\n{magazine}"},
    "research": {"allow_single_trusted": True,
                 "sites": {"official": [], "tier1": ["chonborista.com", "nana-press.com", "note.com/g1slotapple", "altema.jp"],
                           "tier2": ["p-world.co.jp"]},
                 "blocked": ["x.com"], "shared_hosts": ["note.com"], "not_independent": [["altema.jp", "chonborista.com"]]},
    "paths": {"ai_vtuber_root": "/nonexistent"},
})

MATS = {"machines": [{"id": "m041", "name": "モンキー", "lines": ["それ以外　400g〜"]}],
        "facts": [{"text": "天井は795G+α", "sources": [{"url": "https://chonborista.com/a"}]}],
        "conflicts": [], "strategy_notes": ["[全体の考え方] 強気に打つ"], "ev": {}}
DRAFT = {"title": "【モンキー】天井・狙い目", "lead": ["特徴です。"], "shallowest": "400G〜",
         "paid_sections": [{"heading": "条件別の狙い目", "body": "ふつうは400G〜。天井は795G+α。",
                            "sources": ["https://chonborista.com/a", "https://example.com/unknown"]}],
         "cautions": ["ハマることもあります"], "summary_table": {"columns": ["状況", "打ち始め"], "rows": [["ふつう", "400G〜"]]},
         "closing": "楽しく打とうね", "hashtags": ["モンキー"], "images": []}


class TestResearch(unittest.TestCase):
    def test_tiers_like_youtube(self):
        self.assertEqual(tier_of("https://note.com/g1slotapple/n/1", CFG)[0], "tier1")
        self.assertEqual(tier_of("https://note.com/other/n/1", CFG)[0], "other")
        self.assertEqual(tier_of("https://www.p-world.co.jp/x", CFG)[0], "tier2")

    def test_judge(self):
        self.assertEqual(judge_urls(["https://chonborista.com/a", "https://nana-press.com/b"], CFG)[0], "high")
        self.assertEqual(judge_urls(["https://chonborista.com/a"], CFG)[0], "single")
        # アルテマとちょんぼりすたは同じ出どころなので2つと数えない
        self.assertEqual(judge_urls(["https://chonborista.com/a", "https://altema.jp/b"], CFG)[0], "single")
        self.assertIsNone(judge_urls(["https://x.com/a"], CFG)[0])


class TestArticle(unittest.TestCase):
    def build(self, kind="machine", draft=DRAFT):
        return article.build(draft, MATS, CFG, kind)

    def test_structure_and_checks(self):
        md, unknown = self.build()
        self.assertEqual(md.count(checks.PAYWALL), 1)
        self.assertIn("200円", md)
        self.assertIn("## 参考", md)
        self.assertEqual(unknown, ["https://example.com/unknown"])   # 材料に無い出典は参考に載せない
        self.assertNotIn("example.com", md)
        self.assertIn("強気に打つ", md)                              # 運営者の考え方は strategy_notes から
        allowed = {400.0, 795.0, 18.0, 200.0, 590.0, 790.0, 100.0}
        self.assertEqual(checks.check_article(md, "machine", MATS, allowed, CFG), [])

    def test_number_check_catches_new_numbers(self):
        d = {**DRAFT, "paid_sections": [{"heading": "x", "body": "天井は1234Gです。", "sources": []}]}
        md, _ = self.build(draft=d)
        probs = checks.check_article(md, "machine", MATS, {400.0, 795.0, 18.0}, CFG)
        self.assertTrue(any("1234" in p for p in probs))

    def test_free_has_no_paywall_and_has_guide(self):
        d = {**DRAFT, "paid_sections": [], "free_sections": [{"heading": "見る場所", "body": "液晶を見る", "sources": []}]}
        md, _ = self.build("free", d)
        self.assertNotIn(checks.PAYWALL, md)
        self.assertIn("月額マガジン", md)

    def test_free_machine_guide(self):
        # 機種ガイド（無料）：その機種の完全版へ案内し、期待値表は入れない
        mats = {**MATS, "ev": {"モンキー": {"spec_id": "monkey", "tables": {"normal": {"md": "### 表\n| a |", "label": "通常"}}}}}
        d = {**DRAFT, "paid_sections": [], "free_sections": [{"heading": "打ち方", "body": "左から", "sources": []}]}
        md, _ = article.build(d, mats, CFG, "free")
        self.assertIn("モンキーの天井・狙い目・やめどき完全版", md)
        self.assertIn("https://note.com/x/n/abc", md)
        self.assertEqual(md.count("https://note.com/x/n/abc"), 1)     # 機種ごとの一覧に同じ記事を重ねない
        self.assertNotIn("<!-- auto:ev -->", md)

    def test_ev_table_has_image_marker(self):
        mats = {**MATS, "ev": {"モンキー": {"spec_id": "monkey", "tables": {"normal": {"md": "### 表\n\n| a |\n|---|\n| 1 |", "label": "通常", "border_toka": 350}}}}}
        md, _ = article.build(DRAFT, mats, CFG, "machine")
        self.assertIn("images/table_ev_monkey_normal.png", md)
        self.assertIn("強気ボーダー・通常：350G〜", md)

    def test_banned_phrases(self):
        d = {**DRAFT, "closing": "必ず勝てる台だよ"}
        md, _ = self.build(draft=d)
        self.assertTrue(any("必ず勝てる" in p for p in checks.check_article(md, "machine", MATS, {400.0, 795.0}, CFG)))


class FakeDraw:
    """1文字50px として幅を測る（フォントに関係なく改行を確かめる）。"""
    def textlength(self, text, font=None):
        return 50 * len(text)


class TestImages(unittest.TestCase):
    def test_bubble_wrap(self):
        lines = images._wrap_px(FakeDraw(), "ST後は即ヤメが基本！背景だけチェックしてね", None, 520)
        self.assertEqual(lines[0], "ST後は即ヤメが基本！")                # 文の終わりで改行
        self.assertGreater(len(lines[-1]), 2)                             # 最後の行が1〜2文字だけにならない
        self.assertEqual("".join(lines), "ST後は即ヤメが基本！背景だけチェックしてね")
        for ln in lines[1:]:
            self.assertNotIn(ln[0], images._NO_LINE_START)


class TestSheetAndLinks(unittest.TestCase):
    def test_search_normalization(self):
        ms = [sheet.Machine("m041", "モンキー", ["モンキーターンV"], "", []), sheet.Machine("m046", "リコリコ", ["リコリス"], "", [])]
        self.assertEqual(sheet.find(ms, "ﾓﾝｷｰ")[0].id, "m041")
        self.assertEqual(sheet.find(ms, "りこりす")[0].id, "m046")

    def test_youtube_block(self):
        self.assertEqual(links.youtube_block(CFG, "m041", "モンキー"), "▼記事\nhttps://note.com/x/n/abc")
        self.assertEqual(links.youtube_block(CFG, "m999", "なし"), "")   # URL が空なら何も出さない


if __name__ == "__main__":
    unittest.main()
