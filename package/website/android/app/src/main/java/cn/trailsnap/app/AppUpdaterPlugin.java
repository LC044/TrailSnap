package cn.trailsnap.app;

import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import androidx.core.content.FileProvider;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * App 自动更新的原生桥：读取已安装版本、后台下载 APK（带进度事件）、
 * 校验大小后唤起系统安装器。
 *
 * 设计取舍：
 * - 只做「下载 + 唤起系统安装界面」，不做静默安装。静默安装需要设备
 *   owner / 系统签名，自托管场景拿不到。
 * - APK 落到 {@code cacheDir/app-update}，通过已在 manifest 注册的
 *   FileProvider 以 content:// 授权给安装器，避免 Android 7+ 的
 *   FileUriExposedException。
 * - 下载在单线程 executor 上跑，进度通过 {@code downloadProgress} 事件回抛，
 *   由 WebView 侧节流展示；同一时刻只允许一个下载任务。
 */
@CapacitorPlugin(name = "AppUpdater")
public class AppUpdaterPlugin extends Plugin {
    private static final String DOWNLOAD_DIR = "app-update";
    private static final String EVENT_PROGRESS = "downloadProgress";
    private static final int BUFFER_SIZE = 128 * 1024;
    private static final int CONNECT_TIMEOUT_MS = 15000;
    private static final int READ_TIMEOUT_MS = 60000;
    private static final int MAX_REDIRECTS = 5;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final AtomicBoolean downloading = new AtomicBoolean(false);
    private volatile boolean cancelRequested = false;

    @PluginMethod
    public void getAppInfo(PluginCall call) {
        JSObject result = new JSObject();
        try {
            PackageManager manager = getContext().getPackageManager();
            PackageInfo info = manager.getPackageInfo(getContext().getPackageName(), 0);
            result.put("packageName", info.packageName);
            result.put("versionName", info.versionName == null ? "" : info.versionName);
            result.put("versionCode", Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                ? info.getLongVersionCode()
                : (long) info.versionCode);
            result.put("canRequestInstall", canRequestInstall());
            call.resolve(result);
        } catch (PackageManager.NameNotFoundException error) {
            call.reject("读取应用版本失败", error);
        }
    }

    /** Android 8+ 需要「安装未知应用」授权，否则唤起安装器会被系统直接拒绝。 */
    @PluginMethod
    public void openInstallPermissionSettings(PluginCall call) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || canRequestInstall()) {
            JSObject result = new JSObject();
            result.put("granted", true);
            call.resolve(result);
            return;
        }
        try {
            Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + getContext().getPackageName()));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(intent);
            JSObject result = new JSObject();
            result.put("granted", false);
            call.resolve(result);
        } catch (Exception error) {
            call.reject("无法打开安装权限设置页", error);
        }
    }

    @PluginMethod
    public void downloadApk(PluginCall call) {
        String url = call.getString("url");
        if (url == null || url.isEmpty()) {
            call.reject("缺少安装包下载地址", "INVALID_URL");
            return;
        }
        String version = sanitize(call.getString("version", "latest"));
        long expectedSize = call.getLong("size", 0L);
        if (!downloading.compareAndSet(false, true)) {
            call.reject("已有下载任务在进行中", "DOWNLOAD_IN_PROGRESS");
            return;
        }
        cancelRequested = false;
        call.setKeepAlive(true);
        executor.execute(() -> {
            File target = null;
            try {
                target = prepareTargetFile(version);
                long downloaded = download(url, target, expectedSize);
                if (cancelRequested) {
                    deleteQuietly(target);
                    call.reject("下载已取消", "DOWNLOAD_CANCELLED");
                    return;
                }
                if (expectedSize > 0 && downloaded != expectedSize) {
                    deleteQuietly(target);
                    call.reject("安装包大小与服务端不一致，可能下载不完整", "SIZE_MISMATCH");
                    return;
                }
                JSObject result = new JSObject();
                result.put("path", target.getAbsolutePath());
                result.put("size", downloaded);
                call.resolve(result);
            } catch (Exception error) {
                deleteQuietly(target);
                call.reject("下载安装包失败：" + error.getMessage(), "DOWNLOAD_FAILED", error);
            } finally {
                downloading.set(false);
                call.setKeepAlive(false);
            }
        });
    }

    @PluginMethod
    public void cancelDownload(PluginCall call) {
        cancelRequested = true;
        call.resolve();
    }

    @PluginMethod
    public void installApk(PluginCall call) {
        String path = call.getString("path");
        if (path == null || path.isEmpty()) {
            call.reject("缺少安装包路径", "INVALID_PATH");
            return;
        }
        File apk = new File(path);
        if (!apk.exists() || apk.length() <= 0) {
            call.reject("安装包不存在或已被清理", "APK_MISSING");
            return;
        }
        if (!canRequestInstall()) {
            call.reject("尚未授予「安装未知应用」权限", "INSTALL_PERMISSION_REQUIRED");
            return;
        }
        try {
            Uri uri = FileProvider.getUriForFile(
                getContext(), getContext().getPackageName() + ".fileprovider", apk
            );
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, "application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(intent);
            call.resolve();
        } catch (Exception error) {
            call.reject("唤起安装器失败", error);
        }
    }

    /** 清理历史下载，避免多次更新后缓存目录里堆积旧 APK。 */
    @PluginMethod
    public void clearDownloads(PluginCall call) {
        File directory = new File(getContext().getCacheDir(), DOWNLOAD_DIR);
        File[] files = directory.listFiles();
        if (files != null) {
            for (File file : files) deleteQuietly(file);
        }
        call.resolve();
    }

    private File prepareTargetFile(String version) throws Exception {
        File directory = new File(getContext().getCacheDir(), DOWNLOAD_DIR);
        if (!directory.exists() && !directory.mkdirs()) {
            throw new IllegalStateException("无法创建下载目录");
        }
        File[] stale = directory.listFiles();
        if (stale != null) {
            for (File file : stale) deleteQuietly(file);
        }
        return new File(directory, "TrailSnap-" + version + ".apk");
    }

    private long download(String url, File target, long expectedSize) throws Exception {
        HttpURLConnection connection = openWithRedirects(url);
        try {
            int status = connection.getResponseCode();
            if (status / 100 != 2) throw new IllegalStateException("HTTP " + status);
            long total = expectedSize > 0 ? expectedSize : Math.max(0, connection.getContentLengthLong());
            long downloaded = 0;
            long lastNotified = 0;
            notifyProgress(0, total);
            try (InputStream input = connection.getInputStream();
                 FileOutputStream output = new FileOutputStream(target)) {
                byte[] buffer = new byte[BUFFER_SIZE];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    if (cancelRequested) return downloaded;
                    output.write(buffer, 0, read);
                    downloaded += read;
                    // 每 512KB 上报一次，避免高频事件把 WebView 桥打满。
                    if (downloaded - lastNotified >= 512 * 1024) {
                        lastNotified = downloaded;
                        notifyProgress(downloaded, total);
                    }
                }
                output.flush();
            }
            notifyProgress(downloaded, total);
            return downloaded;
        } finally {
            connection.disconnect();
        }
    }

    /**
     * GitHub Release 的下载地址会 302 到对象存储，且
     * {@link HttpURLConnection} 不会自动跟随 http↔https 之间的跳转，这里手动处理。
     */
    private HttpURLConnection openWithRedirects(String url) throws Exception {
        String current = url;
        for (int hop = 0; hop <= MAX_REDIRECTS; hop++) {
            HttpURLConnection connection = (HttpURLConnection) new URL(current).openConnection();
            connection.setInstanceFollowRedirects(true);
            connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setRequestProperty("Accept", "application/octet-stream");
            int status = connection.getResponseCode();
            if (status == HttpURLConnection.HTTP_MOVED_PERM
                || status == HttpURLConnection.HTTP_MOVED_TEMP
                || status == HttpURLConnection.HTTP_SEE_OTHER
                || status == 307
                || status == 308) {
                String location = connection.getHeaderField("Location");
                connection.disconnect();
                if (location == null || location.isEmpty()) {
                    throw new IllegalStateException("重定向缺少 Location 头");
                }
                current = new URL(new URL(current), location).toString();
                continue;
            }
            return connection;
        }
        throw new IllegalStateException("下载地址重定向次数过多");
    }

    private void notifyProgress(long downloaded, long total) {
        JSObject data = new JSObject();
        data.put("downloaded", downloaded);
        data.put("total", total);
        data.put("percent", total > 0 ? (int) Math.min(100, downloaded * 100 / total) : 0);
        notifyListeners(EVENT_PROGRESS, data, true);
    }

    private boolean canRequestInstall() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return true;
        return getContext().getPackageManager().canRequestPackageInstalls();
    }

    private String sanitize(String value) {
        String safe = value == null ? "" : value.replaceAll("[^a-zA-Z0-9._-]", "_");
        return safe.isEmpty() ? "latest" : safe;
    }

    private void deleteQuietly(File file) {
        if (file == null) return;
        try {
            //noinspection ResultOfMethodCallIgnored
            file.delete();
        } catch (Exception ignored) {
            // 缓存目录里的残留文件由系统兜底清理。
        }
    }

    @Override
    protected void handleOnDestroy() {
        cancelRequested = true;
        executor.shutdownNow();
        super.handleOnDestroy();
    }
}
