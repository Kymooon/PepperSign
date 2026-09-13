package controller;

import com.google.gson.Gson;
import com.google.gson.JsonSyntaxException;
import com.google.gson.reflect.TypeToken;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.lang.reflect.Type;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Gestisce l'avvio di una lesson:
 * - riceve un target in JSON
 * - verifica se il video esiste già nella repository locale
 * - se non esiste, chiede al microservizio Python di generarlo
 */
@WebServlet("/api/lesson")
public class LessonServlet extends HttpServlet {

    private static final String DEFAULT_PYTHON_API_URL = "http://127.0.0.1:5000/process";
    private static final Gson GSON = new Gson();
    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();
    private static final Type MAP_TYPE = new TypeToken<Map<String, Object>>() {}.getType();

    /**
     * Ammessi solo nomi semplici e sicuri.
     */
    private static final Pattern SAFE_NAME_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{1,100}$");

    private Path getRepositoryPath() {
        String configured = getServletConfig() != null ? getServletConfig().getInitParameter("mediaRepositoryPath") : null;
        if (configured != null && !configured.trim().isEmpty()) {
            return Paths.get(configured.trim());
        }
        return Paths.get(System.getProperty("user.home"), "PepperSignData");
    }

    private String getPythonApiUrl() {
        String configured = getServletConfig() != null ? getServletConfig().getInitParameter("pythonApiUrl") : null;
        return (configured != null && !configured.trim().isEmpty())
                ? configured.trim()
                : DEFAULT_PYTHON_API_URL;
    }

    private boolean isJsonRequest(HttpServletRequest request) {
        String contentType = request.getContentType();
        return contentType != null && contentType.toLowerCase().contains("application/json");
    }

    private boolean isSafeName(String value) {
        return value != null && SAFE_NAME_PATTERN.matcher(value).matches();
    }

    private boolean videoExists(String name) {
        Path p = getRepositoryPath().resolve(name + ".mp4");
        return Files.exists(p);
    }

    private void writeJson(HttpServletResponse response, int status, Map<String, Object> payload) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write(GSON.toJson(payload));
    }

    private Map<String, Object> newPayload(String target, String status) {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("target", target);
        out.put("status", status);
        return out;
    }

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        if (!isJsonRequest(request)) {
            Map<String, Object> out = new LinkedHashMap<String, Object>();
            out.put("status", "ERROR");
            out.put("error", "Content-Type non valido. Atteso application/json.");
            writeJson(response, HttpServletResponse.SC_BAD_REQUEST, out);
            return;
        }

        String body = new String(request.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
        if (body.isEmpty()) {
            Map<String, Object> out = new LinkedHashMap<String, Object>();
            out.put("status", "ERROR");
            out.put("error", "Body JSON vuoto.");
            writeJson(response, HttpServletResponse.SC_BAD_REQUEST, out);
            return;
        }

        final Map<String, Object> input;
        try {
            input = GSON.fromJson(body, MAP_TYPE);
        } catch (JsonSyntaxException e) {
            Map<String, Object> out = new LinkedHashMap<String, Object>();
            out.put("status", "ERROR");
            out.put("error", "JSON non valido.");
            writeJson(response, HttpServletResponse.SC_BAD_REQUEST, out);
            return;
        }

        String target = "";
        if (input != null && input.get("target") != null) {
            target = input.get("target").toString().trim().toLowerCase();
        }

        if (target.isEmpty()) {
            Map<String, Object> out = new LinkedHashMap<String, Object>();
            out.put("status", "ERROR");
            out.put("error", "target mancante");
            writeJson(response, HttpServletResponse.SC_BAD_REQUEST, out);
            return;
        }

        if (!isSafeName(target)) {
            Map<String, Object> out = new LinkedHashMap<String, Object>();
            out.put("status", "ERROR");
            out.put("error", "target non valido. Usa solo lettere, numeri, underscore o trattino.");
            writeJson(response, HttpServletResponse.SC_BAD_REQUEST, out);
            return;
        }

        if (videoExists(target)) {
            writeJson(response, HttpServletResponse.SC_OK, newPayload(target, "FOUND"));
            return;
        }

        try {
            callVideoGeneration(target);
            writeJson(response, HttpServletResponse.SC_OK, newPayload(target, "GENERATING"));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log("Thread interrotto durante la chiamata alla Video Generation.", e);

            Map<String, Object> out = newPayload(target, "ERROR");
            out.put("error", "Operazione interrotta durante la chiamata a Python.");
            writeJson(response, HttpServletResponse.SC_INTERNAL_SERVER_ERROR, out);
        } catch (Exception e) {
            log("Errore nella LessonServlet.", e);

            Map<String, Object> out = newPayload(target, "ERROR");
            out.put("error", "Errore chiamata Video Generation");
            writeJson(response, HttpServletResponse.SC_INTERNAL_SERVER_ERROR, out);
        }
    }

    private void callVideoGeneration(String filename) throws IOException, InterruptedException {
        String json = GSON.toJson(java.util.Collections.singletonMap("filename", filename));

        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(getPythonApiUrl()))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(180))
                .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> res = HTTP_CLIENT.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        if (res.statusCode() != HttpServletResponse.SC_OK) {
            throw new IOException("VideoGen status=" + res.statusCode() + " body=" + res.body());
        }
    }
}
