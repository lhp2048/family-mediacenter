package com.family.mediacenter.sidecar;

import com.github.catvod.crawler.Spider;
import com.github.catvod.net.OkHttp;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import okhttp3.Request;
import okhttp3.Response;

public final class JarManager {

    private static final JarManager INSTANCE = new JarManager();

    private final Path cacheDir;
    private final Map<String, URLClassLoader> loaders = new ConcurrentHashMap<>();

    private JarManager() {
        cacheDir = Path.of(System.getProperty("user.home"), ".family_mediacenter", "spider_jars");
        try {
            Files.createDirectories(cacheDir);
        } catch (IOException ignored) {
        }
    }

    public static JarManager getInstance() {
        return INSTANCE;
    }

    public static String normalizeJarUrl(String raw) {
        if (raw == null) {
            return "";
        }
        String value = raw.trim();
        if (value.isEmpty()) {
            return "";
        }
        int semi = value.indexOf(';');
        if (semi > 0) {
            value = value.substring(0, semi);
        }
        return value.trim();
    }

    public static String expectedMd5(String raw) {
        if (raw == null) {
            return "";
        }
        String[] parts = raw.split(";");
        if (parts.length >= 3 && "md5".equalsIgnoreCase(parts[1].trim())) {
            return parts[2].trim().toLowerCase(Locale.ROOT);
        }
        return "";
    }

    public URLClassLoader loaderFor(String jarUrl) throws IOException {
        String normalized = normalizeJarUrl(jarUrl);
        if (normalized.isEmpty()) {
            return null;
        }
        return loaders.computeIfAbsent(normalized, this::createLoader);
    }

    private URLClassLoader createLoader(String jarUrl) {
        try {
            Path local = downloadJar(jarUrl);
            URL[] urls = new URL[] {local.toUri().toURL()};
            ClassLoader parent = Thread.currentThread().getContextClassLoader();
            if (parent == null) {
                parent = JarManager.class.getClassLoader();
            }
            return new URLClassLoader(urls, parent);
        } catch (Exception ex) {
            throw new IllegalStateException("无法加载 Spider JAR: " + rootMessage(ex), ex);
        }
    }

    private Path downloadJar(String jarSpec) throws Exception {
        String jarUrl = normalizeJarUrl(jarSpec);
        String expected = expectedMd5(jarSpec);
        String fileName = (expected.isEmpty() ? Integer.toHexString(jarUrl.hashCode()) : expected) + ".jar";
        Path target = cacheDir.resolve(fileName);

        if (Files.exists(target) && Files.size(target) > 0) {
            if (expected.isEmpty() || expected.equals(md5(target))) {
                return target;
            }
            Files.deleteIfExists(target);
        }

        Path tmp = cacheDir.resolve(fileName + ".part");
        Files.deleteIfExists(tmp);

        Request request = new Request.Builder()
                .url(jarUrl)
                .header(
                        "User-Agent",
                        "Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
                )
                .build();
        try (Response response = OkHttp.newCall(request)) {
            if (!response.isSuccessful() || response.body() == null) {
                throw new IOException("下载 JAR 失败 HTTP " + response.code());
            }
            try (InputStream in = response.body().byteStream()) {
                Files.copy(in, tmp, StandardCopyOption.REPLACE_EXISTING);
            }
        }

        if (!expected.isEmpty() && !expected.equals(md5(tmp))) {
            Files.deleteIfExists(tmp);
            throw new IOException("JAR MD5 校验失败，期望 " + expected);
        }

        Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING);
        return target;
    }

    public static String md5(Path file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("MD5");
        byte[] data = Files.readAllBytes(file);
        byte[] hash = digest.digest(data);
        StringBuilder sb = new StringBuilder();
        for (byte b : hash) {
            sb.append(String.format(Locale.ROOT, "%02x", b));
        }
        return sb.toString();
    }

    private static String rootMessage(Throwable ex) {
        Throwable current = ex;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current.getMessage() == null ? current.getClass().getSimpleName() : current.getMessage();
    }
}
