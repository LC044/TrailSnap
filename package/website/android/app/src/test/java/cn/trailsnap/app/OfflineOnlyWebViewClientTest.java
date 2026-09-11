package cn.trailsnap.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The temporary-origin mechanism exists so the connection screen can health
 * check a NEW server while the native boundary still pins the saved one.
 * Its key formats must match the JS URL.origin produced by
 * nativeNetworkPolicy.ts, otherwise the test request is answered with a
 * CORS-less 403 ("Failed to fetch").
 *
 * These tests run on the JVM (no Robolectric), so they exercise the pure
 * origin-string layer: registration -> key normalization -> lookup/revoke.
 */
public class OfflineOnlyWebViewClientTest {
    private final OfflineOnlyWebViewClient.TemporaryOriginRegistry registry =
        new OfflineOnlyWebViewClient.TemporaryOriginRegistry();

    @Test
    public void registeredOriginMatchesRequestUrls() {
        registry.allow("http://192.168.1.20:3180", 30_000);
        // Request URL -> origin uses the same formatting as URL.origin.
        assertTrue(registry.contains(formatRequestOrigin("http", "192.168.1.20", 3180)));
        assertFalse(registry.contains(formatRequestOrigin("http", "192.168.1.21", 3180)));
        assertFalse(registry.contains(formatRequestOrigin("http", "192.168.1.20", 3181)));
        assertFalse(registry.contains(formatRequestOrigin("https", "192.168.1.20", 3180)));
    }

    @Test
    public void defaultPortsAreOmittedLikeJsUrlOrigin() {
        registry.allow("http://192.168.1.20", 30_000);
        assertTrue(registry.contains(formatRequestOrigin("http", "192.168.1.20", 80)));
        assertFalse(registry.contains(formatRequestOrigin("http", "192.168.1.20", 8080)));
    }

    @Test
    public void ipv6LiteralsAreBracketedLikeJsUrlOrigin() {
        registry.allow("http://[fe80::a1]:3180", 30_000);
        assertTrue(registry.contains(formatRequestOrigin("http", "fe80::a1", 3180)));
    }

    @Test
    public void revokeRemovesOnlyTheTargetOrigin() {
        registry.allow("http://192.168.1.20:3180", 30_000);
        registry.allow("http://192.168.1.30:3180", 30_000);
        registry.revoke("http://192.168.1.20:3180");
        assertFalse(registry.contains(formatRequestOrigin("http", "192.168.1.20", 3180)));
        assertTrue(registry.contains(formatRequestOrigin("http", "192.168.1.30", 3180)));
    }

    @Test
    public void expiredOriginsStopMatching() {
        registry.allow("http://192.168.1.20:3180", 1);
        try {
            Thread.sleep(1_200);
        } catch (InterruptedException ignored) {
        }
        assertFalse(registry.contains(formatRequestOrigin("http", "192.168.1.20", 3180)));
    }

    @Test
    public void nonHttpOriginsAreRejectedFromRegistration() {
        assertFalse(registry.allow("file:///etc/hosts", 30_000));
        assertFalse(registry.allow("javascript:alert(1)", 30_000));
        assertFalse(registry.allow("not a url", 30_000));
        assertTrue(registry.isEmpty());
    }

    @Test
    public void schemeAndHostAreCaseInsensitive() {
        registry.allow("HTTP://Example.COM:3180", 30_000);
        assertTrue(registry.contains(formatRequestOrigin("http", "example.com", 3180)));
    }

    /** Mirrors what isTemporarilyAllowed builds for an intercepted request. */
    private static String formatRequestOrigin(String scheme, String host, int port) {
        boolean defaultPort = ("http".equals(scheme) && port == 80) || ("https".equals(scheme) && port == 443);
        String hostPart = host.contains(":") ? "[" + host + "]" : host;
        return scheme + "://" + hostPart + (defaultPort ? "" : ":" + port);
    }
}
