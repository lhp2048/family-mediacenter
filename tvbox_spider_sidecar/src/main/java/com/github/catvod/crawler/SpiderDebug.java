package com.github.catvod.crawler;

/** Minimal debug logger for PC-side Spider JARs. */
public final class SpiderDebug {

    private SpiderDebug() {
    }

    public static void log(Throwable throwable) {
        if (throwable != null) {
            throwable.printStackTrace(System.err);
        }
    }

    public static void log(String message) {
        if (message != null && !message.isEmpty()) {
            System.out.println("[Spider] " + message);
        }
    }
}
