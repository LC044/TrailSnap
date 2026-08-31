package cn.trailsnap.app;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.ParcelFileDescriptor;
import android.provider.MediaStore;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.PermissionState;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@CapacitorPlugin(
    name = "GalleryBackup",
    permissions = {
        @Permission(alias = "legacyStorage", strings = { Manifest.permission.READ_EXTERNAL_STORAGE }),
        @Permission(alias = "images", strings = { Manifest.permission.READ_MEDIA_IMAGES }),
        @Permission(alias = "videos", strings = { Manifest.permission.READ_MEDIA_VIDEO }),
        @Permission(alias = "selectedMedia", strings = { Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED }),
        @Permission(alias = "mediaLocation", strings = { Manifest.permission.ACCESS_MEDIA_LOCATION }),
        @Permission(alias = "notifications", strings = { Manifest.permission.POST_NOTIFICATIONS })
    }
)
public class GalleryBackupPlugin extends Plugin {
    private static final int MAX_PAGE_SIZE = 100;
    private static final String NOTIFICATION_CHANNEL_ID = "gallery_backup";
    private static final int NOTIFICATION_ID = 4701;
    private static final String PREFS_NAME = "gallery_backup_native";
    private static final String PREF_PENDING_ACTION = "pending_action";
    public static final String EXTRA_NOTIFICATION_ACTION = "gallery_backup_action";

    @PluginMethod
    public void requestGalleryPermission(PluginCall call) {
        if (galleryPermissionGranted() && originalMediaPermissionGranted()) {
            permissionResult(call);
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                requestPermissionForAliases(new String[] { "images", "videos", "selectedMedia", "mediaLocation" }, call, "galleryPermissionCallback");
            } else {
                requestPermissionForAliases(new String[] { "images", "videos", "mediaLocation" }, call, "galleryPermissionCallback");
            }
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            requestPermissionForAliases(new String[] { "legacyStorage", "mediaLocation" }, call, "galleryPermissionCallback");
        } else {
            requestPermissionForAlias("legacyStorage", call, "galleryPermissionCallback");
        }
    }

    @PermissionCallback
    private void galleryPermissionCallback(PluginCall call) {
        permissionResult(call);
    }

    private void permissionResult(PluginCall call) {
        JSObject result = new JSObject();
        result.put("granted", galleryPermissionGranted() && originalMediaPermissionGranted());
        result.put("galleryGranted", galleryPermissionGranted());
        result.put("originalGranted", originalMediaPermissionGranted());
        call.resolve(result);
    }

    private boolean galleryPermissionGranted() {
        String alias = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU ? "images" : "legacyStorage";
        return getPermissionState(alias) == PermissionState.GRANTED ||
            (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE && getPermissionState("selectedMedia") == PermissionState.GRANTED);
    }

    private boolean originalMediaPermissionGranted() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            getPermissionState("mediaLocation") == PermissionState.GRANTED;
    }

    @PluginMethod
    public void requestNotificationPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || getPermissionState("notifications") == PermissionState.GRANTED) {
            notificationPermissionResult(call);
            return;
        }
        requestPermissionForAlias("notifications", call, "notificationPermissionCallback");
    }

    @PermissionCallback
    private void notificationPermissionCallback(PluginCall call) {
        notificationPermissionResult(call);
    }

    private void notificationPermissionResult(PluginCall call) {
        JSObject result = new JSObject();
        result.put("granted", Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            getPermissionState("notifications") == PermissionState.GRANTED);
        call.resolve(result);
    }

    @PluginMethod
    public void listAssets(PluginCall call) {
        if (!galleryPermissionGranted()) {
            call.reject("图库权限未授权", "PERMISSION_DENIED");
            return;
        }
        int limit = Math.min(Math.max(call.getInt("limit", 40), 1), MAX_PAGE_SIZE);
        boolean includeVideos = call.getBoolean("includeVideos", true);
        long imageModified = call.getLong("imageModified", 0L);
        long imageId = call.getLong("imageId", 0L);
        long videoModified = call.getLong("videoModified", 0L);
        long videoId = call.getLong("videoId", 0L);
        List<String> sourcePaths = readSourcePaths(call);

        try {
            List<Asset> images = query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, "image", imageModified, imageId, limit, sourcePaths);
            boolean canReadVideos = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || getPermissionState("videos") == PermissionState.GRANTED;
            List<Asset> videos = includeVideos && canReadVideos
                ? query(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, "video", videoModified, videoId, limit, sourcePaths)
                : new ArrayList<>();
            List<Asset> merged = new ArrayList<>();
            merged.addAll(images);
            merged.addAll(videos);
            merged.sort(Comparator.comparingLong((Asset asset) -> asset.modifiedMs)
                .thenComparing(asset -> asset.kind)
                .thenComparingLong(asset -> asset.id));
            if (merged.size() > limit) merged = new ArrayList<>(merged.subList(0, limit));
            for (Asset asset : merged) asset.liveCompanion = findLiveCompanion(asset);

            JSArray items = new JSArray();
            long nextImageModified = imageModified, nextImageId = imageId;
            long nextVideoModified = videoModified, nextVideoId = videoId;
            for (Asset asset : merged) {
                items.put(asset.toJson());
                if ("image".equals(asset.kind)) {
                    nextImageModified = asset.modifiedMs;
                    nextImageId = asset.id;
                } else {
                    nextVideoModified = asset.modifiedMs;
                    nextVideoId = asset.id;
                }
            }
            JSObject result = new JSObject();
            result.put("assets", items);
            result.put("imageModified", nextImageModified);
            result.put("imageId", nextImageId);
            result.put("videoModified", nextVideoModified);
            result.put("videoId", nextVideoId);
            result.put("hasMore", merged.size() == limit);
            call.resolve(result);
        } catch (Exception error) {
            call.reject("读取图库失败", error);
        }
    }

    @PluginMethod
    public void countAssets(PluginCall call) {
        if (!galleryPermissionGranted()) {
            call.reject("图库权限未授权", "PERMISSION_DENIED");
            return;
        }
        boolean includeVideos = call.getBoolean("includeVideos", true);
        long imageModified = call.getLong("imageModified", 0L);
        long imageId = call.getLong("imageId", 0L);
        long videoModified = call.getLong("videoModified", 0L);
        long videoId = call.getLong("videoId", 0L);
        List<String> sourcePaths = readSourcePaths(call);
        try {
            long[] imageStats = count(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, imageModified, imageId, sourcePaths);
            boolean canReadVideos = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || getPermissionState("videos") == PermissionState.GRANTED;
            long[] videoStats = includeVideos && canReadVideos
                ? count(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, videoModified, videoId, sourcePaths)
                : new long[] { 0L, 0L };
            JSObject result = new JSObject();
            result.put("count", imageStats[0] + videoStats[0]);
            result.put("bytes", imageStats[1] + videoStats[1]);
            call.resolve(result);
        } catch (Exception error) {
            call.reject("统计图库失败", error);
        }
    }

    private long[] count(Uri collection, long afterModifiedMs, long afterId, List<String> sourcePaths) {
        SelectionSpec selection = buildSelection(afterModifiedMs, afterId, sourcePaths);
        long count = 0L, bytes = 0L;
        try (Cursor cursor = getContext().getContentResolver().query(
            collection,
            new String[] { MediaStore.MediaColumns._ID, MediaStore.MediaColumns.SIZE },
            selection.where,
            selection.args,
            null
        )) {
            if (cursor == null) return new long[] { 0L, 0L };
            int sizeColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE);
            while (cursor.moveToNext()) {
                count++;
                bytes += Math.max(0L, cursor.getLong(sizeColumn));
            }
        }
        return new long[] { count, bytes };
    }

    @PluginMethod
    public void listSourceFolders(PluginCall call) {
        if (!galleryPermissionGranted()) {
            call.reject("图库权限未授权", "PERMISSION_DENIED");
            return;
        }
        boolean includeVideos = call.getBoolean("includeVideos", true);
        try {
            Map<String, SourceFolder> folders = new LinkedHashMap<>();
            collectSourceFolders(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, folders);
            boolean canReadVideos = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || getPermissionState("videos") == PermissionState.GRANTED;
            if (includeVideos && canReadVideos) collectSourceFolders(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, folders);
            List<SourceFolder> sorted = new ArrayList<>(folders.values());
            sorted.sort(Comparator.comparing(folder -> folder.name.toLowerCase()));
            JSArray values = new JSArray();
            for (SourceFolder folder : sorted) values.put(folder.toJson());
            JSObject result = new JSObject();
            result.put("folders", values);
            call.resolve(result);
        } catch (Exception error) {
            call.reject("读取本地相册目录失败", error);
        }
    }

    private void collectSourceFolders(Uri collection, Map<String, SourceFolder> folders) {
        boolean modern = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q;
        String pathColumn = modern ? MediaStore.MediaColumns.RELATIVE_PATH : MediaStore.MediaColumns.DATA;
        String[] projection = { pathColumn, MediaStore.Images.ImageColumns.BUCKET_DISPLAY_NAME };
        try (Cursor cursor = getContext().getContentResolver().query(collection, projection, null, null, null)) {
            if (cursor == null) return;
            int pathIndex = cursor.getColumnIndexOrThrow(pathColumn);
            int nameIndex = cursor.getColumnIndex(MediaStore.Images.ImageColumns.BUCKET_DISPLAY_NAME);
            while (cursor.moveToNext()) {
                String rawPath = cursor.getString(pathIndex);
                if (rawPath == null || rawPath.isEmpty()) continue;
                String path = modern ? normalizeRelativePath(rawPath) : new File(rawPath).getParent();
                if (path == null || path.isEmpty()) continue;
                String displayName = nameIndex >= 0 ? cursor.getString(nameIndex) : null;
                SourceFolder folder = folders.get(path);
                if (folder == null) {
                    folder = new SourceFolder(path, displayName == null || displayName.isEmpty() ? lastPathSegment(path) : displayName);
                    folders.put(path, folder);
                }
                folder.count++;
            }
        }
    }

    @PluginMethod
    public void updateBackupNotification(PluginCall call) {
        createNotificationChannel();
        String state = call.getString("state", "running");
        int processed = Math.max(0, call.getInt("processed", 0));
        int total = Math.max(0, call.getInt("total", 0));
        int percent = Math.min(100, Math.max(0, call.getInt("percent", 0)));
        String speed = call.getString("speed", "");
        String currentFile = call.getString("currentFile", "");

        boolean paused = "paused".equals(state);
        boolean completed = "completed".equals(state);
        boolean error = "error".equals(state);
        String title = completed ? "手机备份完成" : error ? "手机备份已暂停" : paused ? "手机备份已暂停" : "正在备份手机图库";
        String summary;
        if (completed) {
            summary = "已处理 " + processed + " 项";
        } else if (error) {
            summary = currentFile.isEmpty() ? "点击 APP 查看详情" : currentFile;
        } else {
            summary = processed + " / " + total + (speed.isEmpty() ? "" : " · " + speed);
        }

        Intent contentIntent = new Intent(getContext(), MainActivity.class);
        contentIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent contentPendingIntent = PendingIntent.getActivity(
            getContext(), 4700, contentIntent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        NotificationCompat.Builder builder = new NotificationCompat.Builder(getContext(), NOTIFICATION_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle(title)
            .setContentText(summary)
            .setSubText(currentFile.isEmpty() || error ? null : currentFile)
            .setOnlyAlertOnce(true)
            .setOngoing(!completed && !error)
            .setAutoCancel(completed || error)
            .setContentIntent(contentPendingIntent)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS);

        if (!completed && !error && total > 0) builder.setProgress(100, percent, false);
        if (!completed && !error) {
            String action = paused ? "resume" : "pause";
            String label = paused ? "继续" : "暂停";
            Intent actionIntent = new Intent(getContext(), MainActivity.class);
            actionIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            actionIntent.putExtra(EXTRA_NOTIFICATION_ACTION, action);
            PendingIntent actionPendingIntent = PendingIntent.getActivity(
                getContext(), paused ? 4703 : 4702, actionIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            );
            builder.addAction(0, label, actionPendingIntent);
        }

        try {
            NotificationManagerCompat.from(getContext()).notify(NOTIFICATION_ID, builder.build());
        } catch (SecurityException ignored) {
            // Backup must continue even when the user declines notifications.
        }
        call.resolve();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager manager = (NotificationManager) getContext().getSystemService(Context.NOTIFICATION_SERVICE);
        NotificationChannel channel = new NotificationChannel(
            NOTIFICATION_CHANNEL_ID, "手机图库备份", NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("显示手机图库备份进度和上传速度");
        manager.createNotificationChannel(channel);
    }

    @PluginMethod
    public void cancelBackupNotification(PluginCall call) {
        NotificationManagerCompat.from(getContext()).cancel(NOTIFICATION_ID);
        call.resolve();
    }

    public void handleNotificationAction(String action) {
        if (!"pause".equals(action) && !"resume".equals(action)) return;
        getContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putString(PREF_PENDING_ACTION, action).apply();
        JSObject data = new JSObject();
        data.put("action", action);
        notifyListeners("notificationAction", data, true);
    }

    @PluginMethod
    public void consumeNotificationAction(PluginCall call) {
        SharedPreferences preferences = getContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String action = preferences.getString(PREF_PENDING_ACTION, "");
        preferences.edit().remove(PREF_PENDING_ACTION).apply();
        JSObject result = new JSObject();
        result.put("action", action);
        call.resolve(result);
    }

    private List<Asset> query(Uri collection, String kind, long afterModifiedMs, long afterId, int limit, List<String> sourcePaths) {
        List<Asset> result = new ArrayList<>();
        boolean modern = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q;
        String pathColumn = modern ? MediaStore.MediaColumns.RELATIVE_PATH : MediaStore.MediaColumns.DATA;
        String takenColumnName = "video".equals(kind)
            ? MediaStore.Video.VideoColumns.DATE_TAKEN
            : MediaStore.Images.ImageColumns.DATE_TAKEN;
        String[] projection = {
            MediaStore.MediaColumns._ID, MediaStore.MediaColumns.DISPLAY_NAME, MediaStore.MediaColumns.MIME_TYPE,
            MediaStore.MediaColumns.SIZE, MediaStore.MediaColumns.DATE_MODIFIED, takenColumnName,
            pathColumn
        };
        SelectionSpec selection = buildSelection(afterModifiedMs, afterId, sourcePaths);
        String order = MediaStore.MediaColumns.DATE_MODIFIED + " ASC, " + MediaStore.MediaColumns._ID + " ASC LIMIT " + limit;
        ContentResolver resolver = getContext().getContentResolver();
        Cursor queried;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Bundle queryArgs = new Bundle();
            queryArgs.putString(ContentResolver.QUERY_ARG_SQL_SELECTION, selection.where);
            queryArgs.putStringArray(ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS, selection.args);
            queryArgs.putStringArray(ContentResolver.QUERY_ARG_SORT_COLUMNS, new String[] {
                MediaStore.MediaColumns.DATE_MODIFIED,
                MediaStore.MediaColumns._ID
            });
            queryArgs.putInt(ContentResolver.QUERY_ARG_SORT_DIRECTION, ContentResolver.QUERY_SORT_DIRECTION_ASCENDING);
            queryArgs.putInt(ContentResolver.QUERY_ARG_LIMIT, limit);
            queried = resolver.query(collection, projection, queryArgs, null);
        } else {
            queried = resolver.query(collection, projection, selection.where, selection.args, order);
        }
        try (Cursor cursor = queried) {
            if (cursor == null) return result;
            int idColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns._ID);
            int nameColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME);
            int mimeColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.MIME_TYPE);
            int sizeColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE);
            int modifiedColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_MODIFIED);
            int takenColumn = cursor.getColumnIndex(takenColumnName);
            int pathIndex = cursor.getColumnIndexOrThrow(pathColumn);
            while (cursor.moveToNext()) {
                long id = cursor.getLong(idColumn);
                String rawPath = cursor.getString(pathIndex);
                String relativePath = modern
                    ? normalizeRelativePath(rawPath)
                    : normalizeLegacyAssetPath(rawPath);
                String mediaDirectory = modern ? normalizeRelativePath(rawPath) : new File(rawPath).getParent();
                result.add(new Asset(
                    id,
                    kind,
                    cursor.getString(nameColumn),
                    cursor.getString(mimeColumn),
                    cursor.getLong(sizeColumn),
                    cursor.getLong(modifiedColumn) * 1000L,
                    takenColumn >= 0 ? cursor.getLong(takenColumn) : 0L,
                    relativePath,
                    mediaDirectory,
                    Uri.withAppendedPath(collection, String.valueOf(id))
                ));
            }
        }
        return result;
    }

    private List<String> readSourcePaths(PluginCall call) {
        List<String> result = new ArrayList<>();
        JSArray values = call.getArray("sourcePaths", new JSArray());
        for (int index = 0; index < values.length(); index++) {
            String value = values.optString(index, "");
            if (!value.isEmpty()) result.add(Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q ? normalizeRelativePath(value) : value);
        }
        return result;
    }

    private SelectionSpec buildSelection(long afterModifiedMs, long afterId, List<String> sourcePaths) {
        long modifiedSeconds = afterModifiedMs / 1000L;
        StringBuilder where = new StringBuilder("((" + MediaStore.MediaColumns.DATE_MODIFIED + " > ?) OR (" +
            MediaStore.MediaColumns.DATE_MODIFIED + " = ? AND " + MediaStore.MediaColumns._ID + " > ?))");
        List<String> args = new ArrayList<>();
        args.add(String.valueOf(modifiedSeconds));
        args.add(String.valueOf(modifiedSeconds));
        args.add(String.valueOf(afterId));
        if (!sourcePaths.isEmpty()) {
            where.append(" AND (");
            boolean modern = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q;
            for (int index = 0; index < sourcePaths.size(); index++) {
                if (index > 0) where.append(" OR ");
                if (modern) {
                    where.append(MediaStore.MediaColumns.RELATIVE_PATH).append(" = ?");
                    args.add(normalizeRelativePath(sourcePaths.get(index)));
                } else {
                    where.append(MediaStore.MediaColumns.DATA).append(" LIKE ?");
                    args.add(sourcePaths.get(index) + File.separator + "%");
                }
            }
            where.append(")");
        }
        return new SelectionSpec(where.toString(), args.toArray(new String[0]));
    }

    private String normalizeRelativePath(String value) {
        if (value == null) return "";
        String normalized = value.replace('\\', '/').replaceAll("^/+", "");
        return normalized.isEmpty() || normalized.endsWith("/") ? normalized : normalized + "/";
    }

    private String normalizeLegacyAssetPath(String filePath) {
        if (filePath == null) return "";
        String parent = new File(filePath).getParent();
        if (parent == null) return "";
        String storageRoot = Environment.getExternalStorageDirectory().getAbsolutePath();
        return parent.startsWith(storageRoot + File.separator)
            ? parent.substring(storageRoot.length() + 1)
            : lastPathSegment(parent);
    }

    private String lastPathSegment(String path) {
        String normalized = path.replace('\\', '/').replaceAll("/+$", "");
        int slash = normalized.lastIndexOf('/');
        return slash >= 0 ? normalized.substring(slash + 1) : normalized;
    }

    private Asset findLiveCompanion(Asset asset) {
        String lowerName = asset.name.toLowerCase(Locale.ROOT);
        int dot = lowerName.lastIndexOf('.');
        if (dot <= 0) return null;
        String stem = lowerName.substring(0, dot);
        List<String> names = new ArrayList<>();
        Uri collection;
        String kind;
        if ("image".equals(asset.kind)) {
            if (lowerName.endsWith(".heic") || lowerName.endsWith(".heif")) {
                names.add(stem + ".mov");
            } else if (lowerName.endsWith(".jpg") || lowerName.endsWith(".jpeg")) {
                names.add(stem + ".mp4");
                names.add(stem + ".mov");
            } else {
                return null;
            }
            collection = MediaStore.Video.Media.EXTERNAL_CONTENT_URI;
            kind = "video";
        } else {
            if (lowerName.endsWith(".mp4")) {
                names.add(stem + ".jpg");
                names.add(stem + ".jpeg");
            } else if (lowerName.endsWith(".mov")) {
                names.add(stem + ".heic");
                names.add(stem + ".heif");
                names.add(stem + ".jpg");
                names.add(stem + ".jpeg");
            } else {
                return null;
            }
            collection = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;
            kind = "image";
        }
        return findAssetByNames(collection, kind, names, asset.mediaDirectory);
    }

    private Asset findAssetByNames(Uri collection, String kind, List<String> names, String mediaDirectory) {
        if (mediaDirectory == null || mediaDirectory.isEmpty() || names.isEmpty()) return null;
        boolean modern = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q;
        String pathColumn = modern ? MediaStore.MediaColumns.RELATIVE_PATH : MediaStore.MediaColumns.DATA;
        String takenColumnName = "video".equals(kind)
            ? MediaStore.Video.VideoColumns.DATE_TAKEN
            : MediaStore.Images.ImageColumns.DATE_TAKEN;
        String[] projection = {
            MediaStore.MediaColumns._ID, MediaStore.MediaColumns.DISPLAY_NAME, MediaStore.MediaColumns.MIME_TYPE,
            MediaStore.MediaColumns.SIZE, MediaStore.MediaColumns.DATE_MODIFIED, takenColumnName, pathColumn
        };
        StringBuilder selection = new StringBuilder("LOWER(" + MediaStore.MediaColumns.DISPLAY_NAME + ") IN (");
        List<String> args = new ArrayList<>();
        for (int index = 0; index < names.size(); index++) {
            if (index > 0) selection.append(',');
            selection.append('?');
            args.add(names.get(index));
        }
        if (modern) {
            selection.append(") AND ").append(MediaStore.MediaColumns.RELATIVE_PATH).append(" = ?");
            args.add(normalizeRelativePath(mediaDirectory));
        } else {
            selection.append(") AND ").append(MediaStore.MediaColumns.DATA).append(" LIKE ?");
            args.add(mediaDirectory + File.separator + "%");
        }
        try (Cursor cursor = getContext().getContentResolver().query(
            collection, projection, selection.toString(), args.toArray(new String[0]), null
        )) {
            if (cursor == null || !cursor.moveToFirst()) return null;
            long id = cursor.getLong(cursor.getColumnIndexOrThrow(MediaStore.MediaColumns._ID));
            String rawPath = cursor.getString(cursor.getColumnIndexOrThrow(pathColumn));
            String relativePath = modern ? normalizeRelativePath(rawPath) : normalizeLegacyAssetPath(rawPath);
            String directory = modern ? normalizeRelativePath(rawPath) : new File(rawPath).getParent();
            int takenIndex = cursor.getColumnIndex(takenColumnName);
            return new Asset(
                id, kind,
                cursor.getString(cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME)),
                cursor.getString(cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.MIME_TYPE)),
                cursor.getLong(cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE)),
                cursor.getLong(cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_MODIFIED)) * 1000L,
                takenIndex >= 0 ? cursor.getLong(takenIndex) : 0L,
                relativePath, directory, Uri.withAppendedPath(collection, String.valueOf(id))
            );
        } catch (SecurityException ignored) {
            // The user may grant image access but deny video access. In that
            // case the still image remains a normal backup item.
            return null;
        }
    }

    @PluginMethod
    public void exportAsset(PluginCall call) {
        String uriValue = call.getString("uri");
        String requestedName = call.getString("fileName", "asset");
        if (uriValue == null) {
            call.reject("缺少图库资产 URI");
            return;
        }
        String safeName = requestedName.replaceAll("[^a-zA-Z0-9._-]", "_");
        File directory = new File(getContext().getCacheDir(), "gallery-backup");
        if (!directory.exists() && !directory.mkdirs()) {
            call.reject("无法创建临时目录");
            return;
        }
        File output = new File(directory, System.nanoTime() + "-" + safeName);
        Uri sourceUri = Uri.parse(uriValue);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            if (!originalMediaPermissionGranted()) {
                call.reject("未授予照片位置权限，无法读取包含 GPS 的原图", "ORIGINAL_MEDIA_PERMISSION_REQUIRED");
                return;
            }
            sourceUri = MediaStore.setRequireOriginal(sourceUri);
        }
        try (ParcelFileDescriptor descriptor = getContext().getContentResolver().openFileDescriptor(sourceUri, "r")) {
            if (descriptor == null) throw new IllegalStateException("无法打开图库原始文件");
            try (InputStream input = new FileInputStream(descriptor.getFileDescriptor());
                 FileOutputStream stream = new FileOutputStream(output)) {
                byte[] buffer = new byte[256 * 1024];
                int read;
                while ((read = input.read(buffer)) != -1) stream.write(buffer, 0, read);
            }
            JSObject result = new JSObject();
            result.put("path", output.getAbsolutePath());
            call.resolve(result);
        } catch (UnsupportedOperationException | SecurityException error) {
            output.delete();
            call.reject("系统无法提供未经裁剪元数据的原始媒体文件", "ORIGINAL_MEDIA_UNAVAILABLE", error);
        } catch (Exception error) {
            output.delete();
            call.reject("导出图库文件失败", error);
        }
    }

    @PluginMethod
    public void releaseAsset(PluginCall call) {
        String path = call.getString("path");
        try {
            File root = new File(getContext().getCacheDir(), "gallery-backup").getCanonicalFile();
            File target = new File(path == null ? "" : path).getCanonicalFile();
            if (target.getPath().startsWith(root.getPath() + File.separator)) target.delete();
            call.resolve();
        } catch (Exception error) {
            call.reject("清理临时文件失败", error);
        }
    }

    @PluginMethod
    public void getNetworkStatus(PluginCall call) {
        ConnectivityManager manager = (ConnectivityManager) getContext().getSystemService(Context.CONNECTIVITY_SERVICE);
        Network network = manager.getActiveNetwork();
        NetworkCapabilities capabilities = network == null ? null : manager.getNetworkCapabilities(network);
        JSObject result = new JSObject();
        result.put("connected", capabilities != null);
        result.put("wifi", capabilities != null && capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI));
        result.put("unmetered", capabilities != null && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED));
        call.resolve(result);
    }

    private static class Asset {
        final long id, size, modifiedMs, takenMs;
        final String kind, name, mimeType, relativePath, mediaDirectory;
        final Uri uri;
        Asset liveCompanion;

        Asset(long id, String kind, String name, String mimeType, long size, long modifiedMs,
              long takenMs, String relativePath, String mediaDirectory, Uri uri) {
            this.id = id;
            this.kind = kind;
            this.name = name == null ? kind + "-" + id : name;
            this.mimeType = mimeType == null ? ("video".equals(kind) ? "video/mp4" : "image/jpeg") : mimeType;
            this.size = size;
            this.modifiedMs = modifiedMs;
            this.takenMs = takenMs;
            this.relativePath = relativePath == null ? "" : relativePath;
            this.mediaDirectory = mediaDirectory == null ? "" : mediaDirectory;
            this.uri = uri;
        }

        JSObject toJson() {
            JSObject value = new JSObject();
            value.put("id", id);
            value.put("kind", kind);
            value.put("name", name);
            value.put("mimeType", mimeType);
            value.put("size", size);
            value.put("modifiedMs", modifiedMs);
            value.put("takenMs", takenMs);
            value.put("relativePath", relativePath);
            value.put("uri", uri.toString());
            value.put("backupKey", "android:" + kind + ":" + id + ":" + modifiedMs + ":" + size);
            if (liveCompanion != null) value.put("liveCompanion", liveCompanion.toJson());
            return value;
        }
    }

    private static class SelectionSpec {
        final String where;
        final String[] args;

        SelectionSpec(String where, String[] args) {
            this.where = where;
            this.args = args;
        }
    }

    private static class SourceFolder {
        final String path, name;
        long count;

        SourceFolder(String path, String name) {
            this.path = path;
            this.name = name;
        }

        JSObject toJson() {
            JSObject value = new JSObject();
            value.put("path", path);
            value.put("name", name);
            value.put("count", count);
            return value;
        }
    }
}
