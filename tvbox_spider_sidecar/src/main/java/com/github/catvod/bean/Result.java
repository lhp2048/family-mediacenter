package com.github.catvod.bean;

import com.google.gson.Gson;
import com.google.gson.annotations.SerializedName;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class Result {

    @SerializedName("class")
    private List<Class> classes;
    @SerializedName("list")
    private List<Vod> list;
    @SerializedName("filters")
    private LinkedHashMap<String, List<Filter>> filters;
    @SerializedName("header")
    private String header;
    @SerializedName("format")
    private String format;
    @SerializedName("msg")
    private String msg;
    @SerializedName("url")
    private Object url;
    @SerializedName("parse")
    private int parse;
    @SerializedName("jx")
    private int jx;
    @SerializedName("page")
    private Integer page;
    @SerializedName("pagecount")
    private Integer pagecount;
    @SerializedName("limit")
    private Integer limit;
    @SerializedName("total")
    private Integer total;

    public static Result get() {
        return new Result();
    }

    public static String error(String msg) {
        return get().vod(Collections.emptyList()).msg(msg).string();
    }

    public static String string(List<Class> classes, List<Vod> list) {
        return get().classes(classes).vod(list).string();
    }

    public static String string(List<Vod> list) {
        return get().vod(list).string();
    }

    public Result msg(String msg) {
        this.msg = msg;
        return this;
    }

    public Result classes(List<Class> classes) {
        this.classes = classes;
        return this;
    }

    public Result vod(List<Vod> list) {
        this.list = list;
        return this;
    }

    public Result vod(Vod item) {
        this.list = Collections.singletonList(item);
        return this;
    }

    public Result filters(LinkedHashMap<String, List<Filter>> filters) {
        this.filters = filters;
        return this;
    }

    public Result header(Map<String, String> header) {
        if (header != null && !header.isEmpty()) {
            this.header = new Gson().toJson(header);
        }
        return this;
    }

    public Result parse(int parse) {
        this.parse = parse;
        return this;
    }

    public Result url(String url) {
        this.url = url;
        return this;
    }

    public Result page(int page, int count, int limit, int total) {
        this.page = page > 0 ? page : 1;
        this.pagecount = count > 0 ? count : 1;
        this.limit = limit > 0 ? limit : 20;
        this.total = total > 0 ? total : 0;
        return this;
    }

    public String string() {
        return new Gson().newBuilder().disableHtmlEscaping().create().toJson(this);
    }
}
