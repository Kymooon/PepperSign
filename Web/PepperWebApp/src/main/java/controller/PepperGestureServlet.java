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
    private static final Pattern SAFE_GESTURE_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{1,100}$");

    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        String gestureId = normalize(req.getParameter("gestureId"));

        if (gestureId.isEmpty()) {
            writeError(resp, HttpServletResponse.SC_BAD_REQUEST,
                    "gestureId mancante.",
                    null);
            return;
        }

        if (!isSafeGestureId(gestureId)) {
            writeError(resp, HttpServletResponse.SC_BAD_REQUEST,
                    "gestureId non valido. Usa solo lettere, numeri, underscore o trattino.",
                    null);
            return;
        }

        PepperCommand cmd = PepperCommand.gesture(gestureId);
        boolean queued = PepperCommandBus.getInstance().enqueue(cmd);

        if (!queued) {
            writeError(resp, HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                    "Coda Pepper piena o comando non accodabile.",
                    null);
            return;
        }

        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("ok", true);
        out.put("queued", true);
        out.put("action", cmd.getAction());
        out.put("gestureId", cmd.getGestureId());
        out.put("ts", cmd.getTs());

        resp.setStatus(HttpServletResponse.SC_OK);
        resp.setContentType("application/json");
        resp.setCharacterEncoding("UTF-8");
        resp.getWriter().write(GSON.toJson(out));
    }

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        doPost(req, resp);
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }

    private boolean isSafeGestureId(String value) {
        return SAFE_GESTURE_PATTERN.matcher(value).matches();
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