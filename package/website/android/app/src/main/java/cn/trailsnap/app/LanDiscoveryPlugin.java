package cn.trailsnap.app;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

@CapacitorPlugin(name = "LanDiscovery")
public class LanDiscoveryPlugin extends Plugin {
    private static final int DEFAULT_PORT = 8082;
    private static final int DEFAULT_TIMEOUT_MS = 400;
    private static final int MIN_PREFIX_LENGTH = 24;
    private static final int MAX_NETWORKS = 3;

    private final ExecutorService coordinator = Executors.newSingleThreadExecutor();
    private final ExecutorService probes = Executors.newFixedThreadPool(32);

    @PluginMethod
    public void discover(PluginCall call) {
        Integer requestedPort = call.getInt("port");
        Integer requestedTimeout = call.getInt("timeoutMs");
        int port = requestedPort == null ? DEFAULT_PORT : requestedPort;
        int timeoutMs = requestedTimeout == null ? DEFAULT_TIMEOUT_MS : requestedTimeout;

        if (port < 1 || port > 65535) {
            call.reject("无效的局域网探测端口");
            return;
        }
        timeoutMs = Math.max(150, Math.min(timeoutMs, 1500));

        final int probeTimeoutMs = timeoutMs;
        coordinator.execute(() -> {
            try {
                List<Subnet> subnets = findPrivateSubnets();
                List<ProbeResult> services = scanSubnets(subnets, port, probeTimeoutMs);
                JSArray resultServices = new JSArray();
                for (ProbeResult service : services) {
                    JSObject item = new JSObject();
                    item.put("url", service.url);
                    item.put("name", service.name);
                    item.put("version", service.version);
                    resultServices.put(item);
                }

                JSObject result = new JSObject();
                result.put("services", resultServices);
                result.put("scannedNetworks", subnets.size());
                call.resolve(result);
            } catch (Exception error) {
                call.reject("无法扫描当前局域网", error);
            }
        });
    }

    private List<Subnet> findPrivateSubnets() throws Exception {
        Map<String, Subnet> subnets = new LinkedHashMap<>();
        ConnectivityManager manager = (ConnectivityManager) getContext().getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager != null) {
            for (Network network : manager.getAllNetworks()) {
                NetworkCapabilities capabilities = manager.getNetworkCapabilities(network);
                if (capabilities == null || (!capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
                    && !capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET))) continue;
                LinkProperties properties = manager.getLinkProperties(network);
                if (properties == null) continue;
                for (LinkAddress linkAddress : properties.getLinkAddresses()) {
                    addSubnet(subnets, linkAddress.getAddress(), linkAddress.getPrefixLength());
                }
            }
        }

        Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
        if (interfaces != null) {
            for (NetworkInterface networkInterface : Collections.list(interfaces)) {
                if (!networkInterface.isUp() || networkInterface.isLoopback() || !isLanInterface(networkInterface.getName())) continue;
                for (InterfaceAddress interfaceAddress : networkInterface.getInterfaceAddresses()) {
                    addSubnet(subnets, interfaceAddress.getAddress(), interfaceAddress.getNetworkPrefixLength());
                }
            }
        }
        return new ArrayList<>(subnets.values()).subList(0, Math.min(subnets.size(), MAX_NETWORKS));
    }

    private boolean isLanInterface(String name) {
        String normalized = name == null ? "" : name.toLowerCase();
        return normalized.contains("wlan")
            || normalized.contains("wifi")
            || normalized.contains("softap")
            || normalized.startsWith("ap")
            || normalized.startsWith("eth")
            || normalized.startsWith("en");
    }

    private void addSubnet(Map<String, Subnet> subnets, InetAddress address, int prefixLength) {
        if (!(address instanceof Inet4Address) || !address.isSiteLocalAddress()) return;
        int effectivePrefix = Math.max(prefixLength, MIN_PREFIX_LENGTH);
        if (effectivePrefix > 30) return;

        long ip = ipv4ToLong(address.getAddress());
        long mask = (0xffffffffL << (32 - effectivePrefix)) & 0xffffffffL;
        long network = ip & mask;
        Subnet subnet = new Subnet(network, effectivePrefix, ip);
        subnets.putIfAbsent(network + "/" + effectivePrefix, subnet);
    }

    private List<ProbeResult> scanSubnets(List<Subnet> subnets, int port, int timeoutMs) throws Exception {
        List<Future<ProbeResult>> futures = new ArrayList<>();
        for (Subnet subnet : subnets) {
            long hostCount = 1L << (32 - subnet.prefixLength);
            long first = subnet.network + 1;
            long last = subnet.network + hostCount - 2;
            for (long candidate = first; candidate <= last; candidate++) {
                if (candidate == subnet.ownAddress) continue;
                final long candidateAddress = candidate;
                futures.add(probes.submit(() -> probe(candidateAddress, port, timeoutMs)));
            }
        }

        Map<String, ProbeResult> results = new LinkedHashMap<>();
        for (Future<ProbeResult> future : futures) {
            ProbeResult result = future.get();
            if (result != null) results.putIfAbsent(result.url, result);
        }
        return new ArrayList<>(results.values());
    }

    private ProbeResult probe(long address, int port, int timeoutMs) {
        HttpURLConnection connection = null;
        try {
            String host = InetAddress.getByAddress(longToIpv4(address)).getHostAddress();
            String origin = "http://" + host + ":" + port;
            connection = (HttpURLConnection) new URL(origin + "/.well-known/trailsnap").openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(timeoutMs);
            connection.setReadTimeout(Math.max(timeoutMs, 500));
            connection.setRequestProperty("Accept", "application/json");
            connection.setUseCaches(false);
            if (connection.getResponseCode() != HttpURLConnection.HTTP_OK) return null;

            String body;
            try (InputStream input = connection.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[2048];
                int total = 0;
                int read;
                while ((read = input.read(buffer)) != -1 && total < 16384) {
                    int length = Math.min(read, 16384 - total);
                    output.write(buffer, 0, length);
                    total += length;
                }
                body = output.toString(StandardCharsets.UTF_8.name());
            }

            JSONObject payload = new JSONObject(body);
            JSONObject data = payload.optJSONObject("data");
            if (payload.optInt("code", -1) != 0 || data == null || !"trailsnap".equals(data.optString("service"))) {
                return null;
            }
            return new ProbeResult(
                origin,
                data.optString("instance_name", "TrailSnap"),
                data.optString("version", "")
            );
        } catch (Exception ignored) {
            return null;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private static long ipv4ToLong(byte[] address) {
        return ((long) address[0] & 0xff) << 24
            | ((long) address[1] & 0xff) << 16
            | ((long) address[2] & 0xff) << 8
            | ((long) address[3] & 0xff);
    }

    private static byte[] longToIpv4(long address) {
        return new byte[] {
            (byte) (address >> 24),
            (byte) (address >> 16),
            (byte) (address >> 8),
            (byte) address,
        };
    }

    @Override
    protected void handleOnDestroy() {
        coordinator.shutdownNow();
        probes.shutdownNow();
    }

    private static final class Subnet {
        private final long network;
        private final int prefixLength;
        private final long ownAddress;

        private Subnet(long network, int prefixLength, long ownAddress) {
            this.network = network;
            this.prefixLength = prefixLength;
            this.ownAddress = ownAddress;
        }
    }

    private static final class ProbeResult {
        private final String url;
        private final String name;
        private final String version;

        private ProbeResult(String url, String name, String version) {
            this.url = url;
            this.name = name;
            this.version = version;
        }
    }
}
