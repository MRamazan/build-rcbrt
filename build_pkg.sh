#!/bin/bash
set -e

APP_NAME="Recbert AI"
APP_DIR="dist/mac/$APP_NAME.app"
PKG_OUTPUT="dist/RecbertAI-Setup.pkg"
SCRIPTS_DIR="pkg-scripts"
PAYLOAD_DIR="pkg-payload"

mkdir -p "$SCRIPTS_DIR"
mkdir -p "$PAYLOAD_DIR/Applications"

cp -r "$APP_DIR" "$PAYLOAD_DIR/Applications/"

RESOURCES_DIR="$PAYLOAD_DIR/Applications/$APP_NAME.app/Contents/Resources"

mkdir -p "$RESOURCES_DIR/backend"
mkdir -p "$RESOURCES_DIR/python"

cp main_local.py   "$RESOURCES_DIR/backend/"
cp utils.py        "$RESOURCES_DIR/backend/"
cp options.py      "$RESOURCES_DIR/backend/"
cp config.py       "$RESOURCES_DIR/backend/"
cp loggers.py      "$RESOURCES_DIR/backend/"
cp templates.py    "$RESOURCES_DIR/backend/"
cp requirements.txt "$RESOURCES_DIR/backend/"

cp -r models       "$RESOURCES_DIR/backend/models"
cp -r dataloaders  "$RESOURCES_DIR/backend/dataloaders"
cp -r trainers     "$RESOURCES_DIR/backend/trainers"
cp -r datasets     "$RESOURCES_DIR/backend/datasets"
cp -r Data         "$RESOURCES_DIR/backend/Data"

cp -r python-embed-mac/. "$RESOURCES_DIR/python/"

cp postinstall "$SCRIPTS_DIR/postinstall"
chmod +x "$SCRIPTS_DIR/postinstall"

pkgbuild \
  --root "$PAYLOAD_DIR" \
  --scripts "$SCRIPTS_DIR" \
  --identifier "com.recbert.ai" \
  --version "1.0.0" \
  --install-location "/" \
  "$PKG_OUTPUT"

echo "PKG built: $PKG_OUTPUT"
