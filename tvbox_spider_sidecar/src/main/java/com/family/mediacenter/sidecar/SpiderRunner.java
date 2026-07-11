package com.family.mediacenter.sidecar;

import android.content.Context;
import com.github.catvod.crawler.Spider;
import com.github.catvod.spider.Init;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.lang.reflect.Method;
import java.net.URLClassLoader;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class SpiderRunner {

    private SpiderRunner() {
    }

    public static void destroy(Spider spider) {
        if (spider == null) {
            return;
        }
        try {
            spider.destroy();
        } catch (Exception ignored) {
        }
        try {
            spider.cancelByTag();
        } catch (Exception ignored) {
        }
    }

    public static Spider createSpider(Map<String, Object> site, String spiderJar) throws Exception {
        Init.init();
        String api = stringValue(site.get("api"));
        if (api.isEmpty()) {
            throw new IllegalArgumentException("站点缺少 api 字段");
        }
        if (!api.toLowerCase(Locale.ROOT).startsWith("csp_")) {
            throw new IllegalArgumentException("非 Spider 站点: " + api);
        }

        String simpleName = api.substring(4);
        List<String> candidates = classCandidates(simpleName);
        URLClassLoader loader = JarManager.getInstance().loaderFor(spiderJar);
        ClassLoader searchLoader = loader != null ? loader : SpiderRunner.class.getClassLoader();

        Class<?> clazz = null;
        String lastError = "";
        for (String name : candidates) {
            try {
                clazz = Class.forName(name, true, searchLoader);
                break;
            } catch (ClassNotFoundException | NoClassDefFoundError ex) {
                lastError = rootMessage(ex);
            }
        }
        if (clazz == null) {
            throw new ClassNotFoundException(
                    "未找到 Spider 类: " + simpleName + (lastError.isEmpty() ? "" : " (" + lastError + ")")
            );
        }

        Object instance = clazz.getDeclaredConstructor().newInstance();
        if (!(instance instanceof Spider)) {
            throw new IllegalStateException("类未继承 Spider: " + clazz.getName());
        }
        Spider spider = (Spider) instance;
        Context context = Init.context();
        String ext = stringValue(site.get("ext"));
        if (ext.isEmpty()) {
            spider.init(context);
        } else {
            spider.init(context, ext);
        }
        return spider;
    }

    private static List<String> classCandidates(String simpleName) {
        List<String> names = new ArrayList<>();
        names.add("com.github.catvod.spider." + simpleName);
        if (simpleName.length() > 0) {
            String cap = simpleName.substring(0, 1).toUpperCase(Locale.ROOT)
                    + simpleName.substring(1);
            if (!cap.equals(simpleName)) {
                names.add("com.github.catvod.spider." + cap);
            }
        }
        names.add("com.github.catvod.spider.custom." + simpleName);
        names.add("com.github.catvod.custom." + simpleName);
        names.add("com.github.catvod.spider." + simpleName.toLowerCase(Locale.ROOT));
        return names;
    }

    public static Map<String, Object> probe(
            Spider spider,
            String keyword,
            long timeoutMs
    ) throws Exception {
        Map<String, Object> out = new LinkedHashMap<>();

        String homeJson = invokeWithTimeout(spider, "homeContent", timeoutMs, true);
        JsonObject home = parseObject(homeJson);
        int classCount = arraySize(home, "class");
        int homeList = arraySize(home, "list");
        String typeId = firstTypeId(home);
        String vodId = firstVodId(home);

        Map<String, Object> l3 = new LinkedHashMap<>();
        if (classCount > 0 || homeList > 0) {
            l3.put("ok", true);
            l3.put("status", classCount > 0 ? "pass" : "partial");
            l3.put("score", classCount > 0 ? 15 : 12);
            l3.put("message", "Spider 首页 · 分类 " + classCount + " · 列表 " + homeList);
        } else {
            l3.put("ok", false);
            l3.put("status", "fail");
            l3.put("score", 0);
            l3.put("message", "Spider 首页无分类/列表数据");
        }
        l3.put("sample_vod_id", vodId);
        out.put("l3", l3);

        if (typeId != null && !typeId.isEmpty()) {
            HashMap<String, String> extend = new HashMap<>();
            String categoryJson = invokeCategory(spider, typeId, timeoutMs, extend);
            JsonObject category = parseObject(categoryJson);
            int catList = arraySize(category, "list");
            if (catList > 0 && (vodId == null || vodId.isEmpty())) {
                vodId = firstVodId(category);
                l3.put("sample_vod_id", vodId);
            }
        }

        Map<String, Object> l4 = new LinkedHashMap<>();
        String searchKey = keyword == null || keyword.isEmpty() ? "电影" : keyword;
        try {
            String searchJson = invokeWithTimeout(spider, "searchContent", timeoutMs, searchKey, false);
            JsonObject search = parseObject(searchJson);
            int searchCount = arraySize(search, "list");
            if (searchCount > 0) {
                String searchVod = firstVodId(search);
                if (searchVod != null && !searchVod.isEmpty()) {
                    vodId = searchVod;
                }
                l4.put("ok", true);
                l4.put("status", "pass");
                l4.put("score", 10);
                l4.put("message", "Spider 搜索「" + searchKey + "」" + searchCount + " 条");
            } else if (vodId != null && !vodId.isEmpty()) {
                l4.put("ok", true);
                l4.put("status", "partial");
                l4.put("score", 5);
                l4.put("message", "Spider 搜索无结果，沿用首页样本");
            } else {
                l4.put("ok", false);
                l4.put("status", "fail");
                l4.put("score", 0);
                l4.put("message", "Spider 搜索无结果");
            }
        } catch (Exception ex) {
            if (vodId != null && !vodId.isEmpty()) {
                l4.put("ok", true);
                l4.put("status", "partial");
                l4.put("score", 5);
                l4.put("message", "Spider 搜索异常，沿用首页样本: " + ex.getMessage());
            } else {
                l4.put("ok", false);
                l4.put("status", "fail");
                l4.put("score", 0);
                l4.put("message", "Spider 搜索失败: " + ex.getMessage());
            }
        }
        l4.put("sample_vod_id", vodId);
        out.put("l4", l4);

        Map<String, Object> l5 = new LinkedHashMap<>();
        if (vodId == null || vodId.isEmpty()) {
            l5.put("ok", false);
            l5.put("status", "fail");
            l5.put("score", 0);
            l5.put("message", "Spider 无 vod_id，跳过播放探测");
        } else {
            try {
                List<String> ids = List.of(vodId);
                String detailJson = invokeDetail(spider, ids, timeoutMs);
                JsonObject detail = parseObject(detailJson);
                JsonObject item = firstListItem(detail);
                String playUrl = extractPlaySignal(item);
                String playFlag = extractPlayFlag(item);
                if (playUrl == null || playUrl.isEmpty()) {
                    try {
                        String playerJson = invokePlayerContent(spider, playFlag, vodId, timeoutMs);
                        JsonObject player = parseObject(playerJson);
                        playUrl = extractPlayerUrl(player);
                    } catch (Exception ignored) {
                    }
                }
                if (playUrl != null && !playUrl.isEmpty()) {
                    l5.put("ok", true);
                    l5.put("status", "pass");
                    l5.put("score", 20);
                    l5.put("message", "Spider 详情含播放地址");
                    l5.put("play_preview", playUrl.length() > 80 ? playUrl.substring(0, 80) : playUrl);
                } else {
                    l5.put("ok", true);
                    l5.put("status", "partial");
                    l5.put("score", 8);
                    l5.put("message", "Spider 详情可达但无播放字段");
                }
                l5.put("vod_id", vodId);
            } catch (Exception ex) {
                l5.put("ok", false);
                l5.put("status", "fail");
                l5.put("score", 0);
                l5.put("message", "Spider 详情失败: " + ex.getMessage());
            }
        }
        out.put("l5", l5);
        return out;
    }

    private static String invokeCategory(
            Spider spider,
            String typeId,
            long timeoutMs,
            HashMap<String, String> extend
    ) throws Exception {
        Method method = spider.getClass().getMethod(
                "categoryContent",
                String.class,
                String.class,
                boolean.class,
                HashMap.class
        );
        return runWithTimeout(
                () -> (String) method.invoke(spider, typeId, "1", false, extend),
                timeoutMs
        );
    }

    private static String invokeDetail(Spider spider, List<String> ids, long timeoutMs) throws Exception {
        Method method = spider.getClass().getMethod("detailContent", List.class);
        return runWithTimeout(() -> (String) method.invoke(spider, ids), timeoutMs);
    }

    private static String invokeWithTimeout(Spider spider, String methodName, long timeoutMs, Object... args)
            throws Exception {
        Method method = resolveMethod(spider.getClass(), methodName, args);
        return runWithTimeout(() -> (String) method.invoke(spider, args), timeoutMs);
    }

    private static Method resolveMethod(Class<?> clazz, String methodName, Object... args) throws NoSuchMethodException {
        for (Method method : clazz.getMethods()) {
            if (!method.getName().equals(methodName)) {
                continue;
            }
            Class<?>[] paramTypes = method.getParameterTypes();
            if (paramTypes.length != args.length) {
                continue;
            }
            boolean match = true;
            for (int i = 0; i < args.length; i++) {
                if (!isCompatible(paramTypes[i], args[i])) {
                    match = false;
                    break;
                }
            }
            if (match) {
                return method;
            }
        }
        throw new NoSuchMethodException(methodName);
    }

    private static boolean isCompatible(Class<?> paramType, Object value) {
        if (value == null) {
            return !paramType.isPrimitive();
        }
        if (paramType.isPrimitive()) {
            if (paramType == boolean.class) {
                return value instanceof Boolean;
            }
            if (paramType == int.class) {
                return value instanceof Integer;
            }
            if (paramType == long.class) {
                return value instanceof Long;
            }
        }
        return paramType.isAssignableFrom(value.getClass());
    }

    @FunctionalInterface
    private interface CallableString {
        String call() throws Exception;
    }

    private static String runWithTimeout(CallableString task, long timeoutMs) throws Exception {
        final String[] holder = new String[1];
        final Exception[] error = new Exception[1];
        Thread worker = new Thread(() -> {
            try {
                holder[0] = task.call();
            } catch (Exception ex) {
                error[0] = ex;
            }
        });
        worker.start();
        worker.join(timeoutMs);
        if (worker.isAlive()) {
            worker.interrupt();
            throw new RuntimeException("Spider 调用超时");
        }
        if (error[0] != null) {
            throw error[0];
        }
        return holder[0] == null ? "" : holder[0];
    }

    private static JsonObject parseObject(String json) {
        if (json == null || json.trim().isEmpty()) {
            return new JsonObject();
        }
        JsonElement element = JsonParser.parseString(json);
        if (element != null && element.isJsonObject()) {
            return element.getAsJsonObject();
        }
        return new JsonObject();
    }

    private static int arraySize(JsonObject obj, String key) {
        if (obj == null || !obj.has(key) || !obj.get(key).isJsonArray()) {
            return 0;
        }
        return obj.getAsJsonArray(key).size();
    }

    private static String firstTypeId(JsonObject obj) {
        if (obj == null || !obj.has("class") || !obj.get("class").isJsonArray()) {
            return "";
        }
        JsonArray arr = obj.getAsJsonArray("class");
        if (arr.size() == 0 || !arr.get(0).isJsonObject()) {
            return "";
        }
        JsonObject item = arr.get(0).getAsJsonObject();
        if (item.has("type_id")) {
            return item.get("type_id").getAsString();
        }
        if (item.has("typeId")) {
            return item.get("typeId").getAsString();
        }
        return "";
    }

    private static String firstVodId(JsonObject obj) {
        JsonObject item = firstListItem(obj);
        if (item == null) {
            return "";
        }
        if (item.has("vod_id")) {
            return item.get("vod_id").getAsString();
        }
        if (item.has("vodId")) {
            return item.get("vodId").getAsString();
        }
        if (item.has("id")) {
            return item.get("id").getAsString();
        }
        return "";
    }

    private static JsonObject firstListItem(JsonObject obj) {
        if (obj == null || !obj.has("list") || !obj.get("list").isJsonArray()) {
            return null;
        }
        JsonArray arr = obj.getAsJsonArray("list");
        if (arr.size() == 0 || !arr.get(0).isJsonObject()) {
            return null;
        }
        return arr.get(0).getAsJsonObject();
    }

    private static String invokePlayerContent(
            Spider spider,
            String flag,
            String vodId,
            long timeoutMs
    ) throws Exception {
        List<String> vipFlags = new ArrayList<>();
        return invokeWithTimeout(spider, "playerContent", timeoutMs, flag, vodId, vipFlags);
    }

    private static String extractPlayFlag(JsonObject item) {
        if (item == null) {
            return "play";
        }
        if (item.has("vod_play_from")) {
            return item.get("vod_play_from").getAsString();
        }
        if (item.has("vodPlayFrom")) {
            return item.get("vodPlayFrom").getAsString();
        }
        return "play";
    }

    private static String extractPlayerUrl(JsonObject player) {
        if (player == null) {
            return "";
        }
        if (player.has("url")) {
            return player.get("url").getAsString();
        }
        if (player.has("playUrl")) {
            return player.get("playUrl").getAsString();
        }
        return "";
    }

    private static String extractPlaySignal(JsonObject item) {
        if (item == null) {
            return "";
        }
        if (item.has("vod_play_url")) {
            return item.get("vod_play_url").getAsString();
        }
        if (item.has("vodPlayUrl")) {
            return item.get("vodPlayUrl").getAsString();
        }
        return "";
    }

    private static String stringValue(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private static String rootMessage(Throwable ex) {
        Throwable current = ex;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current.getMessage() == null ? current.getClass().getSimpleName() : current.getMessage();
    }
}
