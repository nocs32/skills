#!/usr/bin/env bash
# Split one branch's commits into a stack of layer branches, by path.
#
#   split-stack.sh <source-branch> <trunk> <spec-file> [--plan] [--from <commit>] [--layer <branch>]
#
# --plan prints what every layer would receive (pick / split per commit) and touches nothing.
#
# The spec file lists layers bottom to top, one per line:  <branch>|<scope>|<path-regex>
#   branch      the layer branch to build (created on the trunk, or on the layer below)
#   scope       the commit scope written into a commit this script has to split, e.g. api
#   path-regex  extended regex; a file belongs to the first layer whose regex matches it
# Lines starting with # are ignored.
#
# A file no layer claims follows the commit it arrives in: the layer of that commit's claimed
# files when they all sit in one layer, otherwise the first code layer — the first whose scope is
# not `docs`, since a docs layer carries documents only.
#
# Each source commit lands on every layer it touches. A commit wholly inside one layer is
# cherry-picked as is. A commit spanning layers is split: each layer gets the path-restricted patch
# as a new commit with the original subject, body, author and date, and the scope in the subject
# (`type(scope):` or `type[scope]:`) swapped for the layer's. A whole-commit pick keeps its scope
# unless it is `all`, which becomes the layer's scope. Commits are written with --no-verify: they
# re-lay history that may predate a commit-message hook, and a layer may span modules. On a
# conflict the script stops with the layer branch at the last good commit and prints the commit to
# resolve; commit the resolution yourself, then rerun with --from <next-commit> --layer <that-branch>.
#
# Environment:
#   LOCKFILE_RE  extended regex for lockfiles (default: common JavaScript lockfiles)
#   MANIFEST_RE  extended regex for the manifests a lockfile records (default: package.json)
set -euo pipefail

LOCKFILE_RE=${LOCKFILE_RE:-'(^|/)(pnpm-lock\.yaml|package-lock\.json|yarn\.lock|bun\.lockb?)$'}
MANIFEST_RE=${MANIFEST_RE:-'(^|/)package\.json$'}

# Editors and IDEs run `git status` on every file change and hold .git/index.lock for a moment;
# a git command that needs the index can lose that race. Retry a few times before giving up.
retry() {
    local n
    for n in 1 2 3 4 5; do
        if "$@" 2>"$err_file"; then return 0; fi
        grep -q 'index.lock' "$err_file" || return 1
        sleep 1
    done
    return 1
}
err_file=$(mktemp); patch_file=$(mktemp)
trap 'rm -f "$err_file" "$patch_file"' EXIT
# A watcher touching a file between two steps leaves the index stat-stale, and `git apply --index`
# then refuses with "does not match index"; refreshing the stat cache first clears the false alarm.
apply_patch() { git update-index -q --refresh; git apply --index "$1"; }
pick() { git update-index -q --refresh; git cherry-pick -n "$1"; }

source_branch=${1:?source branch}; trunk=${2:?trunk}; spec=${3:?spec file}; shift 3
from=""; only_layer=""; plan=0
while [ $# -gt 0 ]; do
    case $1 in
        --plan) plan=1; shift ;;
        --from) from=$2; shift 2 ;;
        --layer) only_layer=$2; shift 2 ;;
        *) echo "unknown flag $1" >&2; exit 2 ;;
    esac
done

branches=(); scopes=(); regexes=()
while IFS='|' read -r b s r; do
    case $b in ''|'#'*) continue ;; esac
    branches+=("$b"); scopes+=("$s"); regexes+=("$r")
done < "$spec"
layer_count=${#branches[@]}
[ "$layer_count" -ge 2 ] || { echo "spec needs at least two layers" >&2; exit 2; }
fallback=-1
for i in $(seq 0 $((layer_count - 1))); do
    if [ "${scopes[$i]}" != docs ]; then fallback=$i; break; fi
done
[ "$fallback" -ge 0 ] || { echo "spec needs a layer whose scope is not docs" >&2; exit 2; }

# layer_of <file>  -> index of the claiming layer, or -1
layer_of() {
    local i
    for i in $(seq 0 $((layer_count - 1))); do
        if echo "$1" | grep -qE "${regexes[$i]}"; then echo "$i"; return; fi
    done
    echo -1
}

# files_for <commit> <layer-index> -> the commit's files that belong to that layer, one per line
files_for() {
    local commit=$1 layer=$2 f l claimed="" unclaimed="" claimed_layers=""
    while IFS= read -r f; do
        l=$(layer_of "$f")
        if [ "$l" = -1 ]; then unclaimed+="$f"$'\n'; else claimed+="$l $f"$'\n'; claimed_layers+="$l"$'\n'; fi
    done < <(git diff-tree --no-commit-id -r --name-only "$commit")
    local distinct; distinct=$(printf '%s' "$claimed_layers" | sort -u | grep -c . || true)
    local home=$fallback; [ "$distinct" = 1 ] && home=$(printf '%s' "$claimed_layers" | head -1)
    printf '%s' "$claimed" | awk -v l="$layer" '$1 == l { sub(/^[0-9]+ /, ""); print }'
    [ "$layer" = "$home" ] && printf '%s' "$unclaimed"
    return 0
}

commits=$(git rev-list --reverse "$trunk".."$source_branch")

for i in $(seq 0 $((layer_count - 1))); do
    branch=${branches[$i]}; scope=${scopes[$i]}
    [ -n "$only_layer" ] && [ "$only_layer" != "$branch" ] && continue
    if [ "$i" = 0 ]; then parent=$trunk; else parent=${branches[$((i - 1))]}; fi
    if [ "$plan" = 1 ]; then :
    elif [ -z "$from" ]; then
        git show-ref --verify --quiet "refs/heads/$branch" && { echo "branch $branch already exists" >&2; exit 2; }
        git checkout -q -b "$branch" "$parent"
    else
        git checkout -q "$branch"
    fi
    echo "== $branch (on $parent)"
    started=0; [ -z "$from" ] && started=1
    for c in $commits; do
        if [ "$started" = 0 ]; then case $c in "$from"*) started=1 ;; *) continue ;; esac; fi
        subject=$(git log -1 --format=%s "$c")
        mine=$(files_for "$c" "$i")
        [ -z "$mine" ] && continue
        total=$(git diff-tree --no-commit-id -r --name-only "$c" | grep -c . || true)
        count=$(printf '%s\n' "$mine" | grep -c . || true)
        author=$(git log -1 --format='%an <%ae>' "$c"); date=$(git log -1 --format=%aD "$c"); body=$(git log -1 --format=%b "$c")
        if [ "$count" = "$total" ]; then
            new_subject=$(printf '%s' "$subject" | sed -E "s#^([a-z]+)([[(])all([])])#\1\2$scope\3#")
            if [ "$plan" = 1 ]; then echo "pick  ${c:0:8} $new_subject"; continue; fi
            if ! retry pick "$c" >/dev/null; then
                echo "CONFLICT cherry-picking ${c:0:8} $subject"; cat "$err_file"; git cherry-pick --abort; exit 1
            fi
            git commit -q --no-verify --author="$author" --date="$date" -m "$new_subject" -m "$body" >/dev/null
            echo "pick  ${c:0:8} $new_subject"
        else
            new_subject=$(printf '%s' "$subject" | sed -E "s#^([a-z]+)([[(])[^])]*([])])#\1\2$scope\3#")
            # The lockfile lands here; warn only when a manifest it records was sent to another layer.
            if printf '%s\n' "$mine" | grep -qE "$LOCKFILE_RE"; then
                elsewhere=$(git diff-tree --no-commit-id -r --name-only "$c" | grep -E "$MANIFEST_RE" \
                    | grep -vxF -f <(printf '%s\n' "$mine") || true)
                if [ -n "$elsewhere" ]; then
                    echo "WARN  ${c:0:8} lockfile split from its manifests — split this dependency commit per layer first"
                fi
            fi
            if [ "$plan" = 1 ]; then echo "split ${c:0:8} $new_subject"; continue; fi
            paths=()
            while IFS= read -r f; do [ -n "$f" ] && paths+=("$f"); done <<< "$mine"
            git diff-tree -p --binary "$c^" "$c" -- "${paths[@]}" > "$patch_file"
            if ! retry apply_patch "$patch_file"; then
                echo "CONFLICT splitting ${c:0:8} $subject"; cat "$err_file"; git reset -q --hard HEAD; exit 1
            fi
            git commit -q --no-verify --author="$author" --date="$date" -m "$new_subject" -m "$body" >/dev/null
            echo "split ${c:0:8} $new_subject"
        fi
    done
    from=""
done
