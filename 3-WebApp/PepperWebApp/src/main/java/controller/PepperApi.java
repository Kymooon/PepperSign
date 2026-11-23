package controller;

import com.google.gson.Gson;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Funzioni comuni delle API /api/pepper/*: risposta JSON, descrizione di un
 * comando e inserimento in coda con il controllo "robot collegato".
 */
final class PepperApi {

    static final Gson GSON = new Gson();

    static final String ROBOT_OFFLINE_MESSAGE =
            "Robot non collegato: il controller di Pepper non risponde. "
            + "Controlla che Controll sia avviato e connesso al robot.";

    private PepperApi() {
    }

    static void writeJson(HttpServletResponse resp, int status, Map<String, Object> payload) throws IOException {
        resp.setStatus(status);
        resp.setContentType("application/json");
        resp.setCharacterEncoding("UTF-8");
        resp.setHeader("Cache-Control", "no-store");
        resp.getWriter().write(GSON.toJson(payload));
    }

    static Map<String, Object> error(String message) {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("ok", false);
        out.put("error", message);
        return out;
    }

    /** Stato di un comando come lo vede il tablet. */
    static Map<String, Object> describe(PepperCommand cmd, PepperCommandBus bus) {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("ok", true);
        out.put("id", cmd.getId());
        out.put("action", cmd.getAction());
        if (cmd.getGestureId() != null) {
            out.put("gestureId", cmd.getGestureId());
        }
        out.put("status", cmd.getStatus());
        out.put("final", cmd.isFinal());
        if (cmd.getResultMessage() != null) {
            out.put("message", cmd.getResultMessage());
        }
        out.put("robotOnline", bus.isControllerOnline());
        return out;
    }

    /**
     * Mette in coda il comando e scrive la risposta. Se Controll non e' collegato
     * il comando non viene accodato: il tablet riceve subito "robot non collegato"
     * invece di un falso "ok" (il comando scadrebbe comunque senza essere eseguito).
     *
     * @return true se il comando e' stato accodato
     */
    static boolean enqueueAndRespond(HttpServletResponse resp, PepperCommand cmd) throws IOException {
        PepperCommandBus bus = PepperCommandBus.getInstance();
        Map<String, Object> out = new LinkedHashMap<String, Object>();

        if (!bus.isControllerOnline()) {
            out.put("ok", false);
            out.put("queued", false);
            out.put("robotOnline", false);
            out.put("queueSize", bus.size());
            out.put("error", ROBOT_OFFLINE_MESSAGE);
            writeJson(resp, HttpServletResponse.SC_SERVICE_UNAVAILABLE, out);
            return false;
        }

        if (!bus.enqueue(cmd)) {
            out.put("ok", false);
            out.put("queued", false);
            out.put("robotOnline", true);
            out.put("queueSize", bus.size());
            out.put("error", "Coda Pepper piena o comando non accodabile.");
            writeJson(resp, HttpServletResponse.SC_SERVICE_UNAVAILABLE, out);
            return false;
        }

        out.put("ok", true);
        out.put("queued", true);
        out.put("id", cmd.getId());
        out.put("status", cmd.getStatus());
        out.put("robotOnline", true);
        out.put("queueSize", bus.size());
        out.put("action", cmd.getAction());
        if (cmd.getGestureId() != null) {
            out.put("gestureId", cmd.getGestureId());
        }
        out.put("ts", cmd.getTs());
        writeJson(resp, HttpServletResponse.SC_OK, out);
        return true;
    }
}
