package controller;

import java.io.IOException;

import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/api/pepper/next")
public class PepperNextServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        handle(resp);
    }

    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        handle(resp);
    }

    private void handle(HttpServletResponse resp) throws IOException {
        resp.setContentType("application/json");
        resp.setCharacterEncoding("UTF-8");

        PepperCommand cmd = PepperCommandBus.getInstance().poll();

        if (cmd == null) {
            cmd = PepperCommand.none();
        }

        String json = toJson(cmd);
        resp.getWriter().write(json);
    }

    private String toJson(PepperCommand cmd) {
        StringBuilder sb = new StringBuilder();

        sb.append("{");
        sb.append("\"action\":\"").append(escape(cmd.getAction())).append("\",");
        sb.append("\"text\":\"").append(escape(cmd.getText())).append("\",");
        sb.append("\"gestureId\":\"").append(escape(cmd.getGestureId())).append("\",");
        sb.append("\"ts\":").append(cmd.getTs());
        sb.append("}");

        return sb.toString();
    }

    private String escape(String s) {
        if (s == null) {
            return "";
        }
        return s
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t");
    }
}