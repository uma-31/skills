# コミット作成ガイド

コミットメッセージは、`show-rules`が示す制約と、以下の判断基準を踏まえて書くこと。

## コマンドの使い方

各フラグは次のように指定する。

```bash
uv run scripts/commit.py create --dry-run \
  --type feat \
  --scope skills \
  --subject "add commit skill" \
  --body "Explain why the change was needed, not what the diff already shows."
```

## `type`

typeの意味は`show-rules`の説明に従う。
該当するtypeが無いからといって、意味の異なるtypeで代用してはならない。

## `subject`

英語で書く場合は命令形を用いる（"added"や"adds"ではなく"add"）。
触ったファイルではなく変更内容を説明すること。
`fix(auth): update auth.py`より`fix(auth): reject expired tokens`が良い。

## `body`

変更の理由を書く。差分から読み取れること（何をどう変更したか）は書かない。
検討して見送った代替案や、書かなければレビュアーが質問することになる背景は、判断に必要な場合のみ補足し、無理に埋めない。
動機が自明な変更では、`show-rules`で`body`が必須と示されない限り省略してよい。
段落ごとに`--body`を指定する。長いbodyは`--body-file PATH`（`-`で標準入力）で渡せる。
bodyの行を`#`で始めない。commit-msgフックがコメントとして無視してしまう。Issueへの参照はfooterに書く。

## `breaking`

既存の呼び出し側が依存している挙動を削除・変更する場合は`--breaking`を渡し、併せて何が壊れ代わりに何をすべきかを説明する`--breaking-description`を指定する。
どの記法を使うかはスクリプトがリポジトリの規約に従って適用する。

## `footer`

issue参照やメタデータには`--footer "Refs: #123"`を使う。
トークン中の空白は`-`に置き換える（`Reviewed by`ではなく`Reviewed-by`）。
