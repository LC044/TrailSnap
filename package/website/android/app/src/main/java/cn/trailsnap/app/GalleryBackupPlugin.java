package cn.trailsnap.app;

import android.Manifest;
import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
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

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

@CapacitorPlugin(
    name = "GalleryBackup",
    permissions = {
        @Permission(alias = "legacyStorage", strings = { Manifest.permission.READ_EXTERNAL_STORAGE }),
        @Permission(alias = "images", strings = { Manifest.permission.READ_MEDIA_IMAGES }),
        @Permission(alias = "videos", strings = { Manifest.permission.READ_MEDIA_VIDEO }),
        @Permission(alias = "selectedMedia", strings = { Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED })
    }
)
public class GalleryBackupPlugin extends Plugin {
    private static final int MAX_PAGE_SIZE = 100;

    @PluginMethod
    public void requestGalleryPermission(PluginCall call) {
        if (galleryPermissionGranted()) {
            permissionResult(call);
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                requestPermissionForAliases(new String[] { "images", "videos", "selectedMedia" }, call, "galleryPermissionCallback");
            } else {
                requestPermissionForAliases(new String[] { "images", "videos" }, call, "galleryPermissionCallback");
            }
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
        result.put("granted", galleryPermissionGranted());
        call.resolve(result);
    }

    private boolean galleryPermissionGranted() {
        String alias = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU ? "images" : "legacyStorage";
        return getPermissionState(alias) == PermissionState.GRANTED ||
            (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE && getPermissionState("selectedMedia") == PermissionState.GRANTED);
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

        try {
            List<Asset> images = query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, "image", imageModified, imageId, limit);
            boolean canReadVideos = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || getPermissionState("videos") == PermissionState.GRANTED;
            List<Asset> videos = includeVideos && canReadVideos
                ? query(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, "video", videoModified, videoId, limit)
                : new ArrayList<>();
            List<Asset> merged = new ArrayList<>();
            merged.addAll(images);
            merged.addAll(videos);
            merged.sort(Comparator.comparingLong((Asset asset) -> asset.modifiedMs)
                .thenComparing(asset -> asset.kind)
                .thenComparingLong(asset -> asset.id));
            if (merged.size() > limit) merged = new ArrayList<>(merged.subList(0, limit));

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

    private List<Asset> query(Uri collection, String kind, long afterModifiedMs, long afterId, int limit) {
        List<Asset> result = new ArrayList<>();
        String[] projection = {
            MediaStore.MediaColumns._ID,
            MediaStore.MediaColumns.DISPLAY_NAME,
            MediaStore.MediaColumns.MIME_TYPE,
            MediaStore.MediaColumns.SIZE,
            MediaStore.MediaColumns.DATE_MODIFIED
        };
        long modifiedSeconds = afterModifiedMs / 1000L;
        String selection = "(" + MediaStore.MediaColumns.DATE_MODIFIED + " > ?) OR (" +
            MediaStore.MediaColumns.DATE_MODIFIED + " = ? AND " + MediaStore.MediaColumns._ID + " > ?)";
        String[] args = { String.valueOf(modifiedSeconds), String.valueOf(modifiedSeconds), String.valueOf(afterId) };
        String order = MediaStore.MediaColumns.DATE_MODIFIED + " ASC, " + MediaStore.MediaColumns._ID + " ASC LIMIT " + limit;
        ContentResolver resolver = getContext().getContentResolver();
        Cursor queried;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Bundle queryArgs = new Bundle();
            queryArgs.putString(ContentResolver.QUERY_ARG_SQL_SELECTION, selection);
            queryArgs.putStringArray(ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS, args);
            queryArgs.putStringArray(ContentResolver.QUERY_ARG_SORT_COLUMNS, new String[] {
                MediaStore.MediaColumns.DATE_MODIFIED,
                MediaStore.MediaColumns._ID
            });
            queryArgs.putInt(ContentResolver.QUERY_ARG_SORT_DIRECTION, ContentResolver.QUERY_SORT_DIRECTION_ASCENDING);
            queryArgs.putInt(ContentResolver.QUERY_ARG_LIMIT, limit);
            queried = resolver.query(collection, projection, queryArgs, null);
        } else {
            queried = resolver.query(collection, projection, selection, args, order);
        }
        try (Cursor cursor = queried) {
            if (cursor == null) return result;
            int idColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns._ID);
            int nameColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME);
            int mimeColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.MIME_TYPE);
            int sizeColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE);
            int modifiedColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_MODIFIED);
            while (cursor.moveToNext()) {
                long id = cursor.getLong(idColumn);
                result.add(new Asset(
                    id,
                    kind,
                    cursor.getString(nameColumn),
                    cursor.getString(mimeColumn),
                    cursor.getLong(sizeColumn),
                    cursor.getLong(modifiedColumn) * 1000L,
                    Uri.withAppendedPath(collection, String.valueOf(id))
                ));
            }
        }
        return result;
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
        try (InputStream input = getContext().getContentResolver().openInputStream(Uri.parse(uriValue));
             FileOutputStream stream = new FileOutputStream(output)) {
            if (input == null) throw new IllegalStateException("无法打开图库文件");
            byte[] buffer = new byte[256 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) stream.write(buffer, 0, read);
            JSObject result = new JSObject();
            result.put("path", output.getAbsolutePath());
            call.resolve(result);
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
        final long id, size, modifiedMs;
        final String kind, name, mimeType;
        final Uri uri;

        Asset(long id, String kind, String name, String mimeType, long size, long modifiedMs, Uri uri) {
            this.id = id;
            this.kind = kind;
            this.name = name == null ? kind + "-" + id : name;
            this.mimeType = mimeType == null ? ("video".equals(kind) ? "video/mp4" : "image/jpeg") : mimeType;
            this.size = size;
            this.modifiedMs = modifiedMs;
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
            value.put("uri", uri.toString());
            value.put("backupKey", "android:" + kind + ":" + id + ":" + modifiedMs + ":" + size);
            return value;
        }
    }
}
