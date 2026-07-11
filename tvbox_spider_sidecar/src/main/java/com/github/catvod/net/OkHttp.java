package com.github.catvod.net;

import com.github.catvod.crawler.Spider;
import okhttp3.Dns;
import okhttp3.Headers;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/** CatVod-compatible HTTP helper backed by OkHttp. */
public final class OkHttp {

    public static final String POST = "POST";
    public static final String GET = "GET";

    private static OkHttpClient client;

    private OkHttp() {
    }

    public static Dns dns() {
        return Spider.safeDns();
    }

    public static OkHttpClient client() {
        if (client == null) {
            synchronized (OkHttp.class) {
                if (client == null) {
                    client = getBuilder().build();
                }
            }
        }
        return client;
    }

    public static OkHttpClient.Builder getBuilder() {
        return new OkHttpClient.Builder()
                .dns(dns())
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .writeTimeout(20, TimeUnit.SECONDS)
                .followRedirects(true)
                .followSslRedirects(true);
    }

    public static Response newCall(Request request) throws IOException {
        return client().newCall(request).execute();
    }

    public static Response newCall(String url) throws IOException {
        return client().newCall(new Request.Builder().url(url).build()).execute();
    }

    public static Response newCall(String url, Map<String, String> header) throws IOException {
        Request.Builder builder = new Request.Builder().url(url);
        if (header != null && !header.isEmpty()) {
            builder.headers(Headers.of(header));
        }
        return client().newCall(builder.build()).execute();
    }

    public static String string(String url) throws IOException {
        return string(url, null);
    }

    public static String string(String url, Map<String, String> headers) throws IOException {
        return string(client(), url, null, headers);
    }

    public static String string(OkHttpClient client, String url, Map<String, String> headers) throws IOException {
        return string(client, url, null, headers);
    }

    public static String string(
            OkHttpClient client,
            String url,
            Map<String, String> params,
            Map<String, String> headers
    ) throws IOException {
        if (url == null || !url.startsWith("http")) {
            return "";
        }
        return new OkRequest(GET, url, params, headers).execute(client).getBody();
    }

    public static OkResult post(String url, Map<String, String> params) throws IOException {
        return post(client(), url, params, null);
    }

    public static OkResult post(OkHttpClient client, String url, Map<String, String> params, Map<String, String> headers)
            throws IOException {
        return new OkRequest(POST, url, params, headers).execute(client);
    }

    public static OkResult postJson(String url, String json, Map<String, String> headers) throws IOException {
        return postJson(client(), url, json, headers);
    }

    public static OkResult postJson(OkHttpClient client, String url, String json, Map<String, String> headers)
            throws IOException {
        return new OkRequest(POST, url, json, headers).execute(client);
    }

    /** Legacy CatVod helper returning response body. */
    public static String post(String url, String body, Map<String, String> headers) throws IOException {
        return postJson(url, body, headers).getBody();
    }

    public static OkResult get(String url, Map<String, String> params, Map<String, String> headers) throws IOException {
        return new OkRequest(GET, url, params, headers).execute(client());
    }

    public static byte[] bytes(String url, Map<String, String> headers) throws IOException {
        Request.Builder builder = new Request.Builder().url(url).get();
        applyHeaders(builder, headers);
        try (Response response = client().newCall(builder.build()).execute()) {
            if (response.body() == null) {
                return new byte[0];
            }
            return response.body().bytes();
        }
    }

    public static String getLocation(String url, Map<String, String> header) throws IOException {
        OkHttpClient noRedirect = client().newBuilder()
                .followRedirects(false)
                .followSslRedirects(false)
                .build();
        Request.Builder builder = new Request.Builder().url(url);
        if (header != null && !header.isEmpty()) {
            builder.headers(Headers.of(header));
        }
        try (Response response = noRedirect.newCall(builder.build()).execute()) {
            return getLocation(response.headers().toMultimap());
        }
    }

    public static String getLocation(Map<String, List<String>> headers) {
        if (headers == null) {
            return null;
        }
        if (headers.containsKey("location") && !headers.get("location").isEmpty()) {
            return headers.get("location").get(0);
        }
        if (headers.containsKey("Location") && !headers.get("Location").isEmpty()) {
            return headers.get("Location").get(0);
        }
        return null;
    }

    private static void applyHeaders(Request.Builder builder, Map<String, String> headers) {
        if (headers == null || headers.isEmpty()) {
            builder.header(
                    "User-Agent",
                    "Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
            );
            return;
        }
        Headers.Builder hb = new Headers.Builder();
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            if (entry.getKey() != null && entry.getValue() != null) {
                hb.add(entry.getKey(), entry.getValue());
            }
        }
        builder.headers(hb.build());
    }
}
