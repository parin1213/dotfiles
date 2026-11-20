# VSCodeが渡すworkspaceFolderを基準にする。通常のターミナルには適用しない。
[[ ${TERM_PROGRAM-} == vscode ]] || return 0

_vscode_update_prompt() {
  emulate -L zsh
  local current=${PWD:A}
  local root=${VSCODE_PROJECT_ROOT-}
  local shown=$current prefix absolute
  local -a parts

  if [[ $root == /* && -d $root ]]; then
    root=${root:A}
    prefix="${root%/}/"
    if [[ $current == "$root" ]]; then
      shown=.
    elif [[ $current == "$prefix"* ]]; then
      shown="./${current#"$prefix"}"
    fi
  fi

  # プロジェクト内の相対パスは省略せず、外側だけ末尾3階層を残す。
  if [[ $shown == /* ]]; then
    absolute=${current#/}
    parts=("${(@s:/:)absolute}")
    if (( ${#parts} > 3 )); then
      shown="…/${(j:/:)parts[-3,-1]}"
    fi
  fi

  # パス中の制御文字と%をプロンプト命令として解釈させない。
  shown=${(V)shown}
  PROMPT="${shown//\%/%%} %# "
  RPROMPT=''
}

# パスに含まれる$()や!は文字として表示する。
unsetopt promptsubst promptbang
setopt promptpercent
autoload -Uz add-zsh-hook
add-zsh-hook -d precmd _vscode_update_prompt
add-zsh-hook precmd _vscode_update_prompt
_vscode_update_prompt
