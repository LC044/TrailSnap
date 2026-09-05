package cn.trailsnap.app;

import android.content.Context;
import android.net.Uri;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

/**
 * Native network boundary for the packaged App.
 *
 * Once a TrailSnap Server is selected, WebView HTTP(S) requests are accepted
 * only for that exact origin.  Before onboarding, private/LAN hosts are allowed
 * so discovery and connection testing can work.  App assets remain available
 * from Capacitor's localhost origin.
 */
public final class OfflineOnlyWebViewClient extends BridgeWebViewClient {
    private static final String PREFERENCES_GROUP = "CapacitorStorage";
    private static final String SERVER_URL_KEY = "trailsnap_server_url";

    private final Context context;

    public OfflineOnlyWebViewClient(Bridge bridge, Context context) {
        super(bridge);
        this.context = context.getApplicationContext();
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri uri = request.getUrl();
        if (isAllowed(uri)) return super.shouldInterceptRequest(view, request);
        byte[] body = "Blocked by TrailSnap offline network policy".getBytes(StandardCharsets.UTF_8);
        return new WebResourceResponse(
            "text/plain", "UTF-8", 403, "Blocked", null, new ByteArrayInputStream(body)
        );
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        Uri uri = request.getUrl();
        if (!isAllowed(uri)) return true;
        return super.shouldOverrideUrlLoading(view, request);
    }

    private boolean isAllowed(Uri uri) {
        String scheme = lower(uri.getScheme());
        if (scheme.equals("data") || scheme.equals("blob") || scheme.equals("file")
            || scheme.equals("content") || scheme.equals("capacitor")) return true;
        if (!scheme.equals("http") && !scheme.equals("https")) return false;

        String host = lower(uri.getHost());
        if (host.equals("localhost") || host.equals("127.0.0.1") || host.equals("::1")) return true;

        String configured = context
            .getSharedPreferences(PREFERENCES_GROUP, Context.MODE_PRIVATE)
            .getString(SERVER_URL_KEY, "");
        // Onboarding must be able to test a user-entered public or LAN URL.
        // The exact-origin boundary becomes active immediately after it is saved.
        if (configured == null || configured.isEmpty()) return true;
        Uri server = Uri.parse(configured);
        return scheme.equals(lower(server.getScheme()))
            && host.equals(lower(server.getHost()))
            && effectivePort(uri) == effectivePort(server);
    }

    private static int effectivePort(Uri uri) {
        if (uri.getPort() >= 0) return uri.getPort();
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    private static boolean isPrivateLanHost(String host) {
        if (host.endsWith(".local")) return true;
        if (host.startsWith("10.") || host.startsWith("192.168.")) return true;
        if (host.startsWith("169.254.")) return true;
        if (host.startsWith("172.")) {
            String[] parts = host.split("\\.");
            if (parts.length == 4) {
                try {
                    int second = Integer.parseInt(parts[1]);
                    return second >= 16 && second <= 31;
                } catch (NumberFormatException ignored) {}
            }
        }
        return host.startsWith("fc") || host.startsWith("fd") || host.startsWith("fe80:");
    }

    private static String lower(String value) {
        return value == null ? "" : value.toLowerCase(java.util.Locale.ROOT);
    }
}
