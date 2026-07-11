package android.content;

import java.io.File;

/** Minimal Android Context stub for PC-side CatVod Spider execution. */
public class Context {

    public Context getApplicationContext() {
        return this;
    }

    public File getCacheDir() {
        File dir = new File(System.getProperty("java.io.tmpdir"), "tvbox-sidecar-cache");
        if (!dir.exists()) {
            dir.mkdirs();
        }
        return dir;
    }

    public File getFilesDir() {
        return getCacheDir();
    }

    public String getPackageName() {
        return "com.family.mediacenter.sidecar";
    }
}
