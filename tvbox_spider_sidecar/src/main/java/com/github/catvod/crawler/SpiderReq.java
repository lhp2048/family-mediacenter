package com.github.catvod.crawler;

import com.github.catvod.net.OkHttp;

/** Deprecated SpiderReq compatibility wrapper. */
@Deprecated
public final class SpiderReq {

    private SpiderReq() {
    }

    public static String get(String url) throws Exception {
        return OkHttp.string(url);
    }

    public static String post(String url, String body) throws Exception {
        return OkHttp.post(url, body, null);
    }
}
