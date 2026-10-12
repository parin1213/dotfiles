#!/bin/bash
# モニターの入力を DDC/CI（m1ddc）で切り替える。Mac の Stream Deck の PC⇄Mac キーから呼ぶ。
#   例: switch-input.sh U2725QE 15   # Dell を DisplayPort（PC）にする
# 入力の値は Dell U2725QE で確かめたもの: 15 = DP（PC）、17 = HDMI、25 = Thunderbolt 4（Mac）。
# m1ddc の display 番号は接続順で変わるので、display list の名前で対象のモニターを選ぶ。
set -euo pipefail
model=${1:?モデル名（例: U2725QE）}
source=${2:?入力の値（例: 15）}
export PATH="/opt/homebrew/bin:$PATH"
command -v m1ddc >/dev/null || { echo 'm1ddc が無い（brew install m1ddc）' >&2; exit 1; }

n=$(m1ddc display list | grep -F "$model" | head -1 | sed -E 's/^\[([0-9]+)\].*/\1/')
[ -n "$n" ] || { echo "DDC で $model が見つからなかった" >&2; exit 1; }
m1ddc display "$n" set input "$source"
