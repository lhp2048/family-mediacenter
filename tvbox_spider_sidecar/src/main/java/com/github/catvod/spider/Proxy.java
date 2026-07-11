package com.github.catvod.spider;

import com.github.catvod.crawler.SpiderDebug;
import com.github.catvod.net.OkHttp;

import java.util.Map;

/** Sidecar proxy stub for Spider.proxyLocal / Util.notify. */
public final class Proxy {

    private static volatile int port = 9978;

    private Proxy() {
    }

    public static void setPort(int value) {
        if (value > 0) {
            port = value;
        }
    }

    public static int getPort() {
        return port;
    }

    public static void adjustPort() {
        if (port > 0) {
            try {
                String resp = OkHttp.string("http://127.0.0.1:" + port + "/proxy?do=ck", null);
                if ("ok".equals(resp)) {
                    return;
                }
            } catch (Exception ignored) {
            }
        }
        for (int pt = 9978; pt < 10000; pt++) {
            try {
                String resp = OkHttp.string("http://127.0.0.1:" + pt + "/proxy?do=ck", null);
                if ("ok".equals(resp)) {
                    SpiderDebug.log("Found local proxy port " + pt);
                    port = pt;
                    return;
                }
            } catch (Exception ignored) {
            }
        }
    }

    public static String getHostPort() {
        adjustPort();
        return "http://127.0.0.1:" + port;
    }

    public static String getProxyUrl() {
        return getHostPort() + "/proxy";
    }

    public static Object[] proxy(Map<String, String> params) {
        return null;
    }
}
