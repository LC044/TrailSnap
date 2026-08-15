const fs = require('fs');
const https = require('https');
const path = require('path');
const { execSync } = require('child_process');

const version = require('../package.json').version;

const platformMap = {
  win32: 'windows',
  darwin: 'macos',
  linux: 'linux'
};

const archMap = {
  x64: 'x64',
  arm64: 'arm64'
};

const platform = platformMap[process.platform];
const arch = archMap[process.arch] || 'x64'; // Default to x64 if unknown

if (!platform) {
  console.error(`Unsupported platform: ${process.platform}`);
  process.exit(1);
}

const ext = platform === 'windows' ? '.exe' : '';
const binaryName = `trailsnap-cli-${platform}-${arch}${ext}`;
const downloadUrl = `https://github.com/LC044/TrailSnap/releases/download/v${version}/${binaryName}`;

const binDir = path.join(__dirname, '..', 'bin');
const binPath = path.join(binDir, `trailsnap${ext}`);

if (!fs.existsSync(binDir)) {
  fs.mkdirSync(binDir, { recursive: true });
}

function downloadBinary(url, dest) {
  return new Promise((resolve, reject) => {
    console.log(`Downloading ${binaryName} from ${url}...`);
    
    const request = https.get(url, (response) => {
      if (response.statusCode === 301 || response.statusCode === 302) {
        // Handle redirect
        console.log(`Redirected to ${response.headers.location}`);
        return downloadBinary(response.headers.location, dest).then(resolve).catch(reject);
      }
      
      if (response.statusCode !== 200) {
        reject(new Error(`Failed to download binary: HTTP ${response.statusCode} - ${response.statusMessage}`));
        return;
      }
      
      const file = fs.createWriteStream(dest);
      response.pipe(file);
      
      file.on('finish', () => {
        file.close();
        if (platform !== 'windows') {
          fs.chmodSync(dest, 0o755); // Make it executable
        }
        console.log('Download completed successfully.');
        resolve();
      });
    });
    
    request.on('error', (err) => {
      fs.unlink(dest, () => {});
      reject(err);
    });
  });
}

downloadBinary(downloadUrl, binPath).catch(err => {
  console.error('Error installing trailsnap:', err.message);
  process.exit(1);
});
