#!/usr/bin/env bash
# Wrap the PyInstaller binary in a .app bundle and pack a .dmg. Ad-hoc signed;
# not notarized, so first launch is right-click -> Open.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${APP_VERSION:?APP_VERSION must be set}"
APP="dist/ai-screenshot.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp dist/ai-screenshot "$APP/Contents/MacOS/ai-screenshot"
chmod +x "$APP/Contents/MacOS/ai-screenshot"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>ai-screenshot</string>
  <key>CFBundleDisplayName</key><string>ai-screenshot</string>
  <key>CFBundleIdentifier</key><string>com.github.tocong282.ai-screenshot</string>
  <key>CFBundleExecutable</key><string>ai-screenshot</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

codesign --force --deep --sign - "$APP" 2>/dev/null || echo "ad-hoc codesign skipped"
hdiutil create -quiet -volname "ai-screenshot $VERSION" -srcfolder "$APP" \
  -ov -format UDZO "dist/ai-screenshot-$VERSION-macos-arm64.dmg"
rm -rf "$APP"
echo "built dist/ai-screenshot-$VERSION-macos-arm64.dmg"
