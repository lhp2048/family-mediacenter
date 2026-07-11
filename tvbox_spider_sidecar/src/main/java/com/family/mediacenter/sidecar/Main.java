package com.family.mediacenter.sidecar;

public final class Main {

    public static void main(String[] args) {
        int port = 9978;
        if (args.length > 0) {
            try {
                port = Integer.parseInt(args[0]);
            } catch (NumberFormatException ignored) {
            }
        }
        SidecarServer server = new SidecarServer(port);
        com.github.catvod.spider.Proxy.setPort(port);
        server.start();
        System.out.println("TVBox Spider Sidecar listening on http://127.0.0.1:" + port);
        Runtime.getRuntime().addShutdownHook(new Thread(server::stop));
    }
}
