#!/bin/sh
set -eu

ensure_vosk_model() {
    if [ "${VOSK_AUTO_DOWNLOAD:-1}" != "1" ]; then
        return
    fi

    model_path="${VOSK_MODEL_PATH:-}"
    model_url="${VOSK_MODEL_URL:-}"

    if [ -z "$model_path" ] || [ -z "$model_url" ]; then
        return
    fi

    if [ -f "$model_path/am/final.mdl" ] && [ -f "$model_path/conf/model.conf" ]; then
        return
    fi

    model_dir="$(dirname "$model_path")"
    model_name="$(basename "$model_path")"
    tmp_dir="$(mktemp -d)"
    archive_path="$tmp_dir/model.zip"
    extracted_root="$tmp_dir/unpacked"

    cleanup() {
        rm -rf "$tmp_dir"
    }

    trap cleanup EXIT HUP INT TERM

    mkdir -p "$model_dir" "$extracted_root"

    echo "Downloading Vosk model into $model_path"
    curl -fsSL "$model_url" -o "$archive_path"
    unzip -q "$archive_path" -d "$extracted_root"

    extracted_dir="$(find "$extracted_root" -mindepth 1 -maxdepth 2 -type d -name "$model_name" | head -n 1)"
    if [ -z "$extracted_dir" ]; then
        extracted_dir="$(find "$extracted_root" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    fi

    if [ -z "$extracted_dir" ] || [ ! -f "$extracted_dir/am/final.mdl" ] || [ ! -f "$extracted_dir/conf/model.conf" ]; then
        echo "Failed to prepare Vosk model from $model_url" >&2
        exit 1
    fi

    rm -rf "$model_path"
    mv "$extracted_dir" "$model_path"
    echo "Vosk model is ready at $model_path"
}

ensure_vosk_model

exec "$@"
