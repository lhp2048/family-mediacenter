package com.github.catvod.utils;

import com.github.catvod.crawler.SpiderDebug;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonSyntaxException;
import com.google.gson.stream.JsonReader;

import java.io.StringReader;
import java.lang.reflect.Type;

public final class Json {

    private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().setLenient().create();

    private Json() {
    }

    public static Gson get() {
        return GSON;
    }

    public static JsonElement parse(String json) {
        try {
            JsonReader reader = new JsonReader(new StringReader(json));
            reader.setLenient(true);
            return JsonParser.parseReader(reader);
        } catch (Throwable ignored) {
            return JsonParser.parseString(json);
        }
    }

    public static <T> T parseSafe(String json, Type type) {
        try {
            return GSON.fromJson(json, type);
        } catch (JsonSyntaxException e) {
            SpiderDebug.log("json parse error: " + e.getMessage());
            return null;
        }
    }

    public static String toJson(Object obj) {
        return GSON.toJson(obj);
    }

    public static JsonObject safeObject(String extend) {
        try {
            return JsonParser.parseString(extend).getAsJsonObject();
        } catch (JsonSyntaxException e) {
            return new JsonObject();
        }
    }
}
