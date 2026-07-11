package com.github.catvod.utils;

import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/** Minimal Crypto helpers used by community Spider JARs. */
public final class Crypto {

    private Crypto() {
    }

    public static String md5(String input) {
        return Util.MD5(input);
    }

    public static String aesDecrypt(String data, String key, String iv) {
        try {
            Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
            SecretKeySpec keySpec = new SecretKeySpec(padKey(key).getBytes(StandardCharsets.UTF_8), "AES");
            IvParameterSpec ivSpec = new IvParameterSpec(padIv(iv).getBytes(StandardCharsets.UTF_8));
            cipher.init(Cipher.DECRYPT_MODE, keySpec, ivSpec);
            byte[] decoded = Base64.getDecoder().decode(data);
            return new String(cipher.doFinal(decoded), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "";
        }
    }

    public static String aesEncrypt(String data, String key, String iv) {
        try {
            Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
            SecretKeySpec keySpec = new SecretKeySpec(padKey(key).getBytes(StandardCharsets.UTF_8), "AES");
            IvParameterSpec ivSpec = new IvParameterSpec(padIv(iv).getBytes(StandardCharsets.UTF_8));
            cipher.init(Cipher.ENCRYPT_MODE, keySpec, ivSpec);
            return Base64.getEncoder().encodeToString(cipher.doFinal(data.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            return "";
        }
    }

    private static String padKey(String key) {
        if (key == null) {
            key = "";
        }
        if (key.length() >= 16) {
            return key.substring(0, 16);
        }
        return String.format("%-16s", key);
    }

    private static String padIv(String iv) {
        if (iv == null) {
            iv = "";
        }
        if (iv.length() >= 16) {
            return iv.substring(0, 16);
        }
        return String.format("%-16s", iv);
    }
}
