package android.util;

/** Minimal android.util.Log stub for PC-side Spider JARs. */
public final class Log {

    private Log() {
    }

    public static int d(String tag, String msg) {
        System.out.println("[D/" + tag + "] " + msg);
        return 0;
    }

    public static int i(String tag, String msg) {
        System.out.println("[I/" + tag + "] " + msg);
        return 0;
    }

    public static int w(String tag, String msg) {
        System.err.println("[W/" + tag + "] " + msg);
        return 0;
    }

    public static int e(String tag, String msg) {
        System.err.println("[E/" + tag + "] " + msg);
        return 0;
    }

    public static int e(String tag, String msg, Throwable tr) {
        System.err.println("[E/" + tag + "] " + msg);
        if (tr != null) {
            tr.printStackTrace(System.err);
        }
        return 0;
    }
}
