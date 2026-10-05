package cn.trailsnap.app;

import android.content.Intent;
import android.os.Bundle;
import android.os.Build;
import android.view.View;
import android.view.WindowManager;
import android.webkit.WebView;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.PluginHandle;
import com.getcapacitor.WebViewListener;
import java.util.Locale;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(GalleryBackupPlugin.class);
        registerPlugin(LanDiscoveryPlugin.class);
        registerPlugin(AppUpdaterPlugin.class);
        registerPlugin(NativeNetworkPolicyPlugin.class);
        super.onCreate(savedInstanceState);
        bridge.setWebViewClient(new OfflineOnlyWebViewClient(bridge, this));
        configureEdgeToEdge();
        handleGalleryBackupAction(getIntent());
    }

    private void configureEdgeToEdge() {
        WindowCompat.enableEdgeToEdge(getWindow());
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            WindowManager.LayoutParams attributes = getWindow().getAttributes();
            attributes.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            getWindow().setAttributes(attributes);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            getWindow().setStatusBarContrastEnforced(false);
            getWindow().setNavigationBarContrastEnforced(false);
        }

        View container = (View) bridge.getWebView().getParent();
        ViewCompat.setOnApplyWindowInsetsListener(container, (view, insets) -> {
            // Keep the WebView behind system bars. Resize only for the keyboard.
            boolean keyboardVisible = insets.isVisible(WindowInsetsCompat.Type.ime());
            Insets keyboard = insets.getInsets(WindowInsetsCompat.Type.ime());
            view.setPadding(0, 0, 0, keyboardVisible ? keyboard.bottom : 0);
            publishSafeArea(insets);
            // CSS owns system-bar spacing; prevent WebView from applying it again.
            return new WindowInsetsCompat.Builder(insets)
                .setInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout(), Insets.NONE)
                .setInsets(WindowInsetsCompat.Type.ime(), Insets.NONE)
                .build();
        });
        bridge.addWebViewListener(new WebViewListener() {
            @Override
            public void onPageCommitVisible(WebView view, String url) {
                ViewCompat.requestApplyInsets(container);
            }

            @Override
            public void onPageLoaded(WebView view) {
                // Republish after reload even when the native insets did not change.
                ViewCompat.requestApplyInsets(container);
            }
        });
        ViewCompat.requestApplyInsets(container);
    }

    private void publishSafeArea(WindowInsetsCompat insets) {
        Insets safeArea = insets.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
        float density = getResources().getDisplayMetrics().density;
        int bottom = insets.isVisible(WindowInsetsCompat.Type.ime()) ? 0 : safeArea.bottom;
        String script = String.format(Locale.US,
            "(function(){if(!document.documentElement)return;var s=document.documentElement.style;"
                + "s.setProperty('--safe-area-inset-top','%.2fpx');"
                + "s.setProperty('--safe-area-inset-right','%.2fpx');"
                + "s.setProperty('--safe-area-inset-bottom','%.2fpx');"
                + "s.setProperty('--safe-area-inset-left','%.2fpx');})()",
            safeArea.top / density, safeArea.right / density, bottom / density, safeArea.left / density);
        bridge.getWebView().evaluateJavascript(script, null);
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
