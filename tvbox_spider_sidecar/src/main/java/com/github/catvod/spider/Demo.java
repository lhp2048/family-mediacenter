package com.github.catvod.spider;

import com.github.catvod.bean.Class;
import com.github.catvod.bean.Result;
import com.github.catvod.bean.Vod;
import com.github.catvod.crawler.Spider;

import java.util.Collections;
import java.util.HashMap;
import java.util.List;

/** Built-in spider for pipeline smoke tests (api=csp_Demo). */
public class Demo extends Spider {

    @Override
    public String homeContent(boolean filter) {
        return Result.string(
                Collections.singletonList(new Class("demo", "演示")),
                Collections.singletonList(new Vod("demo-1", "演示影片", "", "Sidecar OK"))
        );
    }

    @Override
    public String categoryContent(String tid, String pg, boolean filter, HashMap<String, String> extend) {
        return Result.get()
                .page(1, 1, 20, 1)
                .vod(Collections.singletonList(new Vod("demo-1", "演示影片", "", tid)))
                .string();
    }

    @Override
    public String searchContent(String key, boolean quick) {
        return Result.string(Collections.singletonList(new Vod("demo-1", "搜索:" + key, "", "match")));
    }

    @Override
    public String detailContent(List<String> ids) {
        String id = ids == null || ids.isEmpty() ? "demo-1" : ids.get(0);
        Vod vod = new Vod(id, "演示详情", "", "");
        vod.setVodPlayFrom("demo");
        vod.setVodPlayUrl("第1集$https://example.com/demo.m3u8");
        return Result.string(Collections.singletonList(vod));
    }

    @Override
    public String playerContent(String flag, String id, List<String> vipFlags) {
        return Result.get()
                .parse(0)
                .url("https://example.com/demo.m3u8")
                .header(Collections.emptyMap())
                .string();
    }
}
