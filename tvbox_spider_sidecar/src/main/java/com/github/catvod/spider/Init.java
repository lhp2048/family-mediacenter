package com.github.catvod.spider;

import android.content.Context;

import com.github.catvod.crawler.SpiderDebug;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Sidecar Init stub (CatVodSpider Init compatibility). */
public final class Init {

    private static final Context CONTEXT = new Context();
    private static final ExecutorService EXECUTOR = Executors.newFixedThreadPool(5);

    private Init() {
    }

    public static Context context() {
        return CONTEXT;
    }

    public static Init get() {
        return Holder.INSTANCE;
    }

    public static void init() {
        SpiderDebug.log("Sidecar spider runtime ready");
    }

    public static void init(Context context) {
        init();
    }

    public static void init(Context context, String extend) {
        init();
    }

    public static void execute(Runnable runnable) {
        if (runnable != null) {
            EXECUTOR.execute(runnable);
        }
    }

    private static final class Holder {
        private static final Init INSTANCE = new Init();
    }
}
