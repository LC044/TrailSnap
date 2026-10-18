// Cache only the entry's static dependency graph. Lazy routes are cached on use
// or imported by the network-aware idle preloader, never by SW installation.
export function collectShellAssets(bundle) {
  const assets = new Set()
  function visit(fileName) {
    if (assets.has(fileName)) return
    const chunk = bundle[fileName]
    if (!chunk) return
    assets.add(fileName)
    if (chunk.type !== 'chunk') return
    for (const dependency of chunk.imports) visit(dependency)
    for (const css of chunk.viteMetadata?.importedCss || []) assets.add(css)
    for (const asset of chunk.viteMetadata?.importedAssets || []) assets.add(asset)
  }
  for (const chunk of Object.values(bundle)) {
    if (chunk.type === 'chunk' && chunk.isEntry) visit(chunk.fileName)
  }
  // CSS font URLs are not consistently represented in chunk importedAssets.
  for (const fileName of Object.keys(bundle)) {
    if (/\.(?:woff2?|ttf)$/i.test(fileName)) assets.add(fileName)
  }
  return [...assets].map(fileName => `/${fileName}`)
}
