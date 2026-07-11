package com.github.catvod.utils;

import com.github.catvod.constant.HttpHeaders;
import com.github.catvod.crawler.SpiderDebug;
import com.github.catvod.net.OkHttp;
import com.github.catvod.spider.Init;
import com.github.catvod.spider.Proxy;
import org.apache.commons.lang3.StringUtils;

import java.io.IOException;
import java.math.BigInteger;
import java.net.URI;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** PC-side subset of CatVod Util (no Swing/Android UI). */
public final class Util {

    public static final String CHROME =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    + "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
    public static final String CLIENT_ID = "76917ccccd4441c39457a04f6084fb2f";
    public static final List<String> MEDIA = Arrays.asList(
            "mp4", "mkv", "wmv", "flv", "avi", "iso", "mpg", "ts", "mp3", "aac", "flac", "m4a", "ape", "ogg"
    );
    public static final List<String> SUB = Arrays.asList("srt", "ass", "ssa", "vtt");
    public static final Pattern RULE = Pattern.compile(
            "http((?!http).){12,}?\\.(m3u8|mp4|flv|avi|mkv|rm|wmv|mpg|m4a|mp3)\\?.*|"
                    + "http((?!http).){12,}\\.(m3u8|mp4|flv|avi|mkv|rm|wmv|mpg|m4a|mp3)|"
                    + "http((?!http).)*?video/tos*"
    );

    private Util() {
    }

    public static boolean isVideoFormat(String url) {
        if (url == null) {
            return false;
        }
        if (url.contains("url=http") || url.contains(".js") || url.contains(".css") || url.contains(".html")) {
            return false;
        }
        return RULE.matcher(url).find();
    }

    public static String fixUrl(String base, String src) {
        if (src == null || src.isEmpty()) {
            return src;
        }
        if (src.startsWith("//")) {
            URI parse = URI.create(base);
            return parse.getScheme() + ":" + src;
        }
        if (!src.contains("://")) {
            URI parse = URI.create(base);
            return parse.getScheme() + "://" + parse.getHost() + src;
        }
        return src;
    }

    public static String getExt(String name) {
        if (name == null) {
            return "";
        }
        return name.contains(".") ? name.substring(name.lastIndexOf('.') + 1) : name;
    }

    public static boolean isSub(String ext) {
        return SUB.contains(ext);
    }

    public static boolean isMedia(String text) {
        return MEDIA.contains(getExt(text));
    }

    public static String getSize(double size) {
        if (size <= 0) {
            return "";
        }
        if (size > 1024 * 1024 * 1024 * 1024.0) {
            size /= (1024 * 1024 * 1024 * 1024.0);
            return String.format(Locale.ROOT, "%.2f%s", size, "TB");
        }
        if (size > 1024 * 1024 * 1024.0) {
            size /= (1024 * 1024 * 1024.0);
            return String.format(Locale.ROOT, "%.2f%s", size, "GB");
        }
        if (size > 1024 * 1024.0) {
            size /= (1024 * 1024.0);
            return String.format(Locale.ROOT, "%.2f%s", size, "MB");
        }
        size /= 1024.0;
        return String.format(Locale.ROOT, "%.2f%s", size, "KB");
    }

    public static String removeExt(String text) {
        return text != null && text.contains(".") ? text.substring(0, text.lastIndexOf('.')) : text;
    }

    public static void notify(String msg) {
        Init.execute(() -> {
            try {
                OkHttp.newCall(Proxy.getHostPort() + "/postMsg?msg=" + msg);
            } catch (IOException e) {
                SpiderDebug.log(e);
            }
        });
    }

    public static String stringJoin(String separate, Collection<?> list) {
        return StringUtils.join(list, separate);
    }

    public static String stringJoin(Collection<?> list, String separate) {
        return StringUtils.join(list, separate);
    }

    public static String MD5(String src) {
        return MD5(src, StandardCharsets.UTF_8.name());
    }

    public static String MD5(String src, String charset) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] messageDigest = md.digest(src.getBytes(Charset.forName(charset)));
            BigInteger no = new BigInteger(1, messageDigest);
            StringBuilder sb = new StringBuilder(no.toString(16));
            while (sb.length() < 32) {
                sb.insert(0, '0');
            }
            return sb.toString().toLowerCase(Locale.ROOT);
        } catch (Exception e) {
            return "";
        }
    }

    public static HashMap<String, String> webHeaders(String referer) {
        return webHeaders(referer, "", "");
    }

    public static HashMap<String, String> webHeaders(String referer, String cookie) {
        return webHeaders(referer, "", cookie);
    }

    public static HashMap<String, String> webHeaders(String referer, String url, String cookie) {
        HashMap<String, String> headers = new HashMap<>();
        headers.put(HttpHeaders.ACCEPT_LANGUAGE, "zh-CN,zh;q=0.9,en;q=0.8");
        headers.put(HttpHeaders.CONNECTION, "keep-alive");
        headers.put(HttpHeaders.USER_AGENT, CHROME);
        headers.put(HttpHeaders.ACCEPT, "*/*");
        if (StringUtils.isNotBlank(referer)) {
            headers.put(HttpHeaders.REFERER, referer);
        }
        if (StringUtils.isNotBlank(url)) {
            try {
                URI uri = URI.create(url);
                headers.put(HttpHeaders.HOST, uri.getHost());
            } catch (Exception ignored) {
            }
        }
        if (StringUtils.isNotBlank(cookie)) {
            headers.put(HttpHeaders.Cookie, cookie);
        }
        return headers;
    }

    public static String base64Encode(String str) {
        return Base64.getEncoder().encodeToString(str.getBytes(StandardCharsets.UTF_8));
    }

    public static String base64Decode(String str) {
        if (StringUtils.isBlank(str)) {
            return "";
        }
        return new String(Base64.getDecoder().decode(str), StandardCharsets.UTF_8);
    }

    public static void sleep(int millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }

    public static String findByRegex(String regex, String content, int groupCount) {
        Matcher matcher = Pattern.compile(regex).matcher(content);
        return matcher.find() ? matcher.group(groupCount) : "";
    }

    public static boolean isVip(String url) {
        List<String> hosts = Arrays.asList(
                "iqiyi.com", "v.qq.com", "youku.com", "le.com", "tudou.com",
                "mgtv.com", "sohu.com", "acfun.cn", "bilibili.com", "baofeng.com", "pptv.com"
        );
        for (String host : hosts) {
            if (url != null && url.contains(host)) {
                return true;
            }
        }
        return false;
    }
}
