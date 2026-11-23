package controller;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Il controller di Pepper (Controll) e' collegato? GET /api/pepper/robot
 * {"ok": true, "online": true|false, "lastPollMsAgo": 120, "queueSize": 0}
 */
@WebServlet("/api/pepper/robot")
public class PepperRobotServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        PepperCommandBus bus = PepperCommandBus.getInstance();
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("ok", true);
        out.put("online", bus.isControllerOnline());
        out.put("lastPollMsAgo", bus.millisSinceLastPoll());
        out.put("queueSize", bus.size());
        PepperApi.writeJson(resp, HttpServletResponse.SC_OK, out);
    }
}
