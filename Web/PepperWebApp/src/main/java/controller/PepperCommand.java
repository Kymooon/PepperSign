package controller;

import java.util.Locale;

/**
 * Classe modello che rappresenta un comando da inviare a Pepper.
 * Non esegue direttamente alcuna azione sul robot, ma crea un oggetto
 * strutturato contenente le informazioni del comando, come il tipo di azione
 * (ad esempio SAY o PLAY_GESTURE), l'eventuale testo da pronunciare,
 * il gesto da eseguire e un timestamp utile per polling o debug.
 */
public class PepperCommand {

    public static final String ACTION_SAY = "SAY";
    public static final String ACTION_ANIMATED_SAY = "ANIMATED_SAY";
    public static final String ACTION_PLAY_GESTURE = "PLAY_GESTURE";
    public static final String ACTION_NONE = "NONE";

    private String action;
    private String text;
    private String gestureId;
    private long ts;

    public PepperCommand() {
        // Costruttore vuoto utile per framework JSON Serializzazione e Deseralizzazione
    }

    public String getAction() {
        return action;
    }

    public String getText() {
        return text;
    }

    public String getGestureId() {
        return gestureId;
    }

    public long getTs() {
        return ts;
    }

    public boolean isSay() {
        return ACTION_SAY.equals(action);
    }

    public boolean isAnimatedSay() {return ACTION_ANIMATED_SAY.equals(action);}

    public boolean isGesture() {
        return ACTION_PLAY_GESTURE.equals(action);
    }

    public boolean isNone() {
        return ACTION_NONE.equals(action);
    }

    //Comando Say Semplice
    public static PepperCommand say(String text) {
        PepperCommand c = new PepperCommand();
        c.action = ACTION_SAY;
        c.text = normalizeText(text);
        c.ts = System.currentTimeMillis();
        return c;
    }

    // Comando Animated Say
    public static PepperCommand animatedSay(String text) {
        PepperCommand c = new PepperCommand();
        c.action = ACTION_ANIMATED_SAY;
        c.text = normalizeText(text);
        c.ts = System.currentTimeMillis();
        return c;
    }

    //Comando per inviare una gesture da riprodurrre
    public static PepperCommand gesture(String gestureId) {
        PepperCommand c = new PepperCommand();
        c.action = ACTION_PLAY_GESTURE;
        c.gestureId = normalizeGestureId(gestureId);
        c.ts = System.currentTimeMillis();
        return c;
    }

    //Comando vuoto
    public static PepperCommand none() {
        PepperCommand c = new PepperCommand();
        c.action = ACTION_NONE;
        c.ts = System.currentTimeMillis();
        return c;
    }



    //Utility:
    private static String normalizeText(String value) {
        if (value == null) {
            return "";
        }
        return value.trim();
    }

    private static String normalizeGestureId(String value) {
        if (value == null) {
            return "";
        }
        return value.trim().toLowerCase(Locale.ROOT);
    }
}
