#!/usr/bin/env bash

# -----------------------------------------------------------------------------
# Script Name: read_files_and_content.sh
#
# Description:
# This script collects all files under a specified input directory (excluding
# any `.git` folders and their contents) and concatenates them, in
# deterministic sorted order, into a single output file.
#
# Usage:
# ./read_files_and_content.sh
#
# Arguments:
# Path to the directory to search files in.
# Path to the file where concatenated content is written.
#
# Example:
# ./read_files_and_content.sh "./pipeline" "pipeline.md"
#
# Notes:
# - Overwrites if it already exists.
# - Ensures deterministic order by sorting file paths.
# - Skips `.git` directories and everything inside them.
# -----------------------------------------------------------------------------

set -euo pipefail
IFS=$'\n\t'

# Usage check
if [ "$#" -ne 2 ]; then
echo "Usage: $0 <input_dir> <output_file>"
exit 1
fi

INPUT_DIR=$1
OUTPUT_FILE=$2

# Raster & vector images
IMAGE_EXTENSIONS="png|jpg|jpeg|svg|gif|webp|ico|bmp|tiff|tif|avif|heic|heif|raw"

# Compiled binaries & object files
BINARY_EXTENSIONS="exe|dll|so|dylib|o|a|lib|bin|elf|out|class|pyc|pyo|pyd|wasm"

# Archives & packages
ARCHIVE_EXTENSIONS="zip|tar|gz|bz2|xz|zst|rar|7z|jar|war|ear|whl|egg|deb|rpm|apk|ipa"

# Fonts
FONT_EXTENSIONS="ttf|otf|woff|woff2|eot"

# Media
MEDIA_EXTENSIONS="mp3|mp4|wav|ogg|flac|aac|mkv|avi|mov|webm|m4a|m4v|pdf"

# Tabular & columnar data (binary formats — not human-readable)
TABULAR_EXTENSIONS="parquet|arrow|feather|orc|avro|lance"

# Delimited text data (large — skipped to avoid noise)
DELIMITED_EXTENSIONS="csv|tsv|psv|dsv"

# JSON
JSON_EXTENSIONS="geojson"

# Database files (binary — SQLite, DuckDB, etc.)
DATABASE_EXTENSIONS="db|sqlite|sqlite3|duckdb|mdb|accdb|fdb|sdf|h5|hdf5|nc|grib|grib2"

DEPENDENCIES_EXTENSIONS="lock"

BINARY_PATTERN="\.($IMAGE_EXTENSIONS|$BINARY_EXTENSIONS|$ARCHIVE_EXTENSIONS|$FONT_EXTENSIONS|$MEDIA_EXTENSIONS|$TABULAR_EXTENSIONS|$DELIMITED_EXTENSIONS|$DATABASE_EXTENSIONS|$DEPENDENCIES_EXTENSIONS|JSON_EXTENSIONS)$"


find "$INPUT_DIR" \
  -type d \( -name .git -o -name __pycache__ -o -name dbt -o -name '.venv*' -o -name .pytest_cache -o -name logs -o -name node_modules -o -name generated -o -name data \) -prune -o \
  -type f \
  ! -name "*.csv" \
  ! -name "package-lock.json" \
  ! -name "yarn.lock" \
  ! -name "pnpm-lock.yaml" \
  ! -name "composer.lock" \
  ! -name "poetry.lock" \
  ! -name "Pipfile.lock" \
  ! -name "*.lock" \
  -print | sort | while read -r FILE; do

  EXT="${FILE##*.}"
  EXT="${EXT,,}"

  case "$EXT" in
    py)                     LANG_HINT="python" ;;
    js|mjs|cjs)             LANG_HINT="javascript" ;;
    ts|tsx)                 LANG_HINT="typescript" ;;
    jsx)                    LANG_HINT="jsx" ;;
    sh|bash)                LANG_HINT="bash" ;;
    sql)                    LANG_HINT="sql" ;;
    yml|yaml)               LANG_HINT="yaml" ;;
    json|geojson)           LANG_HINT="json" ;;
    toml)                   LANG_HINT="toml" ;;
    ini|cfg|conf)           LANG_HINT="ini" ;;
    md|markdown)            LANG_HINT="markdown" ;;
    html|htm)               LANG_HINT="html" ;;
    css|scss|sass)          LANG_HINT="css" ;;
    xml)                    LANG_HINT="xml" ;;
    dockerfile)             LANG_HINT="dockerfile" ;;
    makefile|mk)            LANG_HINT="makefile" ;;
    rb)                     LANG_HINT="ruby" ;;
    go)                     LANG_HINT="go" ;;
    rs)                     LANG_HINT="rust" ;;
    java)                   LANG_HINT="java" ;;
    c|h)                    LANG_HINT="c" ;;
    cpp|cc|hpp)             LANG_HINT="cpp" ;;
    txt)                    LANG_HINT="text" ;;
    *)                      LANG_HINT="" ;;
  esac

  echo "## $FILE"
  echo

  if echo "$FILE" | grep -qiE "$BINARY_PATTERN"; then

    echo '```'

    case "$EXT" in
      png|jpg|jpeg|svg|gif|webp|ico|bmp|tiff|tif|avif|heic|heif|raw)
        echo "<binary: image>" ;;

      exe|dll|so|dylib|o|a|lib|bin|elf|out)
        echo "<binary: compiled>" ;;

      class|pyc|pyo|pyd)
        echo "<binary: bytecode>" ;;

      wasm)
        echo "<binary: wasm>" ;;
      zip|tar|gz|bz2|xz|zst|rar|7z|jar|war|ear|whl|egg|deb|rpm|apk|ipa)
        echo "<binary: archive>" ;;

      ttf|otf|woff|woff2|eot)
        echo "<binary: font>" ;;

      mp3|wav|ogg|flac|aac|m4a)
        echo "<binary: audio>" ;;

      mp4|mkv|avi|mov|webm|m4v)
        echo "<binary: video>" ;;

      pdf)
        echo "<binary: pdf>" ;;
      *)
        echo "<binary>" ;;
    esac

  else
    echo "\`\`\`${LANG_HINT}"
    cat "$FILE"
  fi

  echo
  echo '```'
  echo

done > "$OUTPUT_FILE"