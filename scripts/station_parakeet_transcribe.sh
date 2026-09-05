#!/usr/bin/env bash
# Hermes command-STT adapter for the loopback-only Station Parakeet service.
set -Eeuo pipefail

input=${1:-}
output=${2:-}
language=${3:-}

[[ "$input" == /* && "$output" == /* ]] || {
  echo "input and output must be absolute paths" >&2
  exit 2
}
[[ "$input" =~ ^/[A-Za-z0-9._/-]+$ && "$output" =~ ^/[A-Za-z0-9._/-]+$ ]] || {
  echo "input and output contain unsupported path characters" >&2
  exit 2
}
[[ -f "$input" && ! -L "$input" ]] || {
  echo "input must be a regular non-symlink file" >&2
  exit 2
}
[[ "$(realpath -e -- "$input")" == "$input" ]] || {
  echo "input path must not traverse a symlink or alias" >&2
  exit 2
}
[[ ! -e "$output" && ! -L "$output" ]] || {
  echo "output must not already exist" >&2
  exit 2
}
output_parent=$(dirname -- "$output")
[[ -d "$output_parent" && ! -L "$output_parent" ]] || {
  echo "output parent must be a real directory" >&2
  exit 2
}
[[ "$(realpath -e -- "$output_parent")" == "$output_parent" ]] || {
  echo "output parent must not traverse a symlink or alias" >&2
  exit 2
}
input_size=$(stat -c '%s' -- "$input")
(( input_size <= 26214400 )) || {
  echo "input exceeds Parakeet's 25 MiB upload limit" >&2
  exit 2
}

temporary=$(mktemp --tmpdir="$output_parent" .station-parakeet.XXXXXX)
trap 'rm -f -- "$temporary"' EXIT
form=(--form "file=@${input}" --form-string "response_format=text")
if [[ -n "$language" && "$language" != auto ]]; then
  [[ "$language" =~ ^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$ ]] || {
    echo "invalid language code" >&2
    exit 2
  }
  form+=(--form-string "language=${language}")
fi
curl --fail --silent --show-error --max-time 300 \
  "${form[@]}" http://127.0.0.1:5092/v1/audio/transcriptions > "$temporary"
[[ -s "$temporary" ]] || {
  echo "Parakeet returned an empty transcript" >&2
  exit 1
}
(( $(stat -c '%s' -- "$temporary") <= 1048576 )) || {
  echo "Parakeet transcript exceeds the 1 MiB safety limit" >&2
  exit 1
}
chmod 0600 "$temporary"
# The output may have appeared while HTTP was in flight. Publish atomically
# without replacing any entry or following a raced-in directory/symlink. The
# private temporary and output share a filesystem, so link(2) is sufficient.
ln --no-target-directory -- "$temporary" "$output"
rm -- "$temporary"
trap - EXIT
