# note 有料記事パイプライン（波音ひより 狙い目チャンネル）

YouTube（入口）で集めた人に、note の有料記事・月額マガジンを売るための仕組み。方針は [docs/strategy.md](docs/strategy.md)、決まりは [CLAUDE.md](CLAUDE.md)。

## 記事を作る

```
python pipeline/note.py --machine モンキー                                   # 単発記事（200円）
python pipeline/note.py --special 優遇狙い --machines ヴ2,モンキー,北斗,戦コレ6  # 特殊狙い・優遇狙い
python pipeline/note.py --new-machine <機種>                                  # 新台の初週速報
python pipeline/note.py --weekly                                             # 月額：今週の狙い目＋変わった台
python pipeline/note.py --free ホールでの探し方 --machines モンキー,北斗         # 無料記事
```

- `--research` を付けると、先に note 用の調査（claude -p ＋ Web 検索）をして `data/research_note/` に保存する。採否は YouTube の research と同じ格付け＋URL確認（＋ページに値が本当に書いてあるか）
- 出力：`notes/<日付>_<種類>_<ID>/` に `article.md`・`images/`・`note_kit.txt`（貼り方）・`review_log.md`（チェック結果と承認の記録）
- 自動チェック：10以上の数字の根拠・注意書き・「ここから有料」の区切り・参考・禁止表現。通らなければ作り直し

## 自作の期待値表

```
python pipeline/ev/specs.py   # 段階1：仕様の出典を確かめて信頼度を付ける
python pipeline/ev/run.py     # 段階2〜5：シミュレーション → 答え合わせ → 合格した状況だけ表
```

状態は [docs/ev_status.md](docs/ev_status.md)、作り方は [docs/ev_method.md](docs/ev_method.md)、実データの可否は [docs/data_sources.md](docs/data_sources.md)。

## テスト

```
python -m unittest discover -s tests -v
```

## YouTube パイプラインとのつなぎ方

[docs/integration.md](docs/integration.md)（channel.yaml に足す節・説明文への案内・画像の描き方）。
