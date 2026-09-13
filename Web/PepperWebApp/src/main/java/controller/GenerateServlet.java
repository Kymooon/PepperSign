package controller;

import com.google.gson.Gson;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.File;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.time.Duration;
import java.util.Collections;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Servlet che riceve il nome di un elemento/gesto e delega a un microservizio Python
 * la generazione del video corrispondente.
 */
@WebServlet("/api/generate")
public class GenerateServlet extends HttpServlet {

    private static final String DEFAULT_MEDIA_OUTPUT_DIR =
            System.getProperty("user.home") + File.separator + "PepperSignData";
    private static final String DEFAULT_PYTHON_API_URL = "http://127.0.0.1:5000/process";

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private static final Gson GSON = new Gson();

    /**
     * Consente nomi semplici e sicuri per i file.
     * Ammessi: lettere, numeri, underscore e trattino.
     */
    private static final Pattern SAFE_NAME_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{1,100}$");

    private String getMediaOutputDir() {
        String configured = getServletConfig() != null ? getServletConfig().getInitParameter("mediaOutputDir") : null;
        return (configured != null && !configured.trim().isEmpty())
                ? configured.trim()
                : DEFAULT_MEDIA_OUTPUT_DIR;
    }

    private String getPythonApiUrl() {
        String configured = getServletConfig() != null ? getServletConfig().getInitParameter("pythonApiUrl") : null;
        return (configured != null && !configured.trim().isEmpty())
                ? configured.trim()
                : DEFAULT_PYTHON_API_URL;
    }

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        String elementName = normalize(request.getParameter("name"));

        if (elementName == null || elementName.isEmpty()) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "Nome elemento mancante.");
            return;
        }

        if (!isSafeName(elementName)) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST,
                    "Nome elemento non valido. Usa solo lettere, numeri, underscore o trattino.");
            return;
        }

        if (Files.exists(Paths.get(getMediaOutputDir(), elementName + ".mp4"))) {
            response.sendError(HttpServletResponse.SC_CONFLICT, "Video già presente.");
            return;
        }

        try {
            boolean success = callPythonService(elementName);

            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");

            if (success) {
                response.setStatus(HttpServletResponse.SC_OK);
                response.getWriter().write(toJson(true, "Generazione completata con successo."));
            } else {
                response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR,
                        "Python ha restituito un errore.");
            }

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log("Thread interrotto durante la comunicazione col servizio Python.", e);
            response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR,
                    "Operazione interrotta durante la generazione.");
        } catch (Exception e) {
            log("Errore nella GenerateServlet.", e);
            response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR,
                    "Impossibile comunicare con il servizio Python. È avviato?");
        }
    }

    private String normalize(String value) {
        return value == null ? null : value.trim();
    }

    private boolean isSafeName(String value) {
        return SAFE_NAME_PATTERN.matcher(value).matches();
    }

    private String toJson(boolean success, String message) {
        Map<String, Object> payload = new java.util.LinkedHashMap<String, Object>();
        payload.put("success", success);
        payload.put("message", message);
        return GSON.toJson(payload);
    }

    /**
     * Invia il nome del file da generare al microservizio Python via JSON.
     */
    private boolean callPythonService(String filename) throws IOException, InterruptedException {
        String jsonInputString = GSON.toJson(Collections.singletonMap("filename", filename));

        HttpRequest httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(getPythonApiUrl()))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonInputString, StandardCharsets.UTF_8))
                .timeout(Duration.ofMinutes(10))
                .build();

        HttpResponse<String> httpResponse = HTTP_CLIENT.send(
                httpRequest,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        log("GenerateServlet -> Python status=" + httpResponse.statusCode() + " body=" + httpResponse.body());

        return httpResponse.statusCode() == HttpServletResponse.SC_OK;
    }
}
