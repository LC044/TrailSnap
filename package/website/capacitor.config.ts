import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'cn.trailsnap.app',
  appName: '行影集',
  webDir: 'dist',
  backgroundColor: '#f8fafc',
  loggingBehavior: 'debug',
  android: {
    // Self-hosted instances are often exposed on a LAN over HTTP.
    allowMixedContent: true,
  },
}

export default config
