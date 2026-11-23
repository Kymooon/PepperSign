package controller;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Esito di un comando, inviato da Controll dopo l'esecuzione:
 * POST /api/pepper/result  {"id": "...", "ok": true|false, "message": "..."}
 * Dati non validi -> 400; id sconosciuto -> 404.
 */
@WebServlet("/api/pepper/result")
public class PepperResultServlet extends HttpServlet {

    static final int MAX_MESSAGE = 500;

    /** Esito letto dal corpo della richiesta. */
    static final class Result {
        final String id;
        final boolean ok;
        final String message;

        Result(String id, boolean ok, String message) {
            this.id = id;
            this.ok = ok;
            this.message = message;
        }
    }

    /**
     * Legge e valida il corpo JSON.
     *
     * @throws IllegalArgumentException con un messaggio per il chiamante se i dati non sono validi
     */
    static Result parse(String raw) {
        JsonObject body;
        try {
            JsonElement parsed = JsonParser.parseString(raw == null ? "" : raw);
            if (!parsed.isJsonObject()) {
                throw new IllegalArgumentException("atteso un oggetto JSON {\"id\", \"ok\", \"message\"}");
            }
            body = parsed.getAsJsonObject();
        } catch (RuntimeException e) {
            if (e instanceof IllegalArgumentException) {
                throw e;
            }
            throw new IllegalArgumentException("corpo JSON non valido: atteso {\"id\", \"ok\", \"message\"}");
        }

        JsonPrimitive id = primitive(body, "id");
        if (id == null || !id.isString() || id.getAsString().trim().isEmpty()) {
            throw new IllegalArgumentException("id mancante o non valido");
        }
        JsonPrimitive ok = primitive(body, "ok");
        if (ok == null || !ok.isBoolean()) {
            throw new IllegalArgumentException("ok mancante o non booleano");
        }
        String message = "";
        if (body.has("message") && !body.get("message").isJsonNull()) {
            JsonPrimitive m = primitive(body, "message");
            if (m == null) {
                throw new IllegalArgumentException("message deve essere un testo");
            }
            message = m.getAsString();
        }
        if (message.length() > MAX_MESSAGE) {
            message = message.substring(0, MAX_MESSAGE);
        }
        return new Result(id.getAsString().trim(), ok.getAsBoolean(), message);
    }

    private static JsonPrimitive primitive(JsonObject body, String name) {
        JsonElement value = body.get(name);
        return value != null && value.isJsonPrimitive() ? value.getAsJsonPrimitive() : null;
    }

    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        Result result;
        try {
            result = parse(req.getReader().lines().collect(Collectors.joining("\n")));
        } catch (IllegalArgumentException e) {
            PepperApi.writeJson(resp, HttpServletResponse.SC_BAD_REQUEST, PepperApi.error("Esito non valido: " + e.getMessage()));
            return;
        }

        boolean found = PepperCommandBus.getInstance().complete(result.id, result.ok, result.message);
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("ok", found);
        out.put("id", result.id);
        if (!found) {
            out.put("error", "Comando sconosciuto (gia' rimosso dallo storico o WebApp riavviata).");
        }
        PepperApi.writeJson(resp, found ? HttpServletResponse.SC_OK : HttpServletResponse.SC_NOT_FOUND, out);
    }
}
