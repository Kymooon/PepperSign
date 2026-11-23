package controller;

import com.google.gson.Gson;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Servlet che valida il gestureId e accoda un comando gesture
 * nel PepperCommandBus, invece di inoltrarlo a un servizio HTTP esterno.
 */
@WebServlet("/api/pepper/gesture")
public class PepperGestureServlet extends HttpServlet {

    private static final Gson GSON = new Gson();

    /**
     * Ammessi solo gestureId semplici e sicuri.
     */
    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        String gestureId = normalize(req.getParameter("gestureId"));

        if (gestureId.isEmpty()) {
            writeError(resp, HttpServletResponse.SC_BAD_REQUEST,
                    "gestureId mancante.",
                    null);
            return;
        }

        if (!GestureIds.isValidId(gestureId)) {
            writeError(resp, HttpServletResponse.SC_BAD_REQUEST,
                    "gestureId non valido. Usa solo lettere, numeri, underscore o trattino.",
                    null);
            return;
        }

        if (!PepperApi.enqueueAndRespond(resp, PepperCommand.gesture(gestureId))) {
            log("Comando PLAY_GESTURE non accodato (robot non collegato o coda piena).");
        }
    }

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        doPost(req, resp);
    }

    private String normalize(String value) {
        return GestureIds.normalize(value);
    }

    private void writeError(HttpServletResponse resp, int status, String error, String details) throws IOException {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("ok", false);
        out.put("error", error);

        if (details != null && !details.isEmpty()) {
            out.put("details", details);
        }

        resp.setStatus(status);
        resp.setContentType("application/json");
        resp.setCharacterEncoding("UTF-8");
        resp.getWriter().write(GSON.toJson(out));
    }
}