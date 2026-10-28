# YouTube パイプライン（C:\dev\ai-vtuber）とのつなぎ方

このリポジトリは、Windows PC の `C:\dev\ai-vtuber` の隣（例：`C:\dev\note`）に置いて使う。
`config/channel.note.yaml` の `paths.ai_vtuber_root`（既定 `../ai-vtuber`）で場所を指定する。

## 1. 置き場所と実行

```
cd C:\dev
git clone https://github.com/lemo3323/note
cd note
uv run --project ..\ai-vtuber python pipeline\note.py --machine モンキー
```

- Python のライブラリ（requests・PyYAML・numpy・Pillow）は ai-vtuber の環境にあるものを使う（`uv run --project ..\ai-vtuber`）
- 下書きは `claude -p`（Claude Code）が書く。AI を呼ばずに下書きを渡すときは `--draft <json>`、材料とプロンプトだけ作るときは `--prompt-only`

## 2. 共有するもの（ai-vtuber 側は変えない）

| ai-vtuber のファイル | note での使い方 |
|---|---|
| `data/nerai_latest.csv` | 狙い目シート（最優先の材料） |
| `data/research/<ID>.json` | research 工程の調べた情報（採用済みの facts だけ） |
| `config/channel.yaml` の `research:` | 格付け（tier1 など）。note でも同じものを使う |
| `pipeline/steps/research.py` | `tier_of`・`url_exists` をそのまま使う（判定をそろえるため） |
| `pipeline/remotion.py`・`renderer/`・`assets/model.vrm` | ひよりの画像（Thumbnail コンポジションの静止画） |

## 3. config/channel.yaml に足すもの

`config/channel.note.yaml` の `note:` と `links:` の節を、ai-vtuber の `config/channel.yaml` の最後にそのまま貼る
（`note.price_single` / `note.price_monthly` / `note.price_premium` / `links.paid_magazine` など）。
貼らなくても note 側は `channel.note.yaml` の値で動く。URL（`links.paid_magazine`・`links.articles`）はあとで運営者が入れる。

## 4. ai-vtuber の CLAUDE.md に足す1行

```
- 収益化の方針（YouTube は入口、note で収益化。価格・売り・12週間の目標）は ..\note\docs\strategy.md。note の記事は ..\note\pipeline\note.py
```

## 5. YouTube の説明文に note の案内を入れる

`pipeline/steps/metadata.py` で説明文を組み立てているところ（`parts.append("▼参考\n" + ...)` の行の前）に、次を足す。
URL が空のあいだは何も出ないので、先に入れておいてよい。

```python
    # note の記事・月額マガジンへの案内（URL は note の config の links: に入れる。空なら出さない）
    try:
        note_pipe = ROOT.parent / "note" / "pipeline"          # ROOT は ai-vtuber のフォルダ
        if str(note_pipe) not in sys.path:
            sys.path.insert(0, str(note_pipe))
        from notelib.config import load_config as load_note_config
        from notelib.links import youtube_block
        ms = plan.get("machines") or []
        if len(ms) == 1:                                         # 1機種の動画だけ
            block = youtube_block(load_note_config(), ms[0].get("id", ""), ms[0].get("name", ""))
            if block:
                parts.append(block)
    except Exception as e:  # 案内が入らなくても動画は作れる
        log.warning("note の案内を入れられませんでした: %s", e)
```

- `ROOT`・`plan`・`parts`・`log` は metadata.py の中の名前に合わせて読み替える（この環境から ai-vtuber のコードは見られないため、名前は未確認）
- 文言は `links.youtube_article_line` / `links.youtube_magazine_line` で変えられる

## 6. 画像（ひより）

- `python pipeline\note.py --render-images <フォルダ名>` で、ai-vtuber の Remotion（`Thumbnail` コンポジション）を使って描く
  - 見出し画像 1280×670、本文 1280×720 を最大2枚。表情（happy・surprised・neutral・relaxed など）でポーズも変わる
  - 背景は `note.images.background`、空なら直近の動画のサムネと同じ背景
- **この環境（クラウド）では ai-vtuber が無いので描画は未確認**。最初の1回は描けた画像を目で確認する
- VRM のメタ情報：作者 re（運営者本人）、商用は個人の営利利用まで可（personalProfit）、アバターとしての利用は別途許可された人のみ（作者本人なので問題なし）、再配布不可。note に画像として載せるのは個人の営利利用の範囲内
- 機種画像・実機画像は使わない（Thumbnail の machineImage は渡さない）

## 7. 公開リポジトリについて

lemo3323/note は公開リポジトリなので、有料記事の本文・狙い目シートの写し・自作の期待値表は `.gitignore` で除外している。
GitHub で Private にしたら、`.gitignore` の上半分（「公開リポジトリのあいだ push しないもの」）を消してよい。
