package com.github.catvod.net;

import okhttp3.FormBody;
import okhttp3.Headers;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

import java.io.IOException;
import java.util.Map;

/** Minimal OkRequest used by community Spider JARs. */
public class OkRequest {

    private final String method;
    private final String url;
    private final Map<String, String> params;
    private final Map<String, String> headers;
    private final String jsonBody;

    public OkRequest(String method, String url, Map<String, String> params, Map<String, String> headers) {
        this(method, url, params, headers, null);
    }

    public OkRequest(String method, String url, String jsonBody, Map<String, String> headers) {
        this(method, url, null, headers, jsonBody);
    }

    private OkRequest(
            String method,
            String url,
            Map<String, String> params,
            Map<String, String> headers,
            String jsonBody
    ) {
        this.method = method == null ? OkHttp.GET : method;
        this.url = url;
        this.params = params;
        this.headers = headers;
        this.jsonBody = jsonBody;
    }

    public OkResult execute(OkHttpClient client) {
        try {
            Request request = buildRequest();
            try (Response response = client.newCall(request).execute()) {
                String body = response.body() == null ? "" : response.body().string();
                return new OkResult(response.code(), body, response.headers().toMultimap());
            }
        } catch (IOException ex) {
            return new OkResult(500, ex.getMessage(), null);
        }
    }

    private Request buildRequest() {
        Request.Builder builder = new Request.Builder().url(url);
        if (headers != null && !headers.isEmpty()) {
            builder.headers(Headers.of(headers));
        }
        if (OkHttp.POST.equalsIgnoreCase(method)) {
            if (jsonBody != null) {
                builder.post(RequestBody.create(jsonBody, MediaType.parse("application/json; charset=utf-8")));
            } else {
                FormBody.Builder form = new FormBody.Builder();
                if (params != null) {
                    for (Map.Entry<String, String> entry : params.entrySet()) {
                        if (entry.getKey() != null && entry.getValue() != null) {
                            form.add(entry.getKey(), entry.getValue());
                        }
                    }
                }
                builder.post(form.build());
            }
        } else {
            builder.get();
        }
        return builder.build();
    }
}
