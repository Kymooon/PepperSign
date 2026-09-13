package controller;

import com.google.gson.Gson;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.MultipartConfig;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.*;

import java.io.*;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.Map;

@WebServlet("/api/asr")
@MultipartConfig
public class AsrServlet extends HttpServlet {

    // Flask ASR service (nuovo)
    private static final String ASR_API_URL = "http://127.0.0.1:5000/transcribe";

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        Part audioPart = request.getPart("audio");
        if (audioPart == null || audioPart.getSize() == 0) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "Audio mancante (campo 'audio').");
            return;
        }

        // Salvataggio temporaneo
        Path tempFile = Files.createTempFile("peppersign_audio_", ".bin");
        try (InputStream in = audioPart.getInputStream()) {
            Files.copy(in, tempFile, StandardCopyOption.REPLACE_EXISTING);
        }

        try {
            Map<String, Object> asrJson = callAsrFlask(tempFile);

            response.setContentType("application/json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write(new Gson().toJson(asrJson));

        } catch (Exception e) {
            e.printStackTrace();
            response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR,
                    "Errore comunicazione con ASR Flask. È avviato su :5001?");
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }

    private Map<String, Object> callAsrFlask(Path audioPath) throws IOException, InterruptedException {
        String boundary = "----PepperSignBoundary" + System.currentTimeMillis();
        byte[] fileBytes = Files.readAllBytes(audioPath);

        ByteArrayOutputStream body = new ByteArrayOutputStream();
        body.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        body.write(("Content-Disposition: form-data; name=\"audio\"; filename=\"audio.bin\"\r\n").getBytes(StandardCharsets.UTF_8));
        body.write(("Content-Type: application/octet-stream\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        body.write(fileBytes);
        body.write("\r\n".getBytes(StandardCharsets.UTF_8));
        body.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(ASR_API_URL))
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .timeout(Duration.ofSeconds(120))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body.toByteArray()))
                .build();

        HttpResponse<String> res = client.send(req, HttpResponse.BodyHandlers.ofString());

        if (res.statusCode() != 200) {
            throw new IOException("ASR Flask status=" + res.statusCode() + " body=" + res.body());
        }

        return new Gson().fromJson(res.body(), Map.class);
    }
}
