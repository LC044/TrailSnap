import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'cn.trailsnap.app',
  appName: '行影集',
  webDir: 'dist',
  backgroundColor: '#f8fafc',
  loggingBehavior: 'debug',
  server: {
    // The native app connects to user-hosted LAN servers that commonly use
    // plain HTTP. Keep the app shell on the same scheme so Android WebView
    // does not block media elements as mixed content.
    androidScheme: 'http',
  },
  android: {
    // Self-hosted instances are often exposed on a LAN over HTTP.
    allowMixedContent: true,
  },
}

export default config
