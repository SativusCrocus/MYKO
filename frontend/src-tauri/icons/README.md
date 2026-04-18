# Icons

Tauri's bundler expects the following files before a release build:

- `32x32.png`
- `128x128.png`
- `128x128@2x.png`
- `icon.icns` (macOS)
- `icon.ico` (Windows)

Generate them from a single 1024×1024 source with:

```bash
npm install -D @tauri-apps/cli
npx tauri icon /path/to/source.png
```

During `npm run tauri dev` the bundle step is skipped so missing icons are not fatal.
