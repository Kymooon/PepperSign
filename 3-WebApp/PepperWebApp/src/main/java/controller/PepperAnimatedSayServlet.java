package controller;

import com.google.gson.Gson;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Servlet che accoda un comando di tipo ANIMATED_SAY per Pepper.
 */
@WebServlet("/api/pepper/animated-say")
public class PepperAnimatedSayServlet extends HttpServlet {

    private static final Gson GSON = new Gson();

    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        String text = normalize(req.getParameter("text"));

        if (text.isEmpty()) {
            writeJson(resp, HttpServletResponse.SC_BAD_REQUEST,
                    buildResponse(false, false, PepperCommandBus.getInstance().size(),
                            "Parametro 'text' mancante o vuoto."));
            return;
        }

        if (!PepperApi.enqueueAndRespond(resp, PepperCommand.animatedSay(text))) {
            log("Comando ANIMATED_SAY non accodato (robot non collegato o coda piena).");
        }
    }

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        doPost(req, resp);
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }

    private Map<String, Object> buildResponse(boolean ok, boolean queued, int queueSize, String error) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", ok);
        out.put("queued", queued);
        out.put("queueSize", queueSize);

        if (error != null && !error.isEmpty()) {
            out.put("error", error);
        }

        return out;
    }

    private void writeJson(HttpServletResponse resp, int status, Map<String, Object> payload) throws IOException {
        resp.setStatus(status);
        resp.setContentType("application/json");
        resp.setCharacterEncoding("UTF-8");
        resp.getWriter().write(GSON.toJson(payload));
    }
}