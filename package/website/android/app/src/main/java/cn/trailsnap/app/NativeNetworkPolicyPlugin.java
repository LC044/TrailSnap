package cn.trailsnap.app;

import android.webkit.WebViewClient;

import com.getcapacitor.Bridge;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Bridge between the JS-layer network guard (nativeNetworkPolicy.ts) and the
 * native WebView boundary (OfflineOnlyWebViewClient).
 *
 * The connection screen tests a candidate server BEFORE saving it. The native
 * boundary only allows the already-saved origin, so without this bridge every
 * health check to a new server would be answered with a CORS-less 403 and the
 * JS fetch would fail with "Failed to fetch". The JS layer mirrors this with
 * withTemporaryServerAccess(); both sides must allow the same origin for the
 * test request to pass.
 */
@CapacitorPlugin(name = "NativeNetworkPolicy")
public class NativeNetworkPolicyPlugin extends Plugin {
    private static final long DEFAULT_TTL_MS = 30_000L;

    @PluginMethod
    public void allowTemporaryOrigin(PluginCall call) {
        String origin = call.getString("origin");
        if (origin == null || origin.isEmpty()) {
            call.reject("origin is required");
            return;
        }
        Long ttlMs = call.getLong("ttlMs");
        long ttl = ttlMs == null ? DEFAULT_TTL_MS : ttlMs;

        OfflineOnlyWebViewClient client = webViewClient();
        if (client == null) {
            // Older runtime without the native boundary: nothing to allow.
            call.resolve();
            return;
        }
        client.allowTemporaryOrigin(origin, ttl);
        call.resolve();
    }

    @PluginMethod
    public void revokeTemporaryOrigin(PluginCall call) {
        String origin = call.getString("origin");
        if (origin == null || origin.isEmpty()) {
            call.reject("origin is required");
            return;
        }
        OfflineOnlyWebViewClient client = webViewClient();
        if (client != null) client.revokeTemporaryOrigin(origin);
        call.resolve();
    }

    private OfflineOnlyWebViewClient webViewClient() {
        Bridge bridge = getBridge();
        if (bridge == null) return null;
        WebViewClient client = bridge.getWebViewClient();
        return client instanceof OfflineOnlyWebViewClient ? (OfflineOnlyWebViewClient) client : null;
    }
}
