package com.github.catvod.bean;

import com.google.gson.annotations.SerializedName;

import java.util.ArrayList;
import java.util.List;

public class Filter {

    @SerializedName("key")
    private String key;
    @SerializedName("name")
    private String name;
    @SerializedName("value")
    private List<Value> value = new ArrayList<>();

    public Filter() {
    }

    public Filter(String key, String name) {
        this.key = key;
        this.name = name;
    }

    public String getKey() {
        return key;
    }

    public void setKey(String key) {
        this.key = key;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public List<Value> getValue() {
        return value;
    }

    public void setValue(List<Value> value) {
        this.value = value;
    }

    public static class Value {
        @SerializedName("n")
        private String n;
        @SerializedName("v")
        private String v;

        public Value() {
        }

        public Value(String n, String v) {
            this.n = n;
            this.v = v;
        }

        public String getN() {
            return n;
        }

        public void setN(String n) {
            this.n = n;
        }

        public String getV() {
            return v;
        }

        public void setV(String v) {
            this.v = v;
        }
    }
}
