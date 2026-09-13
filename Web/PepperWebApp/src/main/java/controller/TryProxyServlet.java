package controller;

import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.MultipartConfig;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.Part;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.regex.Pattern;

/**
 * Servlet proxy tra la WebApp Java/Tomcat e il servizio Flask TRY.
 *
 * Flusso previsto:
 * - POST   /api/try                 -> inoltra video + gestureId a Flask /try
 *                                      Flask deve rispondere subito con sessionId/status queued.
 * - GET    /api/try/status/<sid>     -> inoltra a Flask /try/status/<sid>
 * - GET    /api/try/skeleton/<sid>.mp4 -> inoltra a Flask /try/skeleton/<sid>.mp4
 * - DELETE /api/try/<sid>            -> inoltra a Flask /try/<sid>
 *
 * Nota importante:
 * questa servlet NON deve aspettare la fine della generazione del video.
 * La generazione resta in background nel backend Python; il frontend fa polling sullo status.
 */
@WebServlet("/api/try/*")
@MultipartConfig
public class TryProxyServlet extends HttpServlet {

    private static final String DEFAULT_TRY_BASE = "http://127.0.0.1:5000";

    private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(10);
    private static final Duration POST_TIMEOUT = Duration.ofSeconds(120);
    private static final Duration STATUS_TIMEOUT = Duration.ofSeconds(30);
    private static final Duration SKELETON_TIMEOUT = Duration.ofSeconds(300);
    private static final Duration DELETE_TIMEOUT = Duration.ofSeconds(30);

    private static final int BUFFER_SIZE = 8192;

    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(CONNECT_TIMEOUT)
            .build();

    private static final Pattern SAFE_GESTURE_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{1,100}$");
    private static final Pattern SAFE_SESSION_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{1,120}$");
    private static final Pattern SAFE_SKELETON_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{1,120}\\.mp4$");

    private String getTryBase() {
        String configured = getServletConfig() != null ? getServletConfig().getInitParameter("tryBase") : null;
        return (configured != null && !configured.trim().isEmpty())
                ? configured.trim()
                : DEFAULT_TRY_BASE;
    }

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException, ServletException {
        String pathInfo = request.getPathInfo();
        if (pathInfo != null && pathInfo.length() > 1) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND, "Not Found");
            return;
        }

        Part videoPart = request.getPart("video");
        String gestureId = normalize(request.getParameter("gestureId"));

        if (videoPart == null || videoPart.getSize() <= 0) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "File video mancante (campo 'video')");
            return;
        }
        if (gestureId.isEmpty()) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "gestureId mancante");
            return;
        }
        if (!SAFE_GESTURE_PATTERN.matcher(gestureId).matches()) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "gestureId non valido");
            return;
        }

        String boundary = "----PepperSignTryBoundary" + System.currentTimeMillis();
        byte[] body = buildMultipart(boundary, videoPart, gestureId);

        String targetUrl = getTryBase() + "/try";
        log("[TRY-PROXY] POST -> " + targetUrl + " gestureId=" + gestureId + " uploadBytes=" + videoPart.getSize());

        HttpRequest proxied = HttpRequest.newBuilder()
                .uri(URI.create(targetUrl))
                .timeout(POST_TIMEOUT)
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        proxyJsonOrSmallResponse(proxied, response, "POST /api/try");
    }

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        String pathInfo = request.getPathInfo();
        if (pathInfo == null || "/".equals(pathInfo) || pathInfo.isEmpty()) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND, "Not Found");
            return;
        }

        ResolvedTarget resolved = resolveSafeGetTarget(pathInfo);
        if (resolved == null) {
            log("[TRY-PROXY] GET path non consentito: " + pathInfo);
            response.sendError(HttpServletResponse.SC_NOT_FOUND, "Not Found");
            return;
        }

        log("[TRY-PROXY] GET -> " + resolved.url);

        HttpRequest proxied = HttpRequest.newBuilder()
                .uri(URI.create(resolved.url))
                .timeout(resolved.timeout)
                .GET()
                .build();

        if (resolved.video) {
            proxyStreamingResponse(proxied, response, "GET /api/try" + pathInfo);
        } else {
            proxyJsonOrSmallResponse(proxied, response, "GET /api/try" + pathInfo);
        }
    }

    @Override
    protected void doDelete(HttpServletRequest request, HttpServletResponse response) throws IOException {
        String pathInfo = request.getPathInfo();
        if (pathInfo == null || "/".equals(pathInfo) || pathInfo.isEmpty()) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND, "Not Found");
            return;
        }

        String sessionId = pathInfo.startsWith("/") ? pathInfo.substring(1) : pathInfo;
        if (!SAFE_SESSION_PATTERN.matcher(sessionId).matches()) {
            log("[TRY-PROXY] DELETE con sessionId non valido: " + sessionId);
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "Session id non valido");
            return;
        }

        String targetUrl = getTryBase() + "/try/" + sessionId;
        log("[TRY-PROXY] DELETE -> " + targetUrl);

        HttpRequest proxied = HttpRequest.newBuilder()
                .uri(URI.create(targetUrl))
                .timeout(DELETE_TIMEOUT)
                .DELETE()
                .build();

        proxyJsonOrSmallResponse(proxied, response, "DELETE /api/try/" + sessionId);
    }

    private ResolvedTarget resolveSafeGetTarget(String pathInfo) {
        if (pathInfo.startsWith("/status/")) {
            String sessionId = pathInfo.substring("/status/".length());
            if (SAFE_SESSION_PATTERN.matcher(sessionId).matches()) {
                return new ResolvedTarget(getTryBase() + "/try/status/" + sessionId, STATUS_TIMEOUT, false);
            }
            return null;
        }

        if (pathInfo.startsWith("/skeleton/")) {
            String fileName = pathInfo.substring("/skeleton/".length());
            if (SAFE_SKELETON_PATTERN.matcher(fileName).matches()) {
                return new ResolvedTarget(getTryBase() + "/try/skeleton/" + fileName, SKELETON_TIMEOUT, true);
            }
            return null;
        }

        return null;
    }

    /**
     * Proxy per risposte piccole, come JSON di upload/status/delete.
     */
    private void proxyJsonOrSmallResponse(HttpRequest proxied, HttpServletResponse servletResp, String label) throws IOException {
        long start = System.currentTimeMillis();
        try {
            HttpResponse<byte[]> proxiedResp = CLIENT.send(proxied, HttpResponse.BodyHandlers.ofByteArray());
            long elapsed = System.currentTimeMillis() - start;
            log("[TRY-PROXY] " + label + " <- status=" + proxiedResp.statusCode() + " in " + elapsed + " ms");

            servletResp.setStatus(proxiedResp.statusCode());
            copyCommonHeaders(proxiedResp, servletResp);
            ensureContentType(proxiedResp, servletResp, proxied.uri().toString());

            byte[] body = proxiedResp.body();
            if (body != null && body.length > 0) {
                servletResp.setContentLengthLong(body.length);
                try (OutputStream os = servletResp.getOutputStream()) {
                    os.write(body);
                }
            }

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log("[TRY-PROXY] " + label + " interrotto: " + e.getMessage());
            servletResp.sendError(HttpServletResponse.SC_BAD_GATEWAY, "Proxy interrotto");
        } catch (Exception e) {
            long elapsed = System.currentTimeMillis() - start;
            log("[TRY-PROXY] " + label + " errore dopo " + elapsed + " ms: " + e.getMessage());
            servletResp.sendError(HttpServletResponse.SC_BAD_GATEWAY, "Proxy error: " + e.getMessage());
        }
    }

    /**
     * Proxy streaming per file video MP4.
     * Evita di caricare tutto lo skeleton.mp4 in memoria prima di inviarlo al browser.
     */
    private void proxyStreamingResponse(HttpRequest proxied, HttpServletResponse servletResp, String label) throws IOException {
        long start = System.currentTimeMillis();
        try {
            HttpResponse<InputStream> proxiedResp = CLIENT.send(proxied, HttpResponse.BodyHandlers.ofInputStream());
            long firstResponseMs = System.currentTimeMillis() - start;
            log("[TRY-PROXY] " + label + " <- status=" + proxiedResp.statusCode() + " firstResponse=" + firstResponseMs + " ms");

            servletResp.setStatus(proxiedResp.statusCode());
            copyCommonHeaders(proxiedResp, servletResp);
            ensureContentType(proxiedResp, servletResp, proxied.uri().toString());

            proxiedResp.headers().firstValueAsLong("content-length")
                    .ifPresent(servletResp::setContentLengthLong);

            try (InputStream in = proxiedResp.body(); OutputStream out = servletResp.getOutputStream()) {
                byte[] buffer = new byte[BUFFER_SIZE];
                int read;
                while ((read = in.read(buffer)) != -1) {
                    out.write(buffer, 0, read);
                }
                out.flush();
            }

            long elapsed = System.currentTimeMillis() - start;
            log("[TRY-PROXY] " + label + " streaming completato in " + elapsed + " ms");

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log("[TRY-PROXY] " + label + " interrotto: " + e.getMessage());
            servletResp.sendError(HttpServletResponse.SC_BAD_GATEWAY, "Proxy interrotto");
        } catch (Exception e) {
            long elapsed = System.currentTimeMillis() - start;
            log("[TRY-PROXY] " + label + " errore dopo " + elapsed + " ms: " + e.getMessage());
            servletResp.sendError(HttpServletResponse.SC_BAD_GATEWAY, "Proxy error: " + e.getMessage());
        }
    }

    private static void copyCommonHeaders(HttpResponse<?> from, HttpServletResponse to) {
        copyHeaderIfPresent(from, to, "content-type", "Content-Type");
        copyHeaderIfPresent(from, to, "cache-control", "Cache-Control");
        copyHeaderIfPresent(from, to, "pragma", "Pragma");
        copyHeaderIfPresent(from, to, "content-disposition", "Content-Disposition");
        copyHeaderIfPresent(from, to, "etag", "ETag");
        copyHeaderIfPresent(from, to, "last-modified", "Last-Modified");
    }

    private static void ensureContentType(HttpResponse<?> proxiedResp, HttpServletResponse servletResp, String url) {
        if (headerFirst(proxiedResp, "content-type") == null) {
            if (url.endsWith(".mp4")) {
                servletResp.setContentType("video/mp4");
            } else {
                servletResp.setContentType("application/json; charset=UTF-8");
            }
        }
    }

    private static void copyHeaderIfPresent(HttpResponse<?> from, HttpServletResponse to, String sourceName, String targetName) {
        String value = headerFirst(from, sourceName);
        if (value != null) {
            if ("Content-Type".equalsIgnoreCase(targetName)) {
                to.setContentType(value);
            } else {
                to.setHeader(targetName, value);
            }
        }
    }

    private static String headerFirst(HttpResponse<?> resp, String name) {
        return resp.headers().firstValue(name).orElse(null);
    }

    private static byte[] buildMultipart(String boundary, Part videoPart, String gestureId) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        out.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Disposition: form-data; name=\"gestureId\"\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        out.write((gestureId + "\r\n").getBytes(StandardCharsets.UTF_8));

        String fileName = sanitizeFilename(videoPart.getSubmittedFileName());
        if (fileName == null || fileName.isEmpty()) {
            fileName = "video.webm";
        }

        out.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Disposition: form-data; name=\"video\"; filename=\"" + fileName + "\"\r\n")
                .getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Type: " + safeContentType(videoPart.getContentType()) + "\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8));

        try (InputStream in = videoPart.getInputStream()) {
            byte[] buf = new byte[BUFFER_SIZE];
            int r;
            while ((r = in.read(buf)) != -1) {
                out.write(buf, 0, r);
            }
        }
        out.write("\r\n".getBytes(StandardCharsets.UTF_8));

        out.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));

        return out.toByteArray();
    }

    private static String safeContentType(String ct) {
        if (ct == null || ct.trim().isEmpty()) {
            return "application/octet-stream";
        }
        return ct;
    }

    private static String sanitizeFilename(String s) {
        if (s == null) {
            return null;
        }
        s = s.replace("\\", "/");
        int idx = s.lastIndexOf("/");
        if (idx >= 0) {
            s = s.substring(idx + 1);
        }
        return s.replace("\"", "");
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }

    private static class ResolvedTarget {
        final String url;
        final Duration timeout;
        final boolean video;

        ResolvedTarget(String url, Duration timeout, boolean video) {
            this.url = url;
            this.timeout = timeout;
            this.video = video;
        }
    }
}
