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
import java.util.concurrent.ConcurrentHashMap;

/**
 * Native network boundary for the packaged App.
 *
 * Once a TrailSnap Server is selected, WebView HTTP(S) requests are accepted
 * only for that exact origin.  Before onboarding, private/LAN hosts are allowed
 * so discovery and connection testing can work.  App assets remain available
 * from Capacitor's localhost origin.
 *
 * Switching servers is a two-step flow (test first, then save).  While the JS
 * layer verifies a candidate origin, it registers that origin via
 * {@link #allowTemporaryOrigin(String, long)}; the JS-side guard in
 * nativeNetworkPolicy.ts must stay in sync with this class.
 */
public final class OfflineOnlyWebViewClient extends BridgeWebViewClient {
    private static final String PREFERENCES_GROUP = "CapacitorStorage";
    private static final String SERVER_URL_KEY = "trailsnap_server_url";

    private final Context context;

    /** Candidate origins pending verification, with wall-clock expiry stamps. */
    private final TemporaryOriginRegistry temporaryOrigins = new TemporaryOriginRegistry();

    public OfflineOnlyWebViewClient(Bridge bridge, Context context) {
        super(bridge);
        this.context = context.getApplicationContext();
    }

    /**
     * Allow one candidate server origin while the JS layer runs its health
     * check.  The WebView client reads this set from a different thread than
     * the plugin bridge, hence the concurrent map plus expiry stamps.
     */
    public void allowTemporaryOrigin(String origin, long ttlMs) {
        temporaryOrigins.allow(origin, ttlMs);
    }

    /** Drop a candidate origin once verification finished (success or failure). */
    public void revokeTemporaryOrigin(String origin) {
        temporaryOrigins.revoke(origin);
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

        if (isTemporarilyAllowed(scheme, host, uri)) return true;

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

    private boolean isTemporarilyAllowed(String scheme, String host, Uri uri) {
        return temporaryOrigins.contains(originKey(scheme, host, effectivePort(uri)));
    }

    /**
     * Candidate origins pending verification.  Keys are formatted exactly like
     * the JS {@code URL.origin} (default ports omitted, IPv6 bracketed) so the
     * JS guard and this native guard agree on what "same origin" means.
     */
    static final class TemporaryOriginRegistry {
        private final ConcurrentHashMap<String, Long> origins = new ConcurrentHashMap<>();

        /** @return whether the origin was accepted (http/https with a host). */
        boolean allow(String value, long ttlMs) {
            String key = normalize(value);
            if (key == null) return false;
            long ttl = Math.max(1_000L, Math.min(ttlMs, 120_000L));
            long now = System.currentTimeMillis();
            purgeExpired(now);
            origins.put(key, now + ttl);
            return true;
        }

        void revoke(String value) {
            String key = normalize(value);
            if (key != null) origins.remove(key);
        }

        boolean contains(String originKey) {
            if (origins.isEmpty()) return false;
            Long expiry = origins.get(originKey);
            if (expiry == null) return false;
            if (expiry < System.currentTimeMillis()) {
                origins.remove(originKey);
                return false;
            }
            return true;
        }

        boolean isEmpty() {
            return origins.isEmpty();
        }

        private void purgeExpired(long now) {
            for (String key : origins.keySet()) {
                Long expiry = origins.get(key);
                if (expiry != null && expiry < now) origins.remove(key);
            }
        }

        /**
         * Parse an http(s) origin string without android.net.Uri so unit tests
         * can run on the JVM (framework classes are stubs there).
         * @return the URL.origin-style key, or null when not http(s).
         */
        private static String normalize(String value) {
            if (value == null) return null;
            String candidate = value.trim();
            String scheme;
            String rest;
            int schemeEnd = candidate.indexOf("://");
            if (schemeEnd < 0) return null;
            scheme = lower(candidate.substring(0, schemeEnd));
            rest = candidate.substring(schemeEnd + 3);
            if (!scheme.equals("http") && !scheme.equals("https")) return null;

            // Strip any path/query/fragment: the authority ends at the first
            // '/', '?' or '#'.
            int authorityEnd = rest.length();
            for (int i = 0; i < rest.length(); i++) {
                char c = rest.charAt(i);
                if (c == '/' || c == '?' || c == '#') {
                    authorityEnd = i;
                    break;
                }
            }
            String authority = rest.substring(0, authorityEnd);

            // Split host and port. IPv6 literals are bracketed in an origin
            // string; the closing bracket may be followed by ':port'.
            String hostPart;
            String portPart = null;
            int closeBracket = authority.indexOf(']');
            int colon = authority.lastIndexOf(':');
            if (closeBracket >= 0) {
                hostPart = authority.substring(0, closeBracket + 1);
                if (closeBracket + 1 < authority.length() && authority.charAt(closeBracket + 1) == ':') {
                    portPart = authority.substring(closeBracket + 2);
                }
            } else if (colon >= 0) {
                hostPart = authority.substring(0, colon);
                portPart = authority.substring(colon + 1);
            } else {
                hostPart = authority;
            }
            String host = lower(stripBrackets(hostPart));
            if (host.isEmpty()) return null;

            int port;
            if (portPart == null || portPart.isEmpty()) {
                port = "https".equals(scheme) ? 443 : 80;
            } else {
                try {
                    port = Integer.parseInt(portPart);
                } catch (NumberFormatException ignored) {
                    return null;
                }
            }
            return originKey(scheme, host, port);
        }
    }

    /** Format scheme/host/port the way the JS URL.origin does. */
    private static String originKey(String scheme, String host, int port) {
        boolean defaultPort = ("http".equals(scheme) && port == 80) || ("https".equals(scheme) && port == 443);
        String hostPart = host.contains(":") ? "[" + host + "]" : host;
        return scheme + "://" + hostPart + (defaultPort ? "" : ":" + port);
    }

    private static String stripBrackets(String hostPart) {
        if (hostPart.startsWith("[") && hostPart.endsWith("]") && hostPart.length() >= 2) {
            return hostPart.substring(1, hostPart.length() - 1);
        }
        return hostPart;
    }

    private static int effectivePort(Uri uri) {
        if (uri.getPort() >= 0) return uri.getPort();
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    /** Hosts the JS connection screen may probe before any server is saved. */
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
