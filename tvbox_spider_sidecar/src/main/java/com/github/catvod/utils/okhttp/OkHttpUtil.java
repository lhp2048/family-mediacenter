package com.github.catvod.utils.okhttp;

import com.github.catvod.crawler.SpiderDebug;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

import java.io.IOException;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/** Simplified CatVod OkHttpUtil for PC-side Spider JARs. */
public final class OkHttpUtil {

    public static final String METHOD_GET = "GET";
    public static final String METHOD_POST = "POST";

    private static OkHttpClient defaultClient;

    private OkHttpUtil() {
    }

    private static OkHttpClient client() {
        if (defaultClient == null) {
            synchronized (OkHttpUtil.class) {
                if (defaultClient == null) {
                    defaultClient = new OkHttpClient.Builder()
                            .connectTimeout(15, TimeUnit.SECONDS)
                            .readTimeout(20, TimeUnit.SECONDS)
                            .followRedirects(true)
                            .followSslRedirects(true)
                            .build();
                }
            }
        }
        return defaultClient;
    }

    public static String string(String url) throws IOException {
        return string(url, null);
    }

    public static String string(String url, Map<String, String> headers) throws IOException {
        return string(client(), url, headers);
    }

    public static String string(OkHttpClient client, String url, Map<String, String> headers) throws IOException {
        Request.Builder builder = new Request.Builder().url(url).get();
        applyHeaders(builder, headers);
        try (Response response = client.newCall(builder.build()).execute()) {
            if (response.body() == null) {
                return "";
            }
            return response.body().string();
        }
    }

    public static String post(String url, String body, Map<String, String> headers) throws IOException {
        RequestBody requestBody = RequestBody.create(
                body == null ? "" : body,
                MediaType.parse("application/json; charset=utf-8")
        );
        Request.Builder builder = new Request.Builder().url(url).post(requestBody);
        applyHeaders(builder, headers);
        try (Response response = client().newCall(builder.build()).execute()) {
            if (response.body() == null) {
                return "";
            }
            return response.body().string();
        }
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

    private static void applyHeaders(Request.Builder builder, Map<String, String> headers) {
        if (headers == null || headers.isEmpty()) {
            builder.header(
                    "User-Agent",
                    "Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
            );
            return;
        }
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            if (entry.getKey() != null && entry.getValue() != null) {
                builder.header(entry.getKey(), entry.getValue());
            }
        }
    }

    public static Map<String, List<String>> emptyRespHeaders() {
        return Collections.emptyMap();
    }

    public static void logError(Exception e) {
        SpiderDebug.log(e);
    }
}
