package cn.trailsnap.app;

import com.getcapacitor.BridgeActivity;
import com.getcapacitor.PluginHandle;
import android.content.Intent;
import android.os.Bundle;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(GalleryBackupPlugin.class);
        super.onCreate(savedInstanceState);
        handleGalleryBackupAction(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleGalleryBackupAction(intent);
    }

    private void handleGalleryBackupAction(Intent intent) {
        if (intent == null || bridge == null) return;
        String action = intent.getStringExtra(GalleryBackupPlugin.EXTRA_NOTIFICATION_ACTION);
        if (action == null) return;
        PluginHandle handle = bridge.getPlugin("GalleryBackup");
        if (handle != null && handle.getInstance() instanceof GalleryBackupPlugin) {
            ((GalleryBackupPlugin) handle.getInstance()).handleNotificationAction(action);
        }
        intent.removeExtra(GalleryBackupPlugin.EXTRA_NOTIFICATION_ACTION);
    }
}
