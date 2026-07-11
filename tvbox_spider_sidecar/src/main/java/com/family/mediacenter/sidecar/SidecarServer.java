package com.family.mediacenter.sidecar;

import com.github.catvod.spider.Proxy;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import io.javalin.Javalin;
import io.javalin.http.HttpStatus;

import java.util.LinkedHashMap;
import java.util.Map;

public final class SidecarServer {

    private static final Gson GSON = new Gson();
    private static final String VERSION = "0.2.0";

    private final int port;
    private Javalin app;

    public SidecarServer(int port) {
        this.port = port;
    }

    public void start() {
        Proxy.setPort(port);
        app = Javalin.create(config -> config.showJavalinBanner = false);
        app.get("/health", ctx -> ctx.json(healthPayload()));
        app.get("/api/v1/health", ctx -> ctx.json(healthPayload()));
        app.get("/proxy", ctx -> {
            if ("ck".equals(ctx.queryParam("do"))) {
                ctx.result("ok");
            } else {
                ctx.status(HttpStatus.NOT_FOUND).result("unsupported");
            }
        });
        app.get("/postMsg", ctx -> ctx.result("ok"));
        app.post("/api/v1/probe", ctx -> {
            JsonObject body = GSON.fromJson(ctx.body(), JsonObject.class);
            if (body == null) {
                ctx.status(HttpStatus.BAD_REQUEST).json(error("请求体为空"));
                return;
            }
            Spider spider = null;
            try {
                Map<String, Object> site = jsonToMap(body.getAsJsonObject("site"));
                String spiderJar = body.has("spiderJar") ? body.get("spiderJar").getAsString() : "";
                if (body.has("spider_jar")) {
                    spiderJar = body.get("spider_jar").getAsString();
                }
                String perSiteJar = site.containsKey("spider") ? String.valueOf(site.get("spider")) : "";
                if (perSiteJar != null && !perSiteJar.isBlank()) {
                    spiderJar = perSiteJar;
                }
                String keyword = body.has("keyword") ? body.get("keyword").getAsString() : "电影";
                long timeoutMs = 20000;
                if (body.has("timeoutSec")) {
                    timeoutMs = Math.max(5, body.get("timeoutSec").getAsLong()) * 1000L;
                }

                spider = SpiderRunner.createSpider(site, spiderJar);
                Map<String, Object> layers = SpiderRunner.probe(spider, keyword, timeoutMs);

                Map<String, Object> response = new LinkedHashMap<>();
                response.put("ok", true);
                response.put("site", siteLabel(site));
                response.put("layers", layers);
                ctx.json(response);
            } catch (Exception ex) {
                ctx.status(HttpStatus.OK).json(error(formatError(ex)));
            } finally {
                SpiderRunner.destroy(spider);
            }
        });
        app.start(port);
    }

    public void stop() {
        if (app != null) {
            app.stop();
        }
    }

    private static Map<String, Object> healthPayload() {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("ok", true);
        payload.put("version", VERSION);
        payload.put("service", "tvbox-spider-sidecar");
        payload.put("proxy", Proxy.getProxyUrl());
        return payload;
    }

    private static Map<String, Object> error(String message) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("ok", false);
        payload.put("error", message);
        return payload;
    }

    private static String formatError(Throwable ex) {
        StringBuilder sb = new StringBuilder();
        Throwable current = ex;
        while (current != null) {
            if (current.getMessage() != null && !current.getMessage().isBlank()) {
                if (sb.length() > 0) {
                    sb.append(" -> ");
                }
                sb.append(current.getMessage());
            }
            if (current.getCause() == null || current.getCause() == current) {
                break;
            }
            current = current.getCause();
        }
        if (sb.length() == 0) {
            sb.append(ex.getClass().getSimpleName());
        }
        return sb.toString();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> jsonToMap(JsonObject obj) {
        return GSON.fromJson(obj, Map.class);
    }

    private static String siteLabel(Map<String, Object> site) {
        Object name = site.get("name");
        if (name != null && !String.valueOf(name).isBlank()) {
            return String.valueOf(name);
        }
        Object api = site.get("api");
        return api == null ? "site" : String.valueOf(api);
    }
}
