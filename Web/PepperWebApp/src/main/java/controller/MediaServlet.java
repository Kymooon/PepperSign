package controller;

import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.File;
import java.io.IOException;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.net.URLDecoder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Locale;

@WebServlet("/media/*")
public class MediaServlet extends HttpServlet {

    private static final String DEFAULT_BASE_PATH =
            System.getProperty("user.home") + File.separator + "PepperSignData";

    private String getBasePath() {
        String configured = getServletConfig() != null ? getServletConfig().getInitParameter("mediaBasePath") : null;
        return (configured != null && !configured.trim().isEmpty())
                ? configured.trim()
                : DEFAULT_BASE_PATH;
    }

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        String requestedFile = request.getPathInfo();

        if (requestedFile == null || requestedFile.isEmpty() || "/".equals(requestedFile)) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }

        if (requestedFile.startsWith("/")) {
            requestedFile = requestedFile.substring(1);
        }

        requestedFile = URLDecoder.decode(requestedFile, "UTF-8");

        if (!isAllowedMediaFile(requestedFile)) {
            log("Tentativo di accesso a file non consentito: " + requestedFile);
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "Tipo file non consentito");
            return;
        }

        Path basePath = Paths.get(getBasePath()).toAbsolutePath().normalize();
        Path resolvedPath = basePath.resolve(requestedFile).normalize();

        if (!resolvedPath.startsWith(basePath)) {
            log("Tentativo di path traversal bloccato: " + requestedFile);
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "Accesso negato");
            return;
        }

        File file = resolvedPath.toFile();

        if (!file.exists() || !file.isFile()) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND, "File non trovato");
            return;
        }

        long fileLength = file.length();
        String mimeType = getServletContext().getMimeType(file.getName());

        if (mimeType == null) {
            mimeType = Files.probeContentType(resolvedPath);
        }
        if (mimeType == null) {
            mimeType = guessMimeType(file.getName());
        }
        if (mimeType == null) {
            mimeType = "application/octet-stream";
        }

        response.setHeader("Accept-Ranges", "bytes");
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setContentType(mimeType);

        String rangeHeader = request.getHeader("Range");

        if (rangeHeader == null || !rangeHeader.startsWith("bytes=")) {
            response.setStatus(HttpServletResponse.SC_OK);
            response.setContentLengthLong(fileLength);
            streamWholeFile(file, response.getOutputStream());
            return;
        }

        // Supporto singolo range: bytes=start-end
        String rangeValue = rangeHeader.substring("bytes=".length()).trim();
        int dashIndex = rangeValue.indexOf('-');

        if (dashIndex < 0) {
            response.setHeader("Content-Range", "bytes */" + fileLength);
            response.sendError(HttpServletResponse.SC_REQUESTED_RANGE_NOT_SATISFIABLE);
            return;
        }

        String startPart = rangeValue.substring(0, dashIndex).trim();
        String endPart = rangeValue.substring(dashIndex + 1).trim();

        long start;
        long end;

        try {
            if (startPart.isEmpty()) {
                // es. bytes=-500  => ultimi 500 byte
                long suffixLength = Long.parseLong(endPart);
                if (suffixLength <= 0) {
                    throw new NumberFormatException("Suffix non valido");
                }
                start = Math.max(0, fileLength - suffixLength);
                end = fileLength - 1;
            } else {
                start = Long.parseLong(startPart);
                if (endPart.isEmpty()) {
                    end = fileLength - 1;
                } else {
                    end = Long.parseLong(endPart);
                }
            }
        } catch (NumberFormatException ex) {
            response.setHeader("Content-Range", "bytes */" + fileLength);
            response.sendError(HttpServletResponse.SC_REQUESTED_RANGE_NOT_SATISFIABLE);
            return;
        }

        if (start < 0 || end < start || start >= fileLength) {
            response.setHeader("Content-Range", "bytes */" + fileLength);
            response.sendError(HttpServletResponse.SC_REQUESTED_RANGE_NOT_SATISFIABLE);
            return;
        }

        if (end >= fileLength) {
            end = fileLength - 1;
        }

        long contentLength = end - start + 1;

        response.setStatus(HttpServletResponse.SC_PARTIAL_CONTENT);
        response.setHeader("Content-Range", "bytes " + start + "-" + end + "/" + fileLength);
        response.setContentLengthLong(contentLength);

        streamRange(file, response.getOutputStream(), start, contentLength);
    }

    private void streamWholeFile(File file, OutputStream out) throws IOException {
        try (RandomAccessFile raf = new RandomAccessFile(file, "r")) {
            byte[] buffer = new byte[8192];
            int bytesRead;

            while ((bytesRead = raf.read(buffer)) != -1) {
                out.write(buffer, 0, bytesRead);
            }
        }
    }

    private void streamRange(File file, OutputStream out, long start, long contentLength) throws IOException {
        try (RandomAccessFile raf = new RandomAccessFile(file, "r")) {
            raf.seek(start);

            byte[] buffer = new byte[8192];
            long remaining = contentLength;

            while (remaining > 0) {
                int bytesToRead = (int) Math.min(buffer.length, remaining);
                int bytesRead = raf.read(buffer, 0, bytesToRead);

                if (bytesRead == -1) {
                    break;
                }

                out.write(buffer, 0, bytesRead);
                remaining -= bytesRead;
            }
        }
    }

    private boolean isAllowedMediaFile(String fileName) {
        String lower = fileName.toLowerCase(Locale.ROOT);
        return lower.endsWith(".jpg")
                || lower.endsWith(".jpeg")
                || lower.endsWith(".png")
                || lower.endsWith(".gif")
                || lower.endsWith(".webp")
                || lower.endsWith(".mp4")
                || lower.endsWith(".mov");
    }

    private String guessMimeType(String fileName) {
        String lower = fileName.toLowerCase(Locale.ROOT);

        if (lower.endsWith(".mp4")) return "video/mp4";
        if (lower.endsWith(".mov")) return "video/quicktime";
        if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
        if (lower.endsWith(".png")) return "image/png";
        if (lower.endsWith(".gif")) return "image/gif";
        if (lower.endsWith(".webp")) return "image/webp";

        return null;
    }
}